"""Notes from the lesson's own concept, citations that point at real notes, and quiz quality you can see.

NFR-03 asks for lessons grounded in the syllabus. Three things stood between the
code and that claim: retrieval searched the whole syllabus, so a lesson could be
built from another concept's notes; nothing recorded which notes a lesson used;
and nothing recorded how close a quiz came to failing its own checks.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import vector_index  # noqa: E402
from app.dev_tools import content_report  # noqa: E402
from app.services import content_store, learning_path_service, lesson_service, progress_service, quiz_service, rag_service  # noqa: E402

NOTES = [
    {"text": "An array of length n ends at index n - 1.", "source": "array_indexing.txt", "concept": "array_indexing"},
    {"text": "A loop's counter must reach its bound.", "source": "loop_control.txt", "concept": "loop_control"},
]


# ── Retrieval ───────────────────────────────────────────────────────────────
def test_notes_are_searched_within_the_concept_and_numbered(monkeypatch):
    concepts = []

    def whole_syllabus(*_args, **_kwargs):
        raise AssertionError("searched every concept")

    def within(query, concept, k=3):
        concepts.append(concept)
        return NOTES

    monkeypatch.setattr(rag_service, "search", whole_syllabus)
    monkeypatch.setattr(rag_service, "search_with_prerequisites", within)

    notes = rag_service.retrieve_notes("ARRAY_LENGTH_INDEX_MISUSE", concept="array_indexing")

    assert concepts == ["array_indexing"]
    assert [chunk["id"] for chunk in notes.chunks] == ["N1", "N2"]
    assert "[N1] (notes on array_indexing)" in notes.text


def test_nothing_in_the_concept_is_not_filled_from_another_concept(monkeypatch):
    queries = []

    def fake_query(query, parameters=None):
        queries.append(query)
        return []

    monkeypatch.setattr(vector_index, "_embed", lambda _query: [0.0])
    monkeypatch.setattr(vector_index.neo4j_db, "execute_query", fake_query)

    assert vector_index.search_with_prerequisites("switch fall-through", "switch_statements") == []
    # One query: the filtered one. There used to be a second, unfiltered search.
    assert len(queries) == 1
    assert "chunk_concept.name = $target" in queries[0]


# ── Citations ───────────────────────────────────────────────────────────────
@pytest.fixture
def lesson_setup(monkeypatch):
    prompts, saved = [], []
    reply = {"sources": []}

    def fake_generate(prompt):
        prompts.append(prompt)
        return json.dumps(
            {
                "issue": "Reading one past the end",
                "explanation": "The last index is length - 1.",
                "incorrectCode": "a[a.length]",
                "correctCode": "a[a.length - 1]",
                "sources": reply["sources"],
            }
        )

    monkeypatch.setattr(lesson_service, "generate", fake_generate)
    monkeypatch.setattr(progress_service, "get_concept_mastery", lambda *_a: None)
    monkeypatch.setattr(learning_path_service, "unmastered_prerequisites", lambda *_a: [])
    monkeypatch.setattr(rag_service, "search_with_prerequisites", lambda *_a, **_k: NOTES)
    monkeypatch.setattr(content_store, "find_lesson", lambda _key: None)
    monkeypatch.setattr(content_store, "save_lesson", lambda key, properties: saved.append(properties))
    monkeypatch.setattr(content_store, "record_taught", lambda *_a: None)
    return prompts, saved, reply


def teach():
    return lesson_service.lesson_for("ana", "ARRAY_LENGTH_INDEX_MISUSE", "a[a.length]", "array_indexing", "Needs Simple Basics")


def test_the_prompt_numbers_the_notes_and_asks_which_were_used(lesson_setup):
    prompts, _, _ = lesson_setup
    teach()

    [prompt] = prompts
    assert "[N1] (notes on array_indexing)" in prompt
    assert "[N2] (notes on loop_control)" in prompt
    assert '"sources"' in prompt


def test_only_citations_to_notes_the_lesson_was_given_are_kept(lesson_setup):
    _, saved, reply = lesson_setup
    reply["sources"] = ["N2", "N9", "N2", 3]

    lesson = teach()

    assert lesson["sources"] == [{"id": "N2", "concept": "loop_control", "source": "loop_control.txt"}]
    assert json.loads(saved[0]["sources_json"]) == lesson["sources"]


def test_a_lesson_that_cites_nothing_is_shown_as_citing_nothing(lesson_setup):
    lesson = teach()
    assert lesson["sources"] == []


# ── Quiz quality ────────────────────────────────────────────────────────────
def test_a_stored_quiz_records_how_many_questions_could_be_marked(monkeypatch):
    stored = {}
    candidates = [
        {"question": f"Question {n}?", "options": [f"A{n}", f"B{n}", f"C{n}", f"D{n}"], "correct_answer": f"B{n}", "explanation": "."}
        for n in range(10)
    ]
    candidates[4]["correct_answer"] = "not an option"

    monkeypatch.setattr(quiz_service, "generate", lambda _prompt: json.dumps(candidates))
    monkeypatch.setattr(content_store, "lesson_taught", lambda *_a: {"key": "lesson_x", "issue": "i", "explanation": "e"})
    monkeypatch.setattr(content_store, "quiz_variants", lambda *_a: [])
    monkeypatch.setattr(content_store, "record_quizzed", lambda *_a, **_k: None)

    def save_quiz(lesson_key, variant, questions, generation_ms, candidates=None):
        stored.update(kept=len(questions), candidates=candidates)
        return "lesson_x_quiz1"

    monkeypatch.setattr(content_store, "save_quiz", save_quiz)

    quiz_service.generate_validation_quiz("ana", "ARRAY_LENGTH_INDEX_MISUSE")

    assert stored == {"kept": 8, "candidates": 9}


def test_the_report_gives_the_citation_count_and_markable_questions():
    report = content_report.summarise(
        [{"sources_json": '[{"id": "N1"}]'}, {"sources_json": "[]"}, {}],
        [{"candidates": 9}, {"candidates": 10}],
    )

    assert report["citing_lessons"] == 1
    assert report["markable_questions_median"] == 9.5
