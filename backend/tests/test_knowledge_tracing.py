"""Tests for Bayesian Knowledge Tracing.

These pin the properties that make BKT worth having over the average it
replaced. If any of them stops holding, the model has silently become a
gradebook again with extra steps.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.knowledge_tracing import (  # noqa: E402
    MASTERY_THRESHOLD,
    PRIOR_KNOWN,
    PROBABILITY_OF_GUESS,
    estimate,
    predicted_correct,
    trace,
)


def quiz(score: int, total: int = 4) -> dict:
    return {"score": score, "total": total}


# ── The reason this replaced an average ─────────────────────────────────────
def test_order_matters_which_is_the_whole_point():
    """40 -> 55 -> 85 and 85 -> 55 -> 40 average identically. They are not the same.

    One student is learning and the other is losing it, and an average cannot
    tell them apart. BKT can, because every observation updates a belief rather
    than joining a pool.
    """
    improving = trace([quiz(1), quiz(2), quiz(4)])
    declining = trace([quiz(4), quiz(2), quiz(1)])

    assert improving > declining


def test_a_perfect_run_reaches_mastery():
    result = estimate("loop_boundaries", [quiz(4), quiz(4), quiz(4)])
    assert result.probability_known >= MASTERY_THRESHOLD
    assert result.mastered is True


def test_consistent_failure_drives_the_belief_down():
    assert trace([quiz(0), quiz(0), quiz(0)]) < PRIOR_KNOWN


def test_no_attempts_means_the_prior_and_not_mastered():
    result = estimate("arrays", [])
    assert result.probability_known == PRIOR_KNOWN
    assert result.observations == 0
    # The prior is 0.25, which is below the threshold anyway - but a concept
    # with no evidence must never be called mastered regardless of how the
    # prior is later tuned.
    assert result.mastered is False


# ── The prediction FR-08 actually asks for ──────────────────────────────────
def test_prediction_is_not_the_same_number_as_belief():
    """Knowing nothing still scores 25% on four-option questions."""
    assert predicted_correct(0.0) == PROBABILITY_OF_GUESS
    # And knowing everything still slips sometimes, so it never reaches 1.0.
    assert predicted_correct(1.0) < 1.0


def test_prediction_rises_with_belief():
    assert predicted_correct(0.9) > predicted_correct(0.5) > predicted_correct(0.1)


# ── Every question is evidence, not every quiz ──────────────────────────────
def test_each_question_counts_as_its_own_observation():
    """One 4-question quiz is four observations, not one.

    Collapsing a quiz into a single "75%" throws away most of the evidence the
    student produced.
    """
    assert estimate("c", [quiz(3, 4)]).observations == 4
    assert estimate("c", [quiz(3, 4), quiz(2, 4)]).observations == 8


def test_a_bigger_quiz_moves_the_belief_further():
    assert trace([quiz(8, 8)]) > trace([quiz(2, 2)])


# ── Robustness, because these come from a database ──────────────────────────
def test_attempts_with_no_questions_are_skipped_not_crashed():
    assert trace([{"score": 0, "total": 0}]) == PRIOR_KNOWN
    assert trace([{"score": None, "total": None}]) == PRIOR_KNOWN


def test_a_score_above_total_is_clamped():
    # Nothing should write this, but a stored 5/4 must not produce a belief
    # above 1.0 and poison every later update.
    result = trace([{"score": 5, "total": 4}])
    assert 0.0 <= result <= 1.0


def test_probability_stays_in_range_across_a_long_history():
    history = [quiz(i % 5, 4) for i in range(60)]
    assert 0.0 <= trace(history) <= 1.0
