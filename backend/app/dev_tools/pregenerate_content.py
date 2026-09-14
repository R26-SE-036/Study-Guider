"""Write lessons and their first quiz ahead of time, within a budget.

WHY THIS EXISTS
    The free Gemini tier allows twenty generations a day for the whole project,
    and a new student's first lesson and quiz are two of them - written while
    the student waits 15 to 45 seconds. Every mistake Code Coach reports,
    at every cognitive state, for a student who has not taken a quiz yet, is a
    lesson and quiz that can be written in advance, a few a day, and then served
    to every student who arrives in that situation without a call or a wait.

    It asks lesson_service and quiz_service for them exactly as a real request
    would, so what it stores lands on the key a real student looks up. The
    student it asks as has no attempts on record, which is the "not quizzed yet"
    band - the situation every student starts in.

WHAT IT SPENDS
    At most --budget model calls per run (a lesson is one, a quiz is one), and
    it stops early on the daily limit. Anything already stored costs nothing,
    so running it every day works through the whole set.

USAGE (from backend/, with NEO4J_* and GEMINI_API_KEY set)
    python -m app.dev_tools.pregenerate_content --budget 15
    python -m app.dev_tools.pregenerate_content --error-type OFF_BY_ONE_LOOP_BOUNDARY --budget 6
"""

from __future__ import annotations

import argparse
from typing import Callable, Iterable

from app.core.concepts import ERROR_TYPE_TO_CONCEPT
from app.db.neo4j_connection import neo4j_db
from app.services import lesson_service, quiz_service
from app.services.cognitive_rubric import COGNITIVE_STATES
from app.services.concept_examples import example_for
from app.services.llm import LLMQuotaExhausted, LLMUnavailable
from app.services.rag_service import FOUND

# A student id with no attempts on record, so its situation is the one every
# new student is in.
PREGENERATION_STUDENT = "pregeneration"


def run(
    budget: int,
    error_types: Iterable[str] | None = None,
    states: Iterable[str] | None = None,
    log: Callable[[str], None] = print,
) -> dict:
    """Store what is missing, spending at most `budget` model calls."""
    summary = {"calls": 0, "lessons_written": 0, "quizzes_written": 0, "already_stored": 0, "stopped": "done"}

    for error_type in list(error_types or sorted(ERROR_TYPE_TO_CONCEPT)):
        concept = ERROR_TYPE_TO_CONCEPT.get(error_type, "")
        snippet = example_for(error_type)

        for state in list(states or COGNITIVE_STATES):
            if summary["calls"] >= budget:
                summary["stopped"] = "budget"
                return summary

            label = f"{error_type} / {state}"
            try:
                lesson = lesson_service.lesson_for(PREGENERATION_STUDENT, error_type, snippet, concept, state)
                if lesson["cached"]:
                    summary["already_stored"] += 1
                else:
                    summary["calls"] += 1
                    summary["lessons_written"] += 1

                if lesson["grounding"]["syllabus_notes"] != FOUND:
                    # Not stored, so a quiz built on it would not be either.
                    log(f"  {label}: lesson written without syllabus notes, so not stored - skipped the quiz")
                    continue

                if summary["calls"] >= budget:
                    summary["stopped"] = "budget"
                    return summary

                _questions, written = quiz_service.quiz_for(PREGENERATION_STUDENT, error_type, snippet)
                if written:
                    summary["calls"] += 1
                    summary["quizzes_written"] += 1
                log(f"  {label}: lesson {'stored' if lesson['cached'] else 'written'}, quiz {'written' if written else 'stored'}")

            except LLMQuotaExhausted:
                log("  The daily generation limit is reached. Run again once it resets.")
                summary["stopped"] = "daily_limit"
                return summary
            except LLMUnavailable as error:
                log(f"  {label}: not written ({error})")

    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--budget", type=int, default=15, help="model calls to spend this run (default 15)")
    parser.add_argument("--error-type", action="append", dest="error_types", help="limit to one error type; repeatable")
    arguments = parser.parse_args(argv)

    # Without the graph nothing written could be stored, so every call would be
    # spent on content that is thrown away.
    if not neo4j_db.reconnect_if_due():
        raise SystemExit("Neo4j is unreachable, so nothing written could be stored. Nothing was spent.")

    summary = run(arguments.budget, arguments.error_types)
    print(
        f"\nSpent {summary['calls']} of {arguments.budget} calls: "
        f"{summary['lessons_written']} lesson(s) and {summary['quizzes_written']} quiz(zes) written, "
        f"{summary['already_stored']} lesson(s) already stored. Stopped: {summary['stopped']}."
    )


if __name__ == "__main__":
    main()
