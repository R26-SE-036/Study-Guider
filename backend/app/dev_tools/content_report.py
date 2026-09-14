"""What the stored lessons and quizzes are saving, and what they cost to write.

Reads the Lesson and Quiz nodes content_store writes. "Served from store" is
the number of times a stored lesson or quiz was handed out instead of a new one
being generated - each one a generation call the daily limit did not have to
pay for, and a 15-45 second wait a student did not have.

USAGE (from backend/, with NEO4J_* set)
    python -m app.dev_tools.content_report
"""

from __future__ import annotations

from statistics import median
from typing import Any, Iterable

from app.core.concepts import ERROR_TYPE_TO_CONCEPT
from app.services.cognitive_rubric import COGNITIVE_STATES


def summarise(lessons: Iterable[dict[str, Any]], quizzes: Iterable[dict[str, Any]]) -> dict[str, Any]:
    lessons = list(lessons)
    quizzes = list(quizzes)

    def timing(items):
        values = [item["generation_ms"] for item in items if isinstance(item.get("generation_ms"), (int, float))]
        return {"median_ms": int(median(values)) if values else None, "measured": len(values)}

    new_student = {
        (lesson.get("error_type"), lesson.get("cognitive_state"))
        for lesson in lessons
        if str(lesson.get("situation", "")).startswith("read|none|")
    }
    wanted = {(error_type, state) for error_type in ERROR_TYPE_TO_CONCEPT for state in COGNITIVE_STATES}

    return {
        "lessons": len(lessons),
        "lesson_hits": sum(int(lesson.get("hits") or 0) for lesson in lessons),
        "lesson_generation": timing(lessons),
        "quizzes": len(quizzes),
        "quiz_hits": sum(int(quiz.get("hits") or 0) for quiz in quizzes),
        "quiz_generation": timing(quizzes),
        "new_student_coverage": {
            "covered": len(new_student & wanted),
            "of": len(wanted),
            "missing": sorted(wanted - new_student),
        },
    }


def main() -> None:
    from app.db.neo4j_connection import neo4j_db

    lessons = neo4j_db.execute_query(
        """
        MATCH (l:Lesson) WHERE l.key IS NOT NULL
        RETURN l.error_type AS error_type, l.cognitive_state AS cognitive_state,
               l.situation AS situation, l.generation_ms AS generation_ms, l.hits AS hits
        """
    )
    quizzes = neo4j_db.execute_query(
        "MATCH (q:Quiz) RETURN q.key AS key, q.generation_ms AS generation_ms, q.hits AS hits"
    )
    report = summarise(lessons, quizzes)

    print(f"Lessons stored: {report['lessons']}, served from store {report['lesson_hits']} time(s), "
          f"median generation {report['lesson_generation']['median_ms']} ms")
    print(f"Quizzes stored: {report['quizzes']}, served from store {report['quiz_hits']} time(s), "
          f"median generation {report['quiz_generation']['median_ms']} ms")
    coverage = report["new_student_coverage"]
    print(f"New-student lessons ready: {coverage['covered']} of {coverage['of']} (mistake x cognitive state)")
    for error_type, state in coverage["missing"][:10]:
        print(f"  missing: {error_type} / {state}")
    if len(coverage["missing"]) > 10:
        print(f"  ...and {len(coverage['missing']) - 10} more. dev_tools/pregenerate_content.py writes them.")


if __name__ == "__main__":
    main()
