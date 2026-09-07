"""Tests for turning a model's quiz JSON into something markable.

The bug these exist for: the endpoint answered 503 "No usable questions were
generated" while the model was returning four perfectly good questions. The
model had written `"correct_answer": "B"` where the options are `"A) ..."`,
`"B) ..."`, and an exact string comparison dropped every question.

It was intermittent, which is what made it worth pinning. Asked about a bare
error type the model replies with the full option text and everything works;
given a code snippet in the same prompt it replies with a bare letter and the
whole quiz fails. Same code, same model, different day.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.llm import LLMUnavailable  # noqa: E402
from app.services.quiz_service import _normalise, _resolve_answer  # noqa: E402

LETTERED = [
    "A) for (int i = 0; i <= n; i++)",
    "B) for (int i = 0; i < n; i++)",
    "C) for (int i = 1; i <= n; i++)",
    "D) for (int i = 0; i < n - 1; i++)",
]
PLAIN = ["Zero", "One", "Two", "Three"]


# ── The regression ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("answer", ["B", "b", "B)", "(B)", "B.", " B ", "B) for (int i = 0; i < n; i++)"])
def test_a_letter_resolves_to_its_option(answer):
    assert _resolve_answer(answer, LETTERED) == LETTERED[1]


def test_full_option_text_still_resolves():
    assert _resolve_answer(LETTERED[1], LETTERED) == LETTERED[1]
    assert _resolve_answer("two", PLAIN) == "Two"


@pytest.mark.parametrize("answer,expected", [("2", "One"), ("1", "Zero"), ("4", "Three")])
def test_a_number_is_read_as_1_based(answer, expected):
    # A model writing "3" for a four-option question means the third, not the
    # fourth. 0-based is only tried when 1-based cannot fit.
    assert _resolve_answer(answer, PLAIN) == expected


@pytest.mark.parametrize("answer", ["Z", "9", "", None, "not an option at all", "   "])
def test_an_answer_that_refers_to_nothing_is_rejected(answer):
    assert _resolve_answer(answer, PLAIN) is None


# ── What the caller gets ─────────────────────────────────────────────────────
def test_normalise_rewrites_the_answer_to_the_option_text():
    """The web app marks by comparing the clicked option against this string.

    Storing the model's bare "B" would mark every answer wrong even though the
    question parsed fine - a subtler failure than the 503, and worse, because
    the student sees a score rather than an error.
    """
    questions = _normalise(
        [{"question": "Which loop is correct?", "options": LETTERED, "correct_answer": "B"}]
    )
    assert questions[0]["correct_answer"] == LETTERED[1]
    assert questions[0]["correct_answer"] in questions[0]["options"]


def test_alternative_field_names_are_accepted():
    questions = _normalise(
        {"questions": [{"question": "Pick one", "choices": PLAIN, "answer": "C"}]}
    )
    assert questions[0]["correct_answer"] == "Two"


def test_unmarkable_questions_are_dropped_not_guessed():
    questions = _normalise(
        [
            {"question": "Good", "options": PLAIN, "correct_answer": "A"},
            {"question": "No answer", "options": PLAIN},
            {"question": "Answer refers to nothing", "options": PLAIN, "correct_answer": "Z"},
            {"question": "One option", "options": ["only"], "correct_answer": "only"},
        ]
    )
    assert len(questions) == 1
    assert questions[0]["question"] == "Good"


def test_nothing_usable_is_an_error_not_an_empty_quiz():
    # An empty quiz would be scored 0/0 and resolve the trigger, marking a
    # concept mastered on the strength of no questions at all.
    with pytest.raises(LLMUnavailable):
        _normalise([{"question": "Bad", "options": PLAIN, "correct_answer": "Z"}])

    with pytest.raises(LLMUnavailable):
        _normalise([])


# ── The second shape, found by sampling generations rather than by reading ───
# The model also writes "A `for (...)`" - a letter, a SPACE, then the text -
# while the options carry no letter at all. Comparing both sides with any label
# stripped is what covers every combination of who is carrying the label.

UNLABELLED_CODE = [
    "`for (int i = 1; i < marks.length; i++)`",
    "`for (int i = 0; i < marks.length; i++)`",
]


def test_labelled_answer_against_unlabelled_options():
    assert _resolve_answer("A `for (int i = 0; i < marks.length; i++)`", UNLABELLED_CODE) == (
        UNLABELLED_CODE[1]
    )


def test_backticks_are_presentational_not_a_different_answer():
    assert _resolve_answer("for (int i = 0; i < n; i++)", ["`for (int i = 0; i < n; i++)`"]) == (
        "`for (int i = 0; i < n; i++)`"
    )


def test_an_answer_starting_with_the_article_a_is_not_read_as_a_label():
    """"A loop that runs once" is an answer, not option A.

    Safe because the comparison strips both sides: the answer and the option it
    matches strip identically, so it pairs correctly either way.
    """
    options = ["A loop that runs once", "A loop that never ends"]
    assert _resolve_answer("A loop that never ends", options) == "A loop that never ends"
