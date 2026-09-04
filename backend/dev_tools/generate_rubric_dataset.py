"""Generate the cognitive-state training set from the stated rubric.

The rows this writes are NOT observations. They are a rubric, sampled - see
app/services/cognitive_rubric.py for what the rubric is and why writing it down
beat handwriting ten more rows.

Every row carries `label_source=rubric` and `rater=cognitive_rubric.v1`, and the
trainer refuses to describe a model fitted on them as anything other than an
approximation of that rubric. When a tutor annotates real remediation triggers,
append those rows with label_source=human and the trainer prefers them.

WHY THE INPUTS ARE SAMPLED RATHER THAN GRIDDED
A uniform grid over (error_count, complexity, past_score) spends most of its
rows in corners that do not occur - a student averaging 95% who has repeated the
same mistake eleven times, say. The model would then be most confident exactly
where no student lives, and the class balance would be a property of the box
rather than of the cohort. So a student's ability is drawn first, and their
error count is drawn conditioned on that ability and on how busy the code is.

Usage:
    python dev_tools/generate_rubric_dataset.py            # 2000 rows
    python dev_tools/generate_rubric_dataset.py --rows 500
    python dev_tools/generate_rubric_dataset.py --check    # rubric vs the old
                                                           # handwritten rows
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.cognitive_rubric import (  # noqa: E402
    COMPLEXITY_RANGE,
    ERROR_COUNT_RANGE,
    RULES,
    explain,
)

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(HERE, "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "cognitive_rubric_dataset.csv")
LEGACY_PATH = os.path.join(DATA_DIR, "dataset.csv")

LABEL_SOURCE = "rubric"
RATER = "cognitive_rubric.v1"

FIELDS = [
    "error_count",
    "complexity_score",
    "past_score",
    "cognitive_state",
    "rule_id",
    "label_source",
    "rater",
]


def sample_row(rng: random.Random) -> dict:
    """One plausible (student, snippet, struggle) triple."""
    # Ability: centred a little below the pass mark, because these rows describe
    # students who have already tripped a remediation trigger. A cohort-wide
    # distribution would be wrong here - this is the struggling tail.
    past_score = int(min(100, max(0, rng.gauss(55, 20))))

    # Snippet complexity: first-year Java, so mostly small. Long right tail for
    # the nested-loop exercises.
    complexity_score = int(
        min(COMPLEXITY_RANGE[1], max(COMPLEXITY_RANGE[0], rng.lognormvariate(1.7, 0.7)))
    )

    # Errors, conditioned on both. A weaker student on busier code repeats a
    # mistake more often; this is the dependence a uniform grid throws away.
    pressure = (100 - past_score) / 100 + complexity_score / 20
    expected_errors = 1 + pressure * 2.6
    error_count = int(
        min(ERROR_COUNT_RANGE[1], max(ERROR_COUNT_RANGE[0], rng.gauss(expected_errors, 1.4)))
    )

    state, rule_id, _ = explain(error_count, complexity_score, past_score)

    return {
        "error_count": error_count,
        "complexity_score": complexity_score,
        "past_score": past_score,
        "cognitive_state": state,
        "rule_id": rule_id,
        "label_source": LABEL_SOURCE,
        "rater": RATER,
    }


def generate(rows: int, seed: int, min_per_rule: int) -> list[dict]:
    """`rows` sampled naturally, then rare rules topped up to `min_per_rule`.

    The natural sample alone leaves R5 - very complex code, mid-ability student
    - at about 1% of rows, and a classifier trained on that simply never
    predicts it. The top-up is deliberate oversampling of the rubric's thin
    regions, and it is marked `coverage_topup` in the CSV so nobody mistakes the
    resulting class balance for a cohort's. The trainer weights classes anyway.
    """
    rng = random.Random(seed)
    sampled = [sample_row(rng) for _ in range(rows)]

    counts = Counter(row["rule_id"] for row in sampled)
    wanted = {rule_id for rule_id, _, _, _ in RULES if counts[rule_id] < min_per_rule}

    attempts = 0
    while wanted and attempts < rows * 400:
        attempts += 1
        candidate = sample_row(rng)
        rule_id = candidate["rule_id"]
        if rule_id in wanted:
            candidate["label_source"] = "rubric_coverage_topup"
            sampled.append(candidate)
            counts[rule_id] += 1
            if counts[rule_id] >= min_per_rule:
                wanted.discard(rule_id)

    if wanted:
        print(
            f"Warning: could not reach {min_per_rule} rows for {sorted(wanted)} by "
            "sampling. Those regions are rare enough that the model will be weak "
            "there; the model card records it."
        )

    rng.shuffle(sampled)
    return sampled


def check_against_legacy() -> int:
    """Does the written rubric reproduce the handwritten labels it replaced?

    The ten rows in data/dataset.csv were one person's intuition. If the rubric
    is a faithful formalisation of that intuition it should agree with most of
    them - and where it does not, the disagreement is worth reading, because one
    of the two is wrong and it is not automatically the rubric.
    """
    if not os.path.exists(LEGACY_PATH):
        print(f"No legacy dataset at {LEGACY_PATH}; nothing to compare.")
        return 0

    sys.path.insert(0, HERE)
    from app.services.ml_service import extract_code_complexity

    agreed = 0
    total = 0
    print(f"{'errors':>6} {'cplx':>5} {'past':>5}  {'handwritten':<20} {'rubric':<20} rule")
    with open(LEGACY_PATH, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            total += 1
            complexity = extract_code_complexity(row["code_snippet"])
            state, rule_id, _ = explain(
                int(row["error_count"]), complexity, int(row["past_score"])
            )
            match = state == row["cognitive_state"]
            agreed += match
            print(
                f"{row['error_count']:>6} {complexity:>5} {row['past_score']:>5}  "
                f"{row['cognitive_state']:<20} {state:<20} {rule_id}"
                f"{'' if match else '   <-- disagrees'}"
            )

    print(f"\nAgreement: {agreed}/{total}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-per-rule", type=int, default=150)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.check:
        return check_against_legacy()

    rows = generate(args.rows, args.seed, args.min_per_rule)

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")
    print(f"  label_source={LABEL_SOURCE} (+ rubric_coverage_topup)  rater={RATER}")
    print("\nClass balance:")
    for state, count in Counter(row["cognitive_state"] for row in rows).most_common():
        print(f"  {state:<22} {count:>5}  ({count / len(rows):.1%})")
    print("\nRule coverage:")
    for rule_id, count in sorted(Counter(row["rule_id"] for row in rows).items()):
        print(f"  {rule_id}  {count:>5}  ({count / len(rows):.1%})")
    print(
        "\nThese are a sampled rubric, not observations. A model fitted on them\n"
        "measures fidelity to the rubric and nothing about students."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
