"""The progress routes the web app reads, through FastAPI, with the graph stubbed.

The service tests check knowledge tracing, the learning path and the review
list as functions. These check what the routes hand the progress page: the
same answers, in the envelope and field names the page reads. A renamed field
here does not fail a service test; it empties a section of the page.
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

STUDENT = CurrentUser({"user_id": "student_1", "full_name": "Ana", "email": "ana@example.com"}, "token")

# Long ago on purpose, so the review rules see these as old whatever the clock says.
ATTEMPTS = [
    *[
        {"concept": "assignment_logic", "score": 8, "total": 8, "percentage": 100.0, "timestamp": f"2020-01-0{day}T10:00:00+00:00"}
        for day in (1, 2, 3)
    ],
    {"concept": "boolean_logic", "score": 3, "total": 8, "percentage": 37.5, "timestamp": "2020-02-01T10:00:00+00:00"},
]


@pytest.fixture
def client(monkeypatch):
    def fake_query(query, parameters=None):
        if "PREREQUISITE_OF" in query:
            return [{"concept": "boolean_logic", "steps_away": 1}, {"concept": "assignment_logic", "steps_away": 2}]
        if "ATTEMPTED" in query:
            return ATTEMPTS
        return []

    monkeypatch.setattr(neo4j_db, "execute_query", fake_query)
    app.dependency_overrides[get_current_user] = lambda: STUDENT
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_the_curriculum_maps_every_concept_and_what_is_due(client):
    response = client.get("/api/progress/me/curriculum")

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 14
    states = {concept["concept"]: concept["state"] for concept in data["concepts"]}
    assert states["assignment_logic"] == "mastered"
    assert states["boolean_logic"] == "in_progress"

    due = {item["concept"]: item["reason"] for item in data["review_due"]}
    assert due == {"boolean_logic": "not_yet_known", "assignment_logic": "not_practised_recently"}
    # Not yet known comes before merely unpractised.
    assert data["review_due"][0]["concept"] == "boolean_logic"
    for item in data["review_due"]:
        assert set(item) == {"concept", "reason", "probability_known", "days_since_practice"}


def test_mastery_reports_the_belief_the_prediction_and_the_newest_attempt(client):
    response = client.get("/api/progress/me/mastery")

    assert response.status_code == 200, response.text
    estimates = {item["concept"]: item for item in response.json()["data"]}
    assert estimates["assignment_logic"]["mastered"] is True
    assert estimates["boolean_logic"]["mastered"] is False
    assert estimates["assignment_logic"]["observations"] == 24
    assert estimates["assignment_logic"]["last_attempt"] == "2020-01-03T10:00:00+00:00"
    for estimate in estimates.values():
        assert 0 < estimate["predicted_correct"] < 1


def test_the_learning_path_skips_what_knowledge_tracing_says_is_known(client):
    response = client.get("/api/progress/me/learning-path", params={"concept": "INCORRECT_CONDITIONAL_OPERATOR"})

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["concept"] == "conditional_logic"
    assert data["unmastered_prerequisites"] == [{"concept": "boolean_logic", "steps_away": 1}]
    assert data["start_here"] == "boolean_logic"
