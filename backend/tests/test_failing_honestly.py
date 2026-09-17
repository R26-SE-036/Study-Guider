"""When the graph or the language model is not there, say so.

Study Guider's failures used to look like answers. With the database
unreachable, execute_query returned None and every caller read that as "no
rows": a quiz result "saved" with nothing written, an empty progress page, a
curriculum with every concept untouched, and a lesson prompt telling the model
the student had never tried the concept - all with a 200. And a daily quota
error reached the student as the provider's raw error text under "try again
shortly", which it would not.

These tests hold each of those to an honest answer.
"""

from __future__ import annotations

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.genai import errors as genai_errors  # noqa: E402
from neo4j.exceptions import ServiceUnavailable  # noqa: E402

from app.api import quiz as quiz_api  # noqa: E402
from app.api import struggle as struggle_api  # noqa: E402
from app.core.auth import CurrentUser, get_current_user  # noqa: E402
from app.db import neo4j_connection  # noqa: E402
from app.db.neo4j_connection import GraphUnavailable, Neo4jConnection  # noqa: E402
from app.main import app  # noqa: E402
from app.services import game_summary_service, lesson_service, llm, progress_service, rag_service  # noqa: E402
from app.services.llm import DAILY_LIMIT_MESSAGE, LLMQuotaExhausted, LLMUnavailable  # noqa: E402

STUDENT = CurrentUser({"user_id": "student-1", "full_name": "Test Student"}, "token")

LESSON_JSON = (
    '{"issue": "Off by one", "explanation": "Because the loop runs once too often.", '
    '"incorrectCode": "for (int i = 0; i <= n; i++)", "correctCode": "for (int i = 0; i < n; i++)", '
    '"mermaidDiagram": "graph TD\\n A[Start] --> B[End]", "hint": "Where does it stop?"}'
)


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: STUDENT
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def graph_down(monkeypatch):
    def unreachable(*_args, **_kwargs):
        raise GraphUnavailable("down for this test")

    monkeypatch.setattr(neo4j_connection.neo4j_db, "execute_query", unreachable)


# ── The connection itself ───────────────────────────────────────────────────
def detached_connection(monkeypatch, connect_result=False):
    connection = Neo4jConnection.__new__(Neo4jConnection)
    connection.driver = None
    connection._retry_after = 0.0
    attempts = []

    def connect():
        attempts.append(1)
        return connect_result

    monkeypatch.setattr(connection, "connect", connect)
    return connection, attempts


def test_an_unreachable_database_raises_instead_of_returning_nothing(monkeypatch):
    connection, _ = detached_connection(monkeypatch)
    with pytest.raises(GraphUnavailable):
        connection.execute_query("RETURN 1")


def test_it_does_not_try_to_reconnect_before_every_query(monkeypatch):
    # One lesson makes several queries. Reconnecting before each against a host
    # that is not answering made the student wait through every attempt.
    connection, attempts = detached_connection(monkeypatch)
    for _ in range(5):
        with pytest.raises(GraphUnavailable):
            connection.execute_query("RETURN 1")
    assert len(attempts) == 1


class _Session:
    def __init__(self, outcomes):
        self.outcomes = outcomes

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def run(self, _query, _parameters):
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _Record:
    def __init__(self, data):
        self._data = data

    def data(self):
        return self._data


class _Driver:
    def __init__(self, outcomes):
        self.outcomes = outcomes

    def session(self, **_options):
        # The real driver takes options - database=NEO4J_DATABASE among them.
        return _Session(self.outcomes)

    def close(self):
        pass


def test_a_dropped_connection_is_reconnected_once_and_the_query_answered(monkeypatch):
    connection, attempts = detached_connection(monkeypatch, connect_result=True)
    outcomes = [ServiceUnavailable("connection dropped"), [_Record({"n": 1})]]
    connection.driver = _Driver(outcomes)

    def reconnect():
        attempts.append(1)
        connection.driver = _Driver(outcomes)
        return True

    monkeypatch.setattr(connection, "connect", reconnect)

    assert connection.execute_query("RETURN 1 AS n") == [{"n": 1}]
    assert len(attempts) == 1


def test_a_query_the_server_rejects_is_not_reported_as_an_outage(monkeypatch):
    # A bug in a query must surface as the bug, not as "try again later".
    connection, attempts = detached_connection(monkeypatch, connect_result=True)
    connection.driver = _Driver([ValueError("bad query")])

    with pytest.raises(ValueError):
        connection.execute_query("NOT CYPHER")
    assert attempts == []


# ── Routes that need the graph ──────────────────────────────────────────────
@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/api/progress/update", {"concept": "loop_boundaries", "score": 3, "total_questions": 4}),
        ("get", "/api/progress/me", None),
        ("get", "/api/progress/me/mastery", None),
        ("get", "/api/progress/me/curriculum", None),
        ("get", "/api/progress/me/learning-path?concept=loop_boundaries", None),
        ("get", "/api/games/me", None),
    ],
)
def test_a_route_that_needs_the_graph_answers_503(client, graph_down, method, path, body):
    response = getattr(client, method)(path, json=body) if body else getattr(client, method)(path)

    assert response.status_code == 503
    assert "nothing was read or saved" in response.json()["detail"]


