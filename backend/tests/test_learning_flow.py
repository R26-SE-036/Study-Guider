"""One meaning of mastered, and a list of what is due for review.

The learning path cleared a prerequisite on any single attempt at 50% or more,
while the curriculum map and the lesson's mastery band used knowledge tracing.
So the lesson and the progress page could disagree about the same student.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.neo4j_connection import neo4j_db  # noqa: E402
from app.services import learning_path_service, progress_service  # noqa: E402

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


def fake_graph(monkeypatch, attempts, path_rows):
    queries = []

    def execute_query(query, parameters=None):
        queries.append(query)
        if "PREREQUISITE_OF" in query:
            return path_rows
        return attempts

    monkeypatch.setattr(neo4j_db, "execute_query", execute_query)
    return queries


# ── Learning path ───────────────────────────────────────────────────────────
def test_one_half_right_quiz_no_longer_clears_a_prerequisite(monkeypatch):
    attempts = [
        # 4/8: the old rule called this mastered; knowledge tracing does not.
        {"concept": "loop_boundaries", "score": 4, "total": 8, "percentage": 50.0, "timestamp": "2026-09-10T10:00:00+00:00"},
        # Three perfect quizzes: knowledge tracing believes this one.
        *[
            {"concept": "assignment_logic", "score": 8, "total": 8, "percentage": 100.0, "timestamp": f"2026-09-0{day}T10:00:00+00:00"}
            for day in (1, 2, 3)
        ],
    ]
    paths = [
        {"concept": "loop_boundaries", "steps_away": 1},
        {"concept": "assignment_logic", "steps_away": 2},
        {"concept": "loop_boundaries", "steps_away": 3},
    ]
    queries = fake_graph(monkeypatch, attempts, paths)

    gaps = learning_path_service.unmastered_prerequisites("ana", "array_indexing")

    assert gaps == [{"concept": "loop_boundaries", "steps_away": 1}]
    [path_query] = [q for q in queries if "PREREQUISITE_OF" in q]
    assert "percentage" not in path_query


def test_the_learning_path_and_the_curriculum_agree(monkeypatch):
    attempts = [
        {"concept": "boolean_logic", "score": 4, "total": 8, "percentage": 50.0, "timestamp": "2026-09-10T10:00:00+00:00"},
    ]
    fake_graph(monkeypatch, attempts, [{"concept": "boolean_logic", "steps_away": 1}])

    gaps = {gap["concept"] for gap in learning_path_service.unmastered_prerequisites("ana", "conditional_logic")}
    curriculum = {c["concept"]: c for c in progress_service.get_curriculum("ana")["data"]["concepts"]}

    assert "boolean_logic" in gaps
    assert curriculum["boolean_logic"]["state"] == "in_progress"


# ── Review ──────────────────────────────────────────────────────────────────
def estimate(concept, known, mastered, days_ago):
    return {
        "concept": concept,
        "probability_known": known,
        "mastered": mastered,
        "last_attempt": (NOW - timedelta(days=days_ago)).isoformat(),
    }


def test_what_is_due_and_in_what_order():
    due = progress_service.review_due(
        [
            estimate("loop_control", 0.60, False, 3),
            estimate("array_indexing", 0.20, False, 5),
            estimate("switch_statements", 0.40, False, 0),  # quizzed today
            estimate("boolean_logic", 0.97, True, 20),
            estimate("control_flow", 0.98, True, 30),
            estimate("assignment_logic", 0.99, True, 3),  # known, practised recently
        ],
        now=NOW,
    )

    assert [(item["concept"], item["reason"]) for item in due] == [
        ("array_indexing", "not_yet_known"),
        ("loop_control", "not_yet_known"),
        ("control_flow", "not_practised_recently"),
        ("boolean_logic", "not_practised_recently"),
    ]
    assert due[0]["days_since_practice"] == 5


def test_an_unreadable_date_leans_towards_review_only_when_not_known():
    due = progress_service.review_due(
        [
            {"concept": "loop_control", "probability_known": 0.5, "mastered": False, "last_attempt": None},
            {"concept": "control_flow", "probability_known": 0.99, "mastered": True, "last_attempt": "not a date"},
        ],
        now=NOW,
    )
    assert [item["concept"] for item in due] == ["loop_control"]


def test_the_curriculum_carries_the_review_list(monkeypatch):
    attempts = [
        {"concept": "loop_control", "score": 3, "total": 8, "percentage": 37.5, "timestamp": "2026-09-01T10:00:00+00:00"},
    ]
    fake_graph(monkeypatch, attempts, [])

    data = progress_service.get_curriculum("ana")["data"]

    assert [item["concept"] for item in data["review_due"]] == ["loop_control"]


def test_estimates_record_the_newest_attempt(monkeypatch):
    attempts = [
        {"concept": "loop_control", "score": 2, "total": 8, "percentage": 25.0, "timestamp": "2026-09-01T10:00:00+00:00"},
        {"concept": "loop_control", "score": 6, "total": 8, "percentage": 75.0, "timestamp": "2026-09-09T10:00:00+00:00"},
    ]
    fake_graph(monkeypatch, attempts, [])

    [only] = progress_service.get_mastery_estimates("ana")["data"]

    assert only["last_attempt"] == "2026-09-09T10:00:00+00:00"


def test_traversal_bound_reaches_every_prerequisite():
    """The Cypher bound must be at least the farthest any prerequisite sits.

    It was a hand-set 4 while boolean_logic sat five steps before
    array_indexing, so it silently dropped out of that learning path.
    """
    from collections import deque

    from app.core.concepts import PREREQUISITE_EDGES

    parents: dict = {}
    for prereq, dependent in PREREQUISITE_EDGES:
        parents.setdefault(dependent, []).append(prereq)

    farthest = 0
    for target in parents:
        distance = {target: 0}
        queue = deque([target])
        while queue:
            node = queue.popleft()
            for prereq in parents.get(node, []):
                if prereq not in distance:
                    distance[prereq] = distance[node] + 1
                    queue.append(prereq)
        farthest = max(farthest, *distance.values())

    assert farthest == 5
    assert learning_path_service.MAX_PREREQUISITE_DEPTH >= farthest
