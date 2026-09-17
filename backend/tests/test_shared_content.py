"""Lessons and quizzes written once and shared, without saying anything untrue.

The free Gemini tier allows twenty generations a day for the whole project. A
lesson per student and a new quiz per browser session spent that on ten
students. These tests hold the sharing to its two conditions: a student only
ever gets content written for their own situation, and a stored item is served
instead of a new generation whenever one fits.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.dev_tools import content_report, pregenerate_content  # noqa: E402
from app.services import content_store, learning_path_service, lesson_service, progress_service, quiz_service, rag_service  # noqa: E402
from app.services.llm import LLMUnavailable  # noqa: E402

LESSON_JSON = json.dumps(
    {
        "issue": "The loop runs once too often",
        "explanation": "An array of length n has its last element at n - 1.",
        "incorrectCode": "for (int i = 0; i <= n; i++)",
        "correctCode": "for (int i = 0; i < n; i++)",
        "hint": "Where does the loop stop?",
    }
)


def questions(count: int, *, options: int = 4, prefix: str = "Question") -> list[dict]:
    return [
        {
            "question": f"{prefix} {number}?",
            "options": [f"Option {letter}{number}" for letter in "ABCD"[:options]],
            "correct_answer": f"Option B{number}",
            "explanation": "Because.",
        }
        for number in range(count)
    ]


class FakeStore:
    """content_store's functions, over dictionaries."""

    def __init__(self):
        self.lessons: dict[str, dict] = {}
        self.taught: dict[tuple[str, str], str] = {}
        self.quizzes: dict[str, list[dict]] = {}
        self.served: dict[tuple[str, str], str] = {}

    def install(self, monkeypatch):
        for name in ("find_lesson", "save_lesson", "record_taught", "lesson_taught", "quiz_variants", "save_quiz", "record_quizzed"):
            monkeypatch.setattr(content_store, name, getattr(self, name))

    def find_lesson(self, key):
        return self.lessons.get(key)

    def save_lesson(self, key, properties):
        self.lessons[key] = {**properties, "key": key}

    def record_taught(self, student_id, key, error_type):
        self.taught[(student_id, error_type)] = key

    def lesson_taught(self, student_id, error_type):
        key = self.taught.get((student_id, error_type))
        return self.lessons.get(key) if key else None

    def quiz_variants(self, lesson_key, student_id):
        return [
            {**quiz, "served_at": self.served.get((student_id, quiz["key"]))}
            for quiz in self.quizzes.get(lesson_key, [])
        ]

    def save_quiz(self, lesson_key, variant, quiz_questions, generation_ms, candidates=None):
        key = f"{lesson_key}_quiz{variant}"
        self.quizzes.setdefault(lesson_key, []).append({"key": key, "variant": variant, "questions": quiz_questions})
        return key

    def record_quizzed(self, student_id, quiz_key, *, from_store):
        self.served[(student_id, quiz_key)] = datetime.now(timezone.utc).isoformat()


@pytest.fixture
def store(monkeypatch):
    fake = FakeStore()
    fake.install(monkeypatch)
    return fake


@pytest.fixture
def graph(monkeypatch):
    """The student's record, set per student by the test."""
    records = {}

    def mastery(student_id, _concept):
        return records.get(student_id, {}).get("mastery")

    def gaps(student_id, _concept):
        return [{"concept": name} for name in records.get(student_id, {}).get("gaps", [])]

    monkeypatch.setattr(progress_service, "get_concept_mastery", mastery)
    monkeypatch.setattr(learning_path_service, "unmastered_prerequisites", gaps)
    monkeypatch.setattr(rag_service, "search", lambda *_a, **_k: [{"text": "Loops stop at n - 1."}])
    monkeypatch.setattr(rag_service, "search_with_prerequisites", lambda *_a, **_k: [{"text": "Loops stop at n - 1."}])
    return records


@pytest.fixture
def lesson_calls(monkeypatch):
    prompts = []

    def fake_generate(prompt):
        prompts.append(prompt)
        return LESSON_JSON

    monkeypatch.setattr(lesson_service, "generate", fake_generate)
    return prompts


