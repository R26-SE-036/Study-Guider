"""The stated rubric behind the cognitive-state label.

============================ WHY THIS FILE EXISTS ============================
`cognitive_model.pkl` was a RandomForest fitted on `data/dataset.csv`: ten rows,
handwritten. An 80/20 split left eight rows to train on and TWO to test, across
three classes, so the accuracy the trainer printed could only be 0%, 50% or
100% and measured nothing. With `error_count` and `past_score` as the only
numeric inputs, the ten rows were separable by a threshold on `error_count`
alone - a three-branch rule stored in a pickle.

The deeper problem is that "cognitive state" has no ground truth in this
project. Nobody observed these students and recorded whether they were
cognitively overloaded. The ten labels were one person's intuition, and
generating two thousand more rows in the same spirit would only fit that
intuition more tightly while making the number look more impressive.

So the intuition is written down instead, here, as a rubric anyone can read and
disagree with. Then:

  * the training set is GENERATED FROM this rubric (dev_tools/generate_rubric_dataset.py),
  * the model learns to approximate it,
  * and the reported metric is fidelity TO THE RUBRIC - how well the classifier
    reproduces a rule we wrote - which is a claim we can actually support.

It is NOT evidence about students, and `model_card.json` says so in those words.

WHY KEEP A MODEL AT ALL, IF THE RULE IS WRITTEN DOWN
Two reasons, and neither is "because ML sounds better".
  1. The rubric is a step function. The model interpolates near the
     boundaries, so a student one error either side of a cut does not flip
     between a beginner's explanation and a terse correction.
  2. It is the slot real labels go into. Rows carry `label_source`, and when a
     tutor annotates real triggers the trainer prefers those rows and the
     generated ones fall away. Nothing else has to change.

WHAT THE LABEL IS USED FOR
One thing only: choosing the register of the generated micro-lesson. See the
prompt in lesson_service.py - "High Cognitive Load" and "Needs Simple Basics"
ask for a slower, step-by-step explanation, "Minor Syntax Error" asks for a
quick correction. It does not gate content, decide mastery, or reach a
transcript. A wrong label costs a student an explanation pitched slightly off,
which is the right amount of weight for a judgement this soft to carry.
=============================================================================
"""

from __future__ import annotations

# The three states, exactly as lesson_service.py's prompt spells them.
HIGH_COGNITIVE_LOAD = "High Cognitive Load"
NEEDS_SIMPLE_BASICS = "Needs Simple Basics"
MINOR_SYNTAX_ERROR = "Minor Syntax Error"

COGNITIVE_STATES = (HIGH_COGNITIVE_LOAD, NEEDS_SIMPLE_BASICS, MINOR_SYNTAX_ERROR)

# Input ranges, matching what actually reaches this code at runtime:
#   error_count       repeats behind the remediation trigger, from Code Coach
#   complexity_score  ml_service.extract_code_complexity, clamped to 1..20
#   past_score        the student's average quiz percentage, 0..100
ERROR_COUNT_RANGE = (1, 12)
COMPLEXITY_RANGE = (1, 20)
PAST_SCORE_RANGE = (0, 100)

# ── The cuts ──────────────────────────────────────────────────────────────────
# Named so they can be argued with individually rather than as one opaque rule.
# These are pedagogical judgements, not measurements. Anyone is free to move
# them; what matters is that moving them is a visible edit to this file rather
# than a silent change in a retrained pickle.
WEAK_PAST_SCORE = 45      # below this, the student is not passing
MID_PAST_SCORE = 60       # below this, shaky; above, broadly coping
STRONG_PAST_SCORE = 75    # above this, the student generally knows the material
SIMPLE_CODE = 6           # at or below, the snippet has almost no control flow
COMPLEX_CODE = 10         # at or above, nested control flow or many conditions
VERY_COMPLEX_CODE = 12
REPEATED_ERRORS = 3       # a pattern rather than a slip
PERSISTENT_ERRORS = 5     # the same mistake is not going away