def test_a_game_round_that_cannot_be_stored_is_not_reported_as_stored(graph_down):
    # A 200 told the engine the round was kept, so it had no reason to resend it.
    with pytest.raises(GraphUnavailable):
        game_summary_service.record_game_summary(
            "student-1", {"concept_tag": "loop_boundaries", "game_session_id": "round-1"}
        )


def test_lesson_timing_that_could_not_be_recorded_says_so(graph_down):
    assert progress_service.record_lesson_opened("student-1", "loop_boundaries")["success"] is False


# ── Lessons ─────────────────────────────────────────────────────────────────
def capture_prompt(monkeypatch):
    prompts = []

    def fake_generate(prompt):
        prompts.append(prompt)
        return LESSON_JSON

    monkeypatch.setattr(lesson_service, "generate", fake_generate)
    return prompts


def test_a_lesson_written_while_the_graph_is_down_says_what_it_lacked(monkeypatch, graph_down):
    prompts = capture_prompt(monkeypatch)

    def search_unreachable(*_args, **_kwargs):
        raise GraphUnavailable("down for this test")

    monkeypatch.setattr(rag_service, "search", search_unreachable)
    monkeypatch.setattr(rag_service, "search_with_prerequisites", search_unreachable)

    lesson = lesson_service.generate_real_lesson(
        "student-1", "OFF_BY_ONE_LOOP_BOUNDARY", "for (int i = 0; i <= n; i++)", 3, "loop_boundaries"
    )

    assert lesson["grounding"] == {"syllabus_notes": "unavailable", "student_record": "unavailable"}
    [prompt] = prompts
    # Not "this is the first time they are being taught it", which it may not be.
    assert "could not be read" in prompt
    assert "first time they are being taught" not in prompt
    assert "No syllabus notes could be retrieved" in prompt


def test_a_grounded_lesson_is_cached_and_an_ungrounded_one_is_not(monkeypatch):
    capture_prompt(monkeypatch)
    queries = []

    def fake_query(query, parameters=None):
        queries.append((query, parameters or {}))
        return []

    monkeypatch.setattr(neo4j_connection.neo4j_db, "execute_query", fake_query)

    def cache_writes():
        return [params for query, params in queries if "MERGE (l:Lesson {key: $key})" in query]

    monkeypatch.setattr(rag_service, "search", lambda *_a, **_k: [{"text": "Loops stop at n - 1.", "source": "loop_boundaries.txt"}])
    monkeypatch.setattr(rag_service, "search_with_prerequisites", lambda *_a, **_k: [{"text": "Loops stop at n - 1.", "source": "loop_boundaries.txt"}])
    grounded = lesson_service.generate_real_lesson("student-1", "OFF_BY_ONE_LOOP_BOUNDARY", "x", 3, "loop_boundaries")
    assert grounded["grounding"] == {"syllabus_notes": "found", "student_record": "read"}
    assert len(cache_writes()) == 1
    assert cache_writes()[0]["properties"]["syllabus_notes"] == "found"

    monkeypatch.setattr(rag_service, "search", lambda *_a, **_k: [])
    monkeypatch.setattr(rag_service, "search_with_prerequisites", lambda *_a, **_k: [])
    ungrounded = lesson_service.generate_real_lesson(
        "student-1", "OFF_BY_ONE_LOOP_BOUNDARY", "x", 3, "loop_boundaries", force_regenerate=True
    )
    assert ungrounded["grounding"]["syllabus_notes"] == "none_found"
    assert len(cache_writes()) == 1


# ── The language model's daily limit ────────────────────────────────────────
def test_a_quota_error_from_gemini_is_its_own_failure(monkeypatch):
    error = genai_errors.ClientError(
        429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded"}}
    )

    class Models:
        def generate_content(self, **_kwargs):
            raise error

    class Client:
        models = Models()

    monkeypatch.setattr(llm, "get_client", lambda: Client())

    with pytest.raises(LLMQuotaExhausted):
        llm.generate("anything")


def test_the_daily_limit_reaches_the_student_as_a_429_with_a_plain_message(client, monkeypatch):
    def exhausted(**_kwargs):
        raise LLMQuotaExhausted("429 RESOURCE_EXHAUSTED quotaId=GenerateRequestsPerDay")

    monkeypatch.setattr(struggle_api, "generate_real_lesson", exhausted)
    monkeypatch.setattr(quiz_api, "generate_validation_quiz", exhausted)

    lesson = client.post(
        "/api/struggle/detect",
        json={"error_type": "OFF_BY_ONE_LOOP_BOUNDARY", "concept_tag": "loop_boundaries", "error_count": 3},
    )
    quiz = client.post("/api/quiz/generate", json={"error_type": "OFF_BY_ONE_LOOP_BOUNDARY"})

    for response in (lesson, quiz):
        assert response.status_code == 429
        assert response.json()["detail"] == DAILY_LIMIT_MESSAGE


def test_other_generation_failures_do_not_show_the_provider_error_text(client, monkeypatch):
    def failed(**_kwargs):
        raise LLMUnavailable("500 INTERNAL request-id=abc123 upstream said no")

    monkeypatch.setattr(struggle_api, "generate_real_lesson", failed)

    response = client.post(
        "/api/struggle/detect",
        json={"error_type": "OFF_BY_ONE_LOOP_BOUNDARY", "concept_tag": "loop_boundaries", "error_count": 3},
    )

    assert response.status_code == 503
    assert "abc123" not in response.json()["detail"]
