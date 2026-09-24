"""The review after a PairPath session: who may ask for it, and what comes back.

The model is replaced in every test; nothing here calls Gemini or Neo4j.
"""

from __future__ import annotations

import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.services import session_review_service as service  # noqa: E402
from app.services.llm import LLMQuotaExhausted  # noqa: E402
from app.services.rag_service import NONE_FOUND, RetrievedNotes  # noqa: E402

KEY = "test-internal-key"
URL = "/api/session-review/generate"

CODE = "public class Main {\n  public static void main(String[] a) {\n    for (int i = 10; i <= 0; i++) {\n      System.out.println(i);\n    }\n  }\n}"

REQUEST = {
    "mode": "pair",
    "exercise": {
        "title": "Countdown",
        "description": "Print 10 down to 1.",
        "difficulty": "BEGINNER",
        "concept_tags": ["loop_boundaries"],
        "expected_output": "10\n9\n8",
        "reference_solution": "for (int i = 10; i >= 1; i--) System.out.println(i);",
    },
    "code": CODE,
    "outcome": "unsolved",
    "runs": {"total": 3, "correct": 0, "failed": 0},
    "teamwork": {
        "duration_minutes": 12,
        "role_switches": 1,
        "edits_by_driver": 40,
        "edits_by_navigator": 0,
        "runs_by_driver": 3,
        "runs_by_navigator": 0,
        "chat_messages": 2,
        "busiest_partner_edit_percent": 90,
    },
}


def review_json(**overrides) -> str:
    review = {
        "title": "Why the countdown printed nothing",
        "summary": "You ran it three times and nothing printed.",
        "steps": [
            {
                "teach": "The loop checks `i <= 0` before the first pass.",
                "lines": [3, 3],
                "question": {
                    "prompt": "What is `i <= 0` when `i` is 10?",
                    "options": ["true", "false", "It does not compile"],
                    "answer": 1,
                    "explanation": "10 is not less than or equal to 0.",
                },
            },
            {
                "teach": "A false condition on the first check means zero passes.",
                "lines": [3, 5],
                "question": {
                    "prompt": "How many times does the body run?",
                    "options": ["0", "1", "10"],
                    "answer": 0,
                    "explanation": "The condition is false at once.",
                },
            },
            {
                "teach": "Counting down needs `i--` and a condition that starts true.",
                "lines": [40, 90],
                "question": {
                    "prompt": "Which condition keeps going while i is 10 down to 1?",
                    "options": ["i <= 0", "i >= 1", "i == 1"],
                    "answer": 1,
                    "explanation": "It is true for 10 through 1.",
                },
            },
        ],
        "reflection": [{"prompt": "Who typed most?", "options": ["Mostly one of us", "About even", "Not sure"]}],
        "solutionNote": "It counts down with `i--`.",
    }
    review.update(overrides)
    return json.dumps(review)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_SERVICE_KEY", KEY)
    monkeypatch.setattr(service, "retrieve_notes", lambda *a, **k: RetrievedNotes(NONE_FOUND))
    return TestClient(app)


def answer_with(monkeypatch, *responses):
    """Make the model return these texts, in order; returns the prompts it got."""
    prompts: list[str] = []
    queue = list(responses)

    def fake(prompt: str) -> str:
        prompts.append(prompt)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(service, "generate", fake)
    return prompts


# ── Who may ask ──────────────────────────────────────────────────────────────


def test_no_key_is_401_and_a_wrong_key_is_403(client):
    assert client.post(URL, json=REQUEST).status_code == 401
    assert client.post(URL, json=REQUEST, headers={"X-Internal-Key": "nope"}).status_code == 403


def test_unconfigured_service_refuses_rather_than_accepting_anything(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_SERVICE_KEY", None)
    assert client.post(URL, json=REQUEST, headers={"X-Internal-Key": KEY}).status_code == 503


def test_a_student_token_does_not_open_it(client):
    response = client.post(URL, json=REQUEST, headers={"Authorization": "Bearer student-token"})
    assert response.status_code == 401


# ── What comes back ──────────────────────────────────────────────────────────


def test_returns_a_checked_review(client, monkeypatch):
    answer_with(monkeypatch, review_json())

    response = client.post(URL, json=REQUEST, headers={"X-Internal-Key": KEY})

    assert response.status_code == 200
    body = response.json()
    assert [s["question"]["answer"] for s in body["steps"]] == [1, 0, 1]
    # A range past the end of the code is dropped, not trusted.
    assert body["steps"][0]["lines"] == [3, 3]
    assert body["steps"][2]["lines"] is None
    assert body["reflection"][0]["options"] == ["Mostly one of us", "About even", "Not sure"]
    assert body["model"] == settings.MODEL_NAME


def test_solo_review_has_no_teamwork_questions(client, monkeypatch):
    answer_with(monkeypatch, review_json())
    solo = {**REQUEST, "mode": "solo", "teamwork": None}

    body = client.post(URL, json=solo, headers={"X-Internal-Key": KEY}).json()

    assert body["reflection"] == []


def test_a_broken_answer_is_regenerated_once(client, monkeypatch):
    bad = json.loads(review_json())
    bad["steps"][0]["question"]["answer"] = 7
    prompts = answer_with(monkeypatch, json.dumps(bad), review_json())

    response = client.post(URL, json=REQUEST, headers={"X-Internal-Key": KEY})

    assert response.status_code == 200
    assert len(prompts) == 2


def test_two_broken_answers_are_refused_not_patched(client, monkeypatch):
    answer_with(monkeypatch, "not json", '{"steps": []}')

    response = client.post(URL, json=REQUEST, headers={"X-Internal-Key": KEY})

    assert response.status_code == 503


def test_quota_is_reported_as_quota(client, monkeypatch):
    answer_with(monkeypatch, LLMQuotaExhausted("daily limit"))

    response = client.post(URL, json=REQUEST, headers={"X-Internal-Key": KEY})

    assert response.status_code == 429


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r["steps"][0]["question"].update(options=["same", "Same", "other"]),
        lambda r: r["steps"][0]["question"].update(answer=True),
        lambda r: r["steps"][0].update(question={"prompt": "?", "options": ["a", "b", "c"]}),
        lambda r: r.update(steps=r["steps"][:1]),
        lambda r: r.update(title=""),
    ],
)
def test_reviews_that_do_not_hold_together_are_rejected(mutate):
    review = json.loads(review_json())
    mutate(review)
    with pytest.raises(service.ReviewError):
        service.validate_review(review, service.SessionReviewRequest(**REQUEST))


# ── What the model is told ───────────────────────────────────────────────────


def test_the_prompt_carries_the_session_not_the_students(client, monkeypatch):
    prompts = answer_with(monkeypatch, review_json())
    client.post(URL, json=REQUEST, headers={"X-Internal-Key": KEY})
    prompt = prompts[0]

    # Their code, numbered so the model can point at lines.
    assert "3 |     for (int i = 10; i <= 0; i++) {" in prompt
    # The unsolved path guides rather than hands over the answer.
    assert "Do not hand" in prompt and "NOT SOLVED" in prompt
    # Teamwork as counts.
    assert "role switches: 1" in prompt and "90% of all edits" in prompt
    # The solution is there for the model, marked as not for the student.
    assert "i >= 1; i--" in prompt and "FOR YOU ONLY" in prompt