def _clamp(error_count: int, complexity_score: int, past_score: int) -> tuple[int, int, int]:
    return (
        max(0, int(error_count)),
        max(1, int(complexity_score)),
        min(100, max(0, int(past_score))),
    )


# The rubric itself: an ordered decision list, first match wins. Ordered rather
# than scored because a reader should be able to point at the one line that
# produced a given label and say whether they agree with it.
#
# Each entry is (rule id, why, predicate, state). Written as data so `classify`
# and `explain` read the same list - a second hand-written copy of the branches
# is exactly how the Gamification trainer's leak survived being fixed once.
#
# R3 and R6 exist because of the disagreement check against the ten handwritten
# rows this rubric replaced (dev_tools/generate_rubric_dataset.py --check).
# Without them, a student who had repeated the same mistake four times on
# moderately busy code matched nothing and fell through to R8, "a slip" - which
# four repeats plainly are not. That was a hole in the rubric, not a bad row.
RULES = (
    (
        "R1",
        "not passing, on simple code - the foundation is missing",
        # Simple code cannot overload anyone; there is not enough in it.
        lambda errors, complexity, past: past < WEAK_PAST_SCORE and complexity <= SIMPLE_CODE,
        NEEDS_SIMPLE_BASICS,
    ),
    (
        "R2",
        "the same error persists and the history is weak",
        # More explanation at the same difficulty has been tried and failed.
        lambda errors, complexity, past: errors >= PERSISTENT_ERRORS and past < MID_PAST_SCORE,
        NEEDS_SIMPLE_BASICS,
    ),
    (
        "R3",
        "repeating a mistake on simple code - a gap, not overload",
        # No `past_score` condition, deliberately. This rule first read
        # `past < STRONG_PAST_SCORE`, which let a strong student repeating an
        # error four times on `int x = 1;` fall through to R5 and be called
        # overloaded - by code with no control flow in it. A good average does
        # not help with the one concept you keep missing; it is still a gap.
        lambda errors, complexity, past: (
            errors >= REPEATED_ERRORS and complexity <= SIMPLE_CODE
        ),
        NEEDS_SIMPLE_BASICS,
    ),
    (
        "R4",
        "complex code plus mounting errors - overloaded",
        # The classic overload signature, and why complexity is a feature.
        lambda errors, complexity, past: complexity >= COMPLEX_CODE and errors >= REPEATED_ERRORS,
        HIGH_COGNITIVE_LOAD,
    ),
    (
        "R5",
        "a normally-coping student stuck repeatedly on this one",
        # Their history says the foundation is there, so it is this problem.
        lambda errors, complexity, past: errors >= 4 and past >= MID_PAST_SCORE,
        HIGH_COGNITIVE_LOAD,
    ),
    (
        "R6",
        "repeated errors on code that is not trivial",
        # Reached by mid-ability students on moderate code: too much to hold at
        # once, but the foundation is not obviously missing.
        lambda errors, complexity, past: errors >= REPEATED_ERRORS and complexity > SIMPLE_CODE,
        HIGH_COGNITIVE_LOAD,
    ),
    (
        "R7",
        "very complex code for a student who is not yet strong",
        lambda errors, complexity, past: (
            complexity >= VERY_COMPLEX_CODE and past < STRONG_PAST_SCORE
        ),
        HIGH_COGNITIVE_LOAD,
    ),
    (
        "R8",
        "few errors on manageable code - a slip",
        lambda errors, complexity, past: True,
        MINOR_SYNTAX_ERROR,
    ),
)


def explain(error_count: int, complexity_score: int, past_score: int) -> tuple[str, str, str]:
    """(state, rule_id, reason) for one input."""
    errors, complexity, past = _clamp(error_count, complexity_score, past_score)

    for rule_id, reason, predicate, state in RULES:
        if predicate(errors, complexity, past):
            return state, rule_id, reason

    raise AssertionError("R8 matches everything; this line is unreachable.")


def classify(error_count: int, complexity_score: int, past_score: int) -> str:
    """The cognitive state for one struggling student, per the rubric."""
    return explain(error_count, complexity_score, past_score)[0]
