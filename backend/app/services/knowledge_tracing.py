"""Bayesian Knowledge Tracing over the student's quiz attempts.

============================ WHY THIS EXISTS ============================
FR-08 asks the system to "update the student's mastery profile using Knowledge
Tracing logic", and §3.2 says the graph should "predict a student's future
performance based on their historical logical error patterns".

What existed was an average of past quiz percentages. That is a gradebook: it
describes what already happened and predicts nothing. Two students on 60% are
indistinguishable under it, even when one has gone 40 -> 55 -> 85 and the other
85 -> 55 -> 40. The first is learning; the second is not.

BKT is the smallest model that actually answers the question the proposal asks.
It carries one number per concept - the probability the student KNOWS it - and
updates that belief after every observation.

============================== THE FOUR NUMBERS =========================
BKT is defined by four parameters. Naming them here, with why each value was
chosen, because they ARE the model - there is nothing else to it.

  P(L0)  prior      Probability the student already knows a concept before any
                    evidence. 0.25 - these concepts reach a student only after
                    Code Coach has seen them get it wrong repeatedly, so
                    starting at "probably knows this" would contradict the
                    reason the lesson exists at all.

  P(T)   transit    Probability of learning it between one question and the
                    next. 0.15 - a micro-lesson sits between the trigger and
                    the quiz, so learning genuinely can happen; but a single
                    lesson moving a student from ignorance to mastery in one
                    step is not the common case.

  P(G)   guess      Probability of answering correctly WITHOUT knowing. 0.25,
                    which is not a guess about guessing: the quizzes are
                    four-option multiple choice, so a student choosing at
                    random is right a quarter of the time. This one is derived,
                    not tuned.

  P(S)   slip       Probability of answering wrongly WHILE knowing. 0.10 -
                    misreading, a typo, a mis-click.

These are literature-standard starting values, not fitted ones, and the model
card says so. Fitting them needs a corpus of real attempts, which does not
exist yet - and inventing one to fit against would be the same mistake the
Gamification trainer made.
=========================================================================
"""

from __future__ import annotations

from dataclasses import dataclass

# The four parameters. Module-level constants rather than arguments because a
# per-call override would let two callers disagree about what "mastered" means.
PRIOR_KNOWN = 0.25
PROBABILITY_OF_LEARNING = 0.15
PROBABILITY_OF_GUESS = 0.25
PROBABILITY_OF_SLIP = 0.10

# ========================= CONFIDENCE (metacognition) =========================
# Before each answer the student says how sure they are: low, medium or high.
# That changes what the answer is evidence OF, so two of the four parameters
# move for two of the six cases:
#
#   right, LOW confidence    a lucky guess is the likelier story, so a correct
#                            answer is weaker evidence: guess 0.40, not 0.25.
#   wrong, HIGH confidence   not a slip but a misconception - the student is
#                            sure of the wrong idea - so slip 0.05, not 0.10,
#                            and mastery drops further.
#
# Every other case, and every answer stored before confidence existed, uses
# the four parameters above unchanged. Like them, these are starting values
# chosen from what the cases mean, not fitted ones: fitting needs real answers
# with confidence attached, which this feature is what starts collecting.
# =============================================================================
CONFIDENCE_LEVELS = ("low", "medium", "high")
PROBABILITY_OF_GUESS_UNSURE = 0.40
PROBABILITY_OF_SLIP_CONFIDENT = 0.05

# What each level means as a probability of being right, for the calibration
# score: "low" is close to a guess on four options, "high" is certainty.
CONFIDENCE_PROBABILITY = {"low": 0.33, "medium": 0.66, "high": 1.0}

# At or above this, the concept is treated as mastered. 0.95 is the usual BKT
# convention and is deliberately far stricter than the old rule, which called a
# single 50% quiz "MASTERED".
MASTERY_THRESHOLD = 0.95


@dataclass(frozen=True)
class MasteryEstimate:
    """What BKT believes about one student and one concept."""

    concept: str
    probability_known: float
    predicted_correct: float
    observations: int
    mastered: bool

    def as_dict(self) -> dict:
        return {
            "concept": self.concept,
            "probability_known": round(self.probability_known, 4),
            "predicted_correct": round(self.predicted_correct, 4),
            "observations": self.observations,
            "mastered": self.mastered,
        }


def _parameters(correct: bool, confidence: str | None) -> tuple[float, float]:
    """(guess, slip) for one answer, given how sure the student said they were."""
    guess, slip = PROBABILITY_OF_GUESS, PROBABILITY_OF_SLIP
    if correct and confidence == "low":
        guess = PROBABILITY_OF_GUESS_UNSURE
    if not correct and confidence == "high":
        slip = PROBABILITY_OF_SLIP_CONFIDENT
    return guess, slip


