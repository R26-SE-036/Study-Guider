"""Give one account a plausible learning history, so the dashboard can be seen.

    python -m app.dev_tools.seed_demo_student --email you@example.com --password ...
    python -m app.dev_tools.seed_demo_student --email ... --password ... --apply
    python -m app.dev_tools.seed_demo_student --email ... --password ... --clear --apply

Dry run is the default: it prints exactly what it would write, and the state
each concept would end up in, without touching the graph.

============================ WHAT THIS IS FOR ============================
The progress dashboard has a lot to show - knowledge tracing per concept, a
coverage radar, a trajectory line, reading-time against score, the curriculum
map - and none of it can be looked at on an account with three quiz attempts.
Judging a layout needs a populated one, and populating one by hand means
sitting through twenty quizzes.

So this writes a history that a student plausibly could have produced, and
marks every relationship it creates with `seeded: true`.

============================ WHAT THIS IS NOT ============================
This data is INVENTED. It is not evidence of anything.

  - It must never appear in an evaluation, a results table, or a figure in the
    dissertation. The BKT curves it produces are curves over numbers this file
    chose, not over anything a person did.
  - It must never be used to fit or validate a model. Every one of these
    scores was picked to make a chart look complete, which is the definition
    of the bias a held-out set exists to catch.
  - It should not be on the account used for a demonstration or a viva unless
    the examiner is told it is sample data.

`seeded: true` exists so that boundary survives contact with a database. The
seeded attempts can be told apart from real ones by anything that queries the
graph later, and `--clear` removes exactly them and nothing else - so an
account with real history can be populated, looked at, and put back.

============================ HOW IT IS SHAPED ===========================
The history follows PREREQUISITE_EDGES: foundations first, and a concept is
only attempted after the things it depends on. Scores improve within a
concept, because that is what a student who is being remediated looks like -
and because a flat sequence would make the trajectory chart pointless.

Reading time correlates with the score that follows, loosely and with
exceptions, because that is the relationship FR-07 exists to let a supervisor
look for. One attempt deliberately has no recorded time, so the "measured
attempts" count and the null handling are both exercised.

Concepts are left unattempted on purpose, and one of them is left blocked, so
all four curriculum states appear:

    mastered · in_progress · ready · locked

Nothing here touches a concept the account already has real attempts on - that
history stays interpretable.
========================================================================
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone

import requests

from app.core.concepts import CONCEPT_TAGS
from app.core.config import settings
from app.db.neo4j_connection import neo4j_db
from app.services import knowledge_tracing
from app.services.progress_service import PASS_MARK_PERCENT

# ── The invented history ──
#
# (concept, [(days_ago, score, seconds_on_lesson), ...]) - four questions per
# quiz, matching what quiz_service generates. Ordered as a student would meet
# them, oldest first.
#
# `None` for the seconds means no measurement, which is what the graph holds
# for a quiz taken without opening a lesson. It is not zero, and the dashboard
# is careful about the difference, so at least one of these has to exist for
# that path to ever be seen.
HISTORY: list[tuple[str, list[tuple[int, int, float | None]]]] = [
    ("assignment_logic",      [(34, 2, 210), (33, 4, 480)]),
    ("boolean_logic",         [(31, 1, 95), (30, 3, 420), (28, 4, 505)]),
    ("arithmetic_operations", [(27, 3, 360), (26, 4, 450)]),
    ("conditional_logic",     [(24, 2, 150), (22, 3, 390), (20, 4, 610)]),
    ("loop_initialization",   [(17, 1, 80), (15, 2, 240), (13, 3, 430)]),
    ("string_comparison",     [(12, 3, 380), (10, 4, 520)]),
    ("loop_control",          [(11, 2, 200), (9, 3, 380)]),
    ("loop_boundaries",       [(7, 1, 120), (6, 2, None), (4, 3, 470)]),
    ("array_indexing",        [(2, 1, 110), (1, 3, 440)]),
]

QUESTIONS_PER_QUIZ = 4


def resolve_student_id(email: str, password: str) -> str:
    """Ask Code Coach who this is. Study Guider has no accounts of its own."""
    response = requests.post(
        f"{settings.CODE_COACH_URL}/api/v1/auth/login",
        json={"identifier": email, "password": password, "client_name": "codeguru-portal"},
        timeout=settings.CODE_COACH_TIMEOUT_SECONDS,
    )

    if response.status_code != 200:
        detail = (response.json() or {}).get("detail", response.text)
        raise SystemExit(f"Could not sign in as {email}: {detail}")

    user = (response.json() or {}).get("user") or {}
    student_id = user.get("user_id")
    if not student_id:
        raise SystemExit("Sign-in succeeded but returned no user_id.")

    print(f"  {email} -> {student_id} ({user.get('full_name')})")
    return student_id


def existing_attempts(student_id: str) -> list[dict]:
    return neo4j_db.execute_query(
        """
        MATCH (s:Student {student_id: $sid})-[a:ATTEMPTED]->(c:Concept)
        RETURN c.name AS concept, a.score AS score, a.total AS total,
               a.timestamp AS timestamp, coalesce(a.seeded, false) AS seeded
        ORDER BY a.timestamp
        """,
        {"sid": student_id},
    ) or []


def clear(student_id: str, apply: bool) -> None:
    """Delete the seeded attempts, and only those."""
    rows = existing_attempts(student_id)
    seeded = [r for r in rows if r["seeded"]]

    print(f"\n{len(seeded)} seeded attempt(s) to remove; "
          f"{len(rows) - len(seeded)} real attempt(s) will be left alone.")

    if not apply:
        print("\nDry run. Re-run with --apply to remove them.")
        return

    result = neo4j_db.execute_query(
        """
        MATCH (:Student {student_id: $sid})-[a:ATTEMPTED {seeded: true}]->(:Concept)
        DELETE a
        RETURN count(a) AS removed
        """,
        {"sid": student_id},
    )
    print(f"Removed {(result or [{}])[0].get('removed', 0)}.")


def seed(student_id: str, apply: bool) -> None:
    rows = existing_attempts(student_id)
    already_seeded = [r for r in rows if r["seeded"]]
    if already_seeded:
        print(f"\n⚠️  This account already has {len(already_seeded)} seeded attempt(s).")
        print("    Run with --clear --apply first, or they will be added to.")

    # Concepts with real history are skipped rather than added to, so a genuine
    # result is never averaged together with an invented one.
    real_concepts = {r["concept"] for r in rows if not r["seeded"]}
    if real_concepts:
        print(f"\nLeaving real history untouched on: {', '.join(sorted(real_concepts))}")

    now = datetime.now(timezone.utc)
    writes: list[dict] = []

    for concept, attempts in HISTORY:
        if concept in real_concepts:
            continue
        for days_ago, score, seconds in attempts:
            percentage = (score / QUESTIONS_PER_QUIZ) * 100
            writes.append(
                {
                    "concept": concept,
                    "score": score,
                    "total": QUESTIONS_PER_QUIZ,
                    "percentage": percentage,
                    "status": "MASTERED" if percentage >= PASS_MARK_PERCENT else "NEEDS_REVIEW",
                    "timestamp": (now - timedelta(days=days_ago)).isoformat(),
                    "seconds_on_lesson": seconds,
                }
            )

    # What the dashboard will say afterwards, computed from the same functions
    # it uses - so this is a prediction that can be wrong, not a description of
    # the intent.
    print(f"\n{len(writes)} attempt(s) to write across "
          f"{len({w['concept'] for w in writes})} concept(s).\n")

    combined: dict[str, list[dict]] = {}
    for row in rows:
        combined.setdefault(row["concept"], []).append(row)
    for write in writes:
        combined.setdefault(write["concept"], []).append(write)

    mastered = set()
    for concept, attempts in combined.items():
        attempts.sort(key=lambda a: a["timestamp"])
        if knowledge_tracing.estimate(concept, attempts).mastered:
            mastered.add(concept)

    states = {"mastered": 0, "in_progress": 0, "ready": 0, "locked": 0}
    from app.core.concepts import PREREQUISITE_EDGES

    prerequisites: dict[str, list[str]] = {tag: [] for tag in CONCEPT_TAGS}
    for prereq, dependent in PREREQUISITE_EDGES:
        prerequisites.setdefault(dependent, []).append(prereq)

    for tag in CONCEPT_TAGS:
        if tag in mastered:
            state = "mastered"
        elif tag in combined:
            state = "in_progress"
        elif all(p in mastered for p in prerequisites.get(tag, [])):
            state = "ready"
        else:
            state = "locked"
        states[state] += 1
        marker = "seeded" if tag in {w["concept"] for w in writes} else (
            "real" if tag in combined else "-"
        )
        print(f"  {tag:<24} {state:<12} {marker}")

    print(f"\n  {states}")

    measured = sum(1 for w in writes if w["seconds_on_lesson"] is not None)
    print(f"  {measured} of {len(writes)} seeded attempts carry a reading time.")

    if not apply:
        print("\nDry run. Nothing was written. Re-run with --apply.")
        return

    for write in writes:
        neo4j_db.execute_query(
            """
            MERGE (s:Student {student_id: $student_id})
            MERGE (c:Concept {name: $concept})
            CREATE (s)-[a:ATTEMPTED {
                score: $score,
                total: $total,
                percentage: $percentage,
                status: $status,
                timestamp: $timestamp,
                seconds_on_lesson: $seconds_on_lesson,
                seeded: true
            }]->(c)
            RETURN a
            """,
            {"student_id": student_id, **write},
        )

    print(f"\nWrote {len(writes)} attempt(s), all marked seeded: true.")
    print("Remove them with --clear --apply.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--clear", action="store_true",
                        help="Remove seeded attempts instead of adding them.")
    parser.add_argument("--apply", action="store_true",
                        help="Actually write. Without this it is a dry run.")
    args = parser.parse_args()

    print("Resolving the account against Code Coach…")
    student_id = resolve_student_id(args.email, args.password)

    if args.clear:
        clear(student_id, args.apply)
    else:
        seed(student_id, args.apply)

    return 0


if __name__ == "__main__":
    sys.exit(main())
