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


def _observe(probability_known: float, correct: bool) -> float:
    """One Bayesian update: belief before an answer -> belief after it.

    The two branches are Bayes' rule with the slip and guess parameters as the
    likelihoods, followed by the learning step. Splitting them is what makes
    BKT more than a running average: a correct answer raises the belief a lot
    when guessing is unlikely and barely at all when it is not.
    """
    if correct:
        numerator = probability_known * (1 - PROBABILITY_OF_SLIP)
        denominator = numerator + (1 - probability_known) * PROBABILITY_OF_GUESS
    else:
        numerator = probability_known * PROBABILITY_OF_SLIP
        denominator = numerator + (1 - probability_known) * (1 - PROBABILITY_OF_GUESS)

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