def _observe(probability_known: float, correct: bool, confidence: str | None = None) -> float:
    """One Bayesian update: belief before an answer -> belief after it.

    The two branches are Bayes' rule with the slip and guess parameters as the
    likelihoods, followed by the learning step. Splitting them is what makes
    BKT more than a running average: a correct answer raises the belief a lot
    when guessing is unlikely and barely at all when it is not.

    `confidence` ("low", "medium", "high", or None when it was not asked)
    adjusts guess and slip for that one answer - see CONFIDENCE above.
    """
    guess, slip = _parameters(correct, confidence)
    if correct:
        numerator = probability_known * (1 - slip)
        denominator = numerator + (1 - probability_known) * guess
    else:
        numerator = probability_known * slip
        denominator = numerator + (1 - probability_known) * (1 - guess)

    # Only reachable if slip and guess are both set to impossible values, but a
    # ZeroDivisionError inside a mastery calculation would surface as a 500 on
    # the dashboard, so it is handled rather than assumed away.
    posterior = numerator / denominator if denominator else probability_known

    # The learning step: having answered, the student may now know it.
    return posterior + (1 - posterior) * PROBABILITY_OF_LEARNING


def predicted_correct(probability_known: float) -> float:
    """Probability the NEXT answer is correct.

    This is the prediction FR-08 asks for, and it is not the same number as
    probability_known: a student who knows nothing still scores 0.25 on
    four-option questions, and one who knows everything still slips.
    """
    return (
        probability_known * (1 - PROBABILITY_OF_SLIP)
        + (1 - probability_known) * PROBABILITY_OF_GUESS
    )


def trace(attempts: list[dict]) -> float:
    """Run BKT over one concept's attempts, oldest first, and return P(known).

    Each attempt is a quiz with `score` correct out of `total`, and each
    QUESTION is one observation - so a 3/4 feeds three corrects and one
    incorrect, not a single "75%". Collapsing a quiz into one observation would
    throw away most of the evidence the student produced.

    Correct answers are applied before incorrect ones within an attempt. The
    order questions were answered in is not stored, and BKT is order-sensitive,
    so this is a deliberate, stated convention rather than an accident - it
    reads a mixed quiz as "got some, then slipped", which is the more
    conservative of the two readings.
    """
    probability = PRIOR_KNOWN

    for attempt in attempts:
        # An attempt saved with its answers is replayed answer by answer, in
        # the order they were given, each with its confidence. Older attempts
        # only have a score, and keep the convention below.
        answers = attempt.get("answers")
        if answers:
            for answer in answers:
                probability = _observe(probability, bool(answer.get("correct")), answer.get("confidence"))
            continue

        total = int(attempt.get("total") or 0)
        score = int(attempt.get("score") or 0)

        if total <= 0:
            continue

        score = max(0, min(score, total))

        for _ in range(score):
            probability = _observe(probability, correct=True)
        for _ in range(total - score):
            probability = _observe(probability, correct=False)

    return probability


def calibration(answers: list[dict]) -> dict:
    """How well a student knows what they know: a Brier score over their answers.

    Each answer's confidence becomes a probability of being right
    (CONFIDENCE_PROBABILITY) and is compared with whether it was right:
    Brier = mean((p - outcome)^2). 0 is perfect calibration; saying "medium"
    to everything on questions you get right half the time scores about 0.25.
    Lower is better.

    Also returned per level, how often the student was right when they said
    it, which is what the progress page explains the score with.
    """
    rated = [a for a in answers if a.get("confidence") in CONFIDENCE_PROBABILITY]
    by_level = {
        level: {"answers": 0, "correct": 0}
        for level in CONFIDENCE_LEVELS
    }
    squared = 0.0
    for answer in rated:
        level = answer["confidence"]
        right = bool(answer.get("correct"))
        squared += (CONFIDENCE_PROBABILITY[level] - (1.0 if right else 0.0)) ** 2
        by_level[level]["answers"] += 1
        by_level[level]["correct"] += int(right)

    for level in by_level.values():
        level["accuracy"] = round(level["correct"] / level["answers"], 4) if level["answers"] else None

    return {
        "answers": len(rated),
        "brier": round(squared / len(rated), 4) if rated else None,
        "by_confidence": by_level,
        # Confident and wrong: the misconceptions, the case worth a teacher's eye.
        "confident_but_wrong": sum(1 for a in rated if a["confidence"] == "high" and not a.get("correct")),
        "unsure_but_right": sum(1 for a in rated if a["confidence"] == "low" and a.get("correct")),
    }


def estimate(concept: str, attempts: list[dict]) -> MasteryEstimate:
    """The full picture for one concept."""
    observations = sum(int(a.get("total") or 0) for a in attempts)
    probability = trace(attempts)

    return MasteryEstimate(
        concept=concept,
        probability_known=probability,
        predicted_correct=predicted_correct(probability),
        observations=observations,
        # A concept with no attempts is not mastered, whatever the prior says.
        mastered=observations > 0 and probability >= MASTERY_THRESHOLD,
    )