@pytest.fixture
def quiz_calls(monkeypatch):
    prompts = []

    def fake_generate(prompt):
        prompts.append(prompt)
        return json.dumps(questions(10, prefix=f"Version {len(prompts)} question"))

    monkeypatch.setattr(quiz_service, "generate", fake_generate)
    return prompts


def teach(student_id: str, state: str = "Needs Simple Basics") -> dict:
    return lesson_service.lesson_for(student_id, "OFF_BY_ONE_LOOP_BOUNDARY", "for (...)", "loop_boundaries", state)


# ── Lessons ─────────────────────────────────────────────────────────────────
def test_two_students_in_the_same_situation_share_one_lesson(store, graph, lesson_calls):
    first = teach("ana")
    second = teach("ben")

    assert len(lesson_calls) == 1
    assert first["cached"] is False and second["cached"] is True
    assert second["explanation"] == first["explanation"]
    assert store.taught[("ana", "OFF_BY_ONE_LOOP_BOUNDARY")] == store.taught[("ben", "OFF_BY_ONE_LOOP_BOUNDARY")]


def test_a_different_situation_gets_its_own_lesson(store, graph, lesson_calls):
    graph["ben"] = {"mastery": {"attempts": 2, "mastered": False, "probability_known": 0.3}, "gaps": ["loop_control"]}

    teach("ana")
    ben = teach("ben")

    assert len(lesson_calls) == 2
    assert ben["unmet_prerequisites"] == ["loop_control"]


def test_the_prompt_describes_a_band_not_one_students_numbers(store, graph, lesson_calls):
    # "3 attempts, average 55%" in a shared lesson would be repeated to the next
    # student in the band, who had different numbers.
    graph["ana"] = {"mastery": {"attempts": 3, "average_percentage": 55.0, "mastered": False, "probability_known": 0.3}}

    teach("ana")

    [prompt] = lesson_calls
    assert "still find it hard" in prompt
    assert "55" not in prompt and "3 quiz attempt" not in prompt


def test_an_unreadable_record_is_neither_served_from_the_store_nor_added_to_it(store, graph, lesson_calls, monkeypatch):
    teach("ana")

    def unreadable(*_args):
        raise RuntimeError("graph unreachable")

    monkeypatch.setattr(progress_service, "get_concept_mastery", unreadable)
    lesson = teach("ben")

    assert len(lesson_calls) == 2
    assert lesson["cached"] is False
    assert lesson["grounding"]["student_record"] == "unavailable"
    assert len(store.lessons) == 1


def test_a_different_cognitive_state_gets_its_own_lesson(store, graph, lesson_calls):
    teach("ana", "Needs Simple Basics")
    teach("ben", "Minor Syntax Error")
    assert len(lesson_calls) == 2


# ── Quizzes ─────────────────────────────────────────────────────────────────
def test_a_quiz_is_eight_questions_written_from_the_lesson(store, graph, lesson_calls, quiz_calls):
    teach("ana")

    quiz = quiz_service.generate_validation_quiz("ana", "OFF_BY_ONE_LOOP_BOUNDARY")

    assert len(quiz) == 8
    [prompt] = quiz_calls
    assert "An array of length n has its last element at n - 1." in prompt


def test_questions_that_are_unfair_to_ask_are_dropped():
    candidates = questions(12)
    candidates[1] = {**candidates[0]}                                        # asked twice
    candidates[2]["options"] = ["Same", "same", "`Same`", "Other"]           # options that read the same
    candidates[3]["options"] = candidates[3]["options"][:3]                  # only three options

    kept = quiz_service.select_questions(candidates)

    assert len(kept) == 8
    assert len({q["question"] for q in kept}) == 8
    assert candidates[2] not in kept and candidates[3] not in kept


def test_fewer_than_eight_usable_questions_is_a_failure_not_a_short_quiz():
    with pytest.raises(LLMUnavailable):
        quiz_service.select_questions(questions(7))


