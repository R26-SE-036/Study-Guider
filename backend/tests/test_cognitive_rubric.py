"""Tests for the cognitive-state rubric and the classifier that approximates it.

The rubric replaced ten handwritten rows and a RandomForest fitted on eight of
them. Two things need holding in place:

  * the rubric stays a complete, reachable decision list - a rule that can never
    fire is a rule nobody is maintaining, and R3/R6 exist only because a
    fall-through to "a slip" was found by comparing against those ten rows;
  * the service never answers with a hardcoded state again. `predict_cognitive_state`
    used to return "Needs Simple Basics" whenever the model was missing or threw,
    so a deployment with no model at all still looked like it was predicting.

Run:  python -m pytest tests/ -q      (from backend/)
"""

from __future__ import annotations

import itertools
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import cognitive_rubric as rubric  # noqa: E402
from app.services.cognitive_rubric import (  # noqa: E402
    COGNITIVE_STATES,
    COMPLEXITY_RANGE,
    ERROR_COUNT_RANGE,
    PAST_SCORE_RANGE,
    RULES,
    classify,
    explain,
)

ALL_INPUTS = list(
    itertools.product(
        range(ERROR_COUNT_RANGE[0], ERROR_COUNT_RANGE[1] + 1),
        range(COMPLEXITY_RANGE[0], COMPLEXITY_RANGE[1] + 1),
        range(PAST_SCORE_RANGE[0], PAST_SCORE_RANGE[1] + 1, 5),
    )
)


# ── The rubric ───────────────────────────────────────────────────────────────
def test_every_input_gets_a_state_the_prompt_understands():
    """lesson_service.py's prompt branches on these exact strings."""
    for errors, complexity, past in ALL_INPUTS:
        assert classify(errors, complexity, past) in COGNITIVE_STATES


def test_every_rule_is_reachable():
    """A rule that never fires is a rule nobody is maintaining."""
    fired = {explain(*inputs)[1] for inputs in ALL_INPUTS}
    unreachable = {rule_id for rule_id, _, _, _ in RULES} - fired
    assert not unreachable, f"these rules can never fire: {sorted(unreachable)}"


def test_classify_and_explain_never_disagree():
    """They read one list. This test is what keeps that true."""
    for inputs in ALL_INPUTS:
        assert classify(*inputs) == explain(*inputs)[0]


def test_repeated_errors_are_never_called_a_slip():
    """The hole the legacy comparison found.

    Four repeats of the same mistake used to fall through every rule to
    "Minor Syntax Error" for a mid-ability student on moderate code.
    """
    for errors, complexity, past in ALL_INPUTS:
        if errors >= 4:
            assert classify(errors, complexity, past) != rubric.MINOR_SYNTAX_ERROR, (
                f"{errors} repeats at complexity {complexity}, past {past} "
                "was labelled a slip"
            )


def test_simple_code_is_never_called_overload():
    """You cannot be cognitively overloaded by a snippet with no control flow."""
    for errors, past in itertools.product(range(1, 13), range(0, 101, 5)):
        for complexity in range(1, rubric.SIMPLE_CODE + 1):
            assert classify(errors, complexity, past) != rubric.HIGH_COGNITIVE_LOAD


def test_a_strong_student_with_one_error_is_a_slip():
    assert classify(1, 3, 90) == rubric.MINOR_SYNTAX_ERROR


def test_inputs_are_clamped_not_rejected():
    """Runtime values arrive from three services; none of them may crash this."""
    assert classify(-5, 0, -20) in COGNITIVE_STATES
    assert classify(999, 999, 999) in COGNITIVE_STATES
    assert classify(0, 1, 100) in COGNITIVE_STATES


@pytest.mark.parametrize("bad", [(1.7, 3.2, 90.5), ("2", "4", "80")])
def test_non_integer_inputs_are_coerced(bad):
    assert classify(*bad) in COGNITIVE_STATES


# ── The classifier that approximates it ──────────────────────────────────────
def test_model_reproduces_the_rubric():
    """Fidelity, which is the only thing this model's metric can mean.

    Not 100%: the model interpolates the rubric's step boundaries, which is why
    it is kept at all. A large drop means the pickle is stale - regenerate the
    dataset and retrain.
    """
    from app.services.ml_service import _bundle

    if _bundle is None:
        pytest.skip("no trained model; run python -m app.services.ml_model_trainer")

    import pandas as pd

    frame = pd.DataFrame(ALL_INPUTS, columns=["error_count", "complexity_score", "past_score"])
    predicted = _bundle["model"].predict(frame[_bundle["feature_columns"]])
    expected = [classify(*inputs) for inputs in ALL_INPUTS]

    agreement = sum(p == e for p, e in zip(predicted, expected)) / len(expected)
    assert agreement > 0.90, f"model agrees with the rubric only {agreement:.1%} of the time"


def test_prediction_falls_back_to_the_rubric_not_a_constant(monkeypatch):
    """The regression test.

    `predict_cognitive_state` returned the literal "Needs Simple Basics" whenever
    the model was absent or raised. A service with no model still answered every
    request with a confident constant, and every lesson came out pitched for a
    beginner.
    """
    from app.services import ml_service

    monkeypatch.setattr(ml_service, "_bundle", None)

    slip = ml_service.predict_cognitive_state(1, "int x = 1;", 95)
    struggling = ml_service.predict_cognitive_state(8, "int x = 1;", 10)

    assert slip == rubric.MINOR_SYNTAX_ERROR
    assert struggling == rubric.NEEDS_SIMPLE_BASICS
    assert slip != struggling, "the fallback is answering with a constant again"


def test_a_broken_model_still_falls_back_to_the_rubric(monkeypatch):
    from app.services import ml_service

    class Exploding:
        def predict(self, _frame):
            raise RuntimeError("feature names mismatch")

    monkeypatch.setattr(
        ml_service,
        "_bundle",
        {"model": Exploding(), "feature_columns": ml_service._bundle["feature_columns"]
         if ml_service._bundle else ["error_count", "complexity_score", "past_score"],
         "card": {}},
    )

    assert ml_service.predict_cognitive_state(1, "int x = 1;", 95) == rubric.MINOR_SYNTAX_ERROR


# ── The generated dataset ────────────────────────────────────────────────────
def test_generated_rows_are_labelled_by_the_rubric_they_claim():
    """Every row's label must be what the rubric says, or the CSV is stale."""
    import csv

    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data",
        "cognitive_rubric_dataset.csv",
    )
    if not os.path.exists(path):
        pytest.skip("dataset not generated")

    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) >= 300
    for row in rows:
        state, rule_id, _ = explain(
            int(row["error_count"]), int(row["complexity_score"]), int(row["past_score"])
        )
        assert row["cognitive_state"] == state
        assert row["rule_id"] == rule_id
        assert row["label_source"].startswith("rubric")
