"""The quiz confidence slider: what it changes in knowledge tracing, and what is stored.

Confidence is only worth asking for if it changes what an answer means. These
pin the two cases it changes - a confident wrong answer is a misconception, an
unsure right answer may be a guess - and that it changes nothing else, so
attempts saved before it existed trace exactly as they did.
"""

from __future__ import annotations

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.auth import CurrentUser, get_current_user  # noqa: E402
from app.db.neo4j_connection import neo4j_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import progress_service  # noqa: E402
from app.services.knowledge_tracing import PRIOR_KNOWN, _observe, calibration, trace  # noqa: E402

STUDENT = CurrentUser({"user_id": "student_1", "full_name": "Ana", "email": "ana@example.com"}, "token")


# ── Knowledge tracing ────────────────────────────────────────────────────────
def test_a_confident_wrong_answer_lowers_mastery_more_than_an_unsure_one():
    for belief in (0.3, 0.6, 0.9):
        confident = _observe(belief, correct=False, confidence="high")
        unsure = _observe(belief, correct=False, confidence="low")
        assert confident < unsure


def test_an_unsure_right_answer_is_weaker_evidence_than_a_sure_one():
    for belief in (0.2, 0.5, 0.8):
        guess = _observe(belief, correct=True, confidence="low")
        sure = _observe(belief, correct=True, confidence="high")
        assert guess < sure
        # Still evidence for knowing it, just less.
        assert guess > _observe(belief, correct=False, confidence="low")


@pytest.mark.parametrize("correct", [True, False])
def test_medium_and_unrated_answers_use_the_original_parameters(correct):
    assert _observe(0.5, correct, "medium") == _observe(0.5, correct)
    assert _observe(0.5, correct, None) == _observe(0.5, correct)


def test_an_attempt_without_answers_traces_exactly_as_before():
    assert trace([{"score": 3, "total": 4}]) == trace([{"score": 3, "total": 4, "answers": None}])


def test_answers_are_replayed_in_order_with_their_confidence():
    answers = [{"correct": True, "confidence": "high"}, {"correct": False, "confidence": "high"}]
    expected = _observe(_observe(PRIOR_KNOWN, True, "high"), False, "high")
    assert trace([{"score": 1, "total": 2, "answers": answers}]) == pytest.approx(expected)


# ── Calibration ─────────────────────────────────────────────────────────────
def test_calibration_is_a_brier_score_over_rated_answers():
    result = calibration([
        {"correct": True, "confidence": "high"},   # (1.0 - 1)^2 = 0
        {"correct": False, "confidence": "high"},  # (1.0 - 0)^2 = 1
        {"correct": True, "confidence": "low"},    # (0.33 - 1)^2 = 0.4489
        {"correct": False, "confidence": None},    # not rated: left out
    ])
    assert result["answers"] == 3
    assert result["brier"] == pytest.approx((0 + 1 + 0.4489) / 3, abs=1e-4)
    assert result["by_confidence"]["high"] == {"answers": 2, "correct": 1, "accuracy": 0.5}
    assert result["by_confidence"]["medium"]["accuracy"] is None
    assert result["confident_but_wrong"] == 1
    assert result["unsure_but_right"] == 1


def test_no_rated_answers_means_no_score_rather_than_zero():
    assert calibration([])["brier"] is None


# ── The API ─────────────────────────────────────────────────────────────────
@pytest.fixture
def client(monkeypatch):
    writes: list[dict] = []

    def fake_query(query, parameters=None):
        if query.lstrip().startswith("MERGE (s:Student"):
            writes.append(parameters)
            return [{"a": {}}]
        if "answers_correct IS NOT NULL" in query:
            return [
                {"answers_correct": [True, False], "answers_confidence": ["high", "high"]},
                {"answers_correct": [True], "answers_confidence": ["low"]},
            ]
        return []

    monkeypatch.setattr(neo4j_db, "execute_query", fake_query)
    monkeypatch.setattr(progress_service, "_seconds_on_lesson", lambda *args: None)
    app.dependency_overrides[get_current_user] = lambda: STUDENT
    try:
        yield TestClient(app), writes
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_each_answer_and_its_confidence_is_stored(client):
    http, writes = client
    response = http.post("/api/progress/update", json={
        "concept": "loop_boundaries", "score": 1, "total_questions": 2,
        "answers": [{"correct": True, "confidence": "low"}, {"correct": False, "confidence": "high"}],
    })
    assert response.status_code == 200, response.text
    assert writes[0]["answers_correct"] == [True, False]
    assert writes[0]["answers_confidence"] == ["low", "high"]
    assert writes[0]["score"] == 1 and writes[0]["total"] == 2


def test_score_only_updates_still_work(client):
    http, writes = client
    response = http.post("/api/progress/update", json={"concept": "loop_boundaries", "score": 3, "total_questions": 4})
    assert response.status_code == 200, response.text
    assert writes[0]["answers_correct"] is None


@pytest.mark.parametrize("answers", [
    [{"correct": True, "confidence": "low"}],                                            # too few
    [{"correct": True, "confidence": "low"}, {"correct": True, "confidence": "high"}],   # score is 1, not 2
    [{"correct": True, "confidence": "sure"}, {"correct": False, "confidence": "low"}],  # not a level
])
def test_answers_that_disagree_with_the_quiz_are_refused(client, answers):
    http, writes = client
    response = http.post("/api/progress/update", json={
        "concept": "loop_boundaries", "score": 1, "total_questions": 2, "answers": answers,
    })
    assert response.status_code == 422
    assert writes == []


def test_calibration_route_reads_every_rated_answer(client):
    http, _ = client
    response = http.get("/api/progress/me/calibration")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["answers"] == 3
    assert data["confident_but_wrong"] == 1
    assert data["unsure_but_right"] == 1