def test_another_student_in_the_same_situation_gets_the_stored_quiz(store, graph, lesson_calls, quiz_calls):
    teach("ana")
    teach("ben")
    ana = quiz_service.generate_validation_quiz("ana", "OFF_BY_ONE_LOOP_BOUNDARY")
    ben = quiz_service.generate_validation_quiz("ben", "OFF_BY_ONE_LOOP_BOUNDARY")

    assert len(quiz_calls) == 1
    assert ben == ana


def test_coming_back_within_two_hours_gets_the_same_quiz(store, graph, lesson_calls, quiz_calls):
    teach("ana")
    first = quiz_service.generate_validation_quiz("ana", "OFF_BY_ONE_LOOP_BOUNDARY")
    again = quiz_service.generate_validation_quiz("ana", "OFF_BY_ONE_LOOP_BOUNDARY")

    assert again == first
    assert len(quiz_calls) == 1


def long_ago(store, student_id):
    earlier = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    for key in list(store.served):
        if key[0] == student_id:
            store.served[key] = earlier


def test_a_retake_later_gets_a_version_not_seen_before(store, graph, lesson_calls, quiz_calls):
    teach("ana")
    first = quiz_service.generate_validation_quiz("ana", "OFF_BY_ONE_LOOP_BOUNDARY")
    long_ago(store, "ana")

    retake = quiz_service.generate_validation_quiz("ana", "OFF_BY_ONE_LOOP_BOUNDARY")

    assert retake != first
    assert len(quiz_calls) == 2


def test_once_there_are_enough_versions_the_one_seen_longest_ago_is_reused(store, graph, lesson_calls, quiz_calls):
    teach("ana")
    seen = []
    for _ in range(content_store.MAX_QUIZ_VARIANTS):
        seen.append(quiz_service.generate_validation_quiz("ana", "OFF_BY_ONE_LOOP_BOUNDARY"))
        long_ago(store, "ana")
    # Make the first version the one seen longest ago.
    first_key = next(key for key in store.served if key[1].endswith("_quiz1"))
    store.served[first_key] = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()

    reused = quiz_service.generate_validation_quiz("ana", "OFF_BY_ONE_LOOP_BOUNDARY")

    assert len(quiz_calls) == content_store.MAX_QUIZ_VARIANTS
    assert reused == seen[0]


def test_a_quiz_with_no_lesson_behind_it_is_written_from_the_mistake_and_not_kept(store, graph, quiz_calls):
    quiz = quiz_service.generate_validation_quiz("ana", "OFF_BY_ONE_LOOP_BOUNDARY", "for (...)")

    assert len(quiz) == 8
    assert store.quizzes == {}
    assert "OFF_BY_ONE_LOOP_BOUNDARY" in quiz_calls[0]


# ── Pregeneration and the report ───────────────────────────────────────────
def test_pregeneration_stops_at_its_budget_and_a_rerun_spends_nothing_twice(store, graph, lesson_calls, quiz_calls):
    types = ["OFF_BY_ONE_LOOP_BOUNDARY"]
    first = pregenerate_content.run(3, types, log=lambda _line: None)

    assert first["calls"] == 3
    assert first["stopped"] == "budget"

    second = pregenerate_content.run(10, types, log=lambda _line: None)
    # Three states x (lesson + quiz) = six calls in all; three were already spent.
    assert second["calls"] == 3
    assert second["stopped"] == "done"


def test_the_report_counts_what_the_store_saved():
    report = content_report.summarise(
        [
            {"error_type": "OFF_BY_ONE_LOOP_BOUNDARY", "cognitive_state": "Needs Simple Basics", "situation": "read|none|", "generation_ms": 20000, "hits": 4},
            {"error_type": "OFF_BY_ONE_LOOP_BOUNDARY", "cognitive_state": "Minor Syntax Error", "situation": "read|early|loop_control", "generation_ms": 30000, "hits": 1},
        ],
        [{"key": "q1", "generation_ms": 15000, "hits": 2}],
    )

    assert report["lesson_hits"] == 5
    assert report["lesson_generation"]["median_ms"] == 25000
    assert report["quiz_hits"] == 2
    assert report["new_student_coverage"]["covered"] == 1
