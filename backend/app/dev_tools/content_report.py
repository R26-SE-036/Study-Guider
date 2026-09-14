"""What the stored lessons and quizzes save, what they cost, and how well-founded they are.

Reads the Lesson and Quiz nodes content_store writes.

  served from store   times a stored lesson or quiz was handed out instead of a
                      new one being generated - each a call the daily limit did
                      not pay for, and a 15-45 second wait nobody sat through
  citing lessons      lessons that name at least one syllabus note they drew on,
                      among notes actually given to them
  markable questions  how many of the model's questions could be marked at all
                      before the best eight were kept; well above eight means
                      the checks have room, near eight means quizzes are close
                      to failing

USAGE (from backend/, with NEO4J_* set)
    python -m app.dev_tools.content_report
"""

from __future__ import annotations

import json
from statistics import median
from typing import Any, Iterable

from app.core.concepts import ERROR_TYPE_TO_CONCEPT
from app.services.cognitive_rubric import COGNITIVE_STATES


def _cited(lesson: dict[str, Any]) -> int:
    try:
        return len(json.loads(lesson.get("sources_json") or "[]"))
    except (TypeError, ValueError):
        return 0


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
    markable = [quiz["candidates"] for quiz in quizzes if isinstance(quiz.get("candidates"), (int, float))]

    return {
        "lessons": len(lessons),
        "lesson_hits": sum(int(lesson.get("hits") or 0) for lesson in lessons),
        "lesson_generation": timing(lessons),
        "citing_lessons": sum(1 for lesson in lessons if _cited(lesson)),
        "quizzes": len(quizzes),
        "quiz_hits": sum(int(quiz.get("hits") or 0) for quiz in quizzes),
        "quiz_generation": timing(quizzes),
        "markable_questions_median": median(markable) if markable else None,
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
               l.situation AS situation, l.generation_ms AS generation_ms, l.hits AS hits,
               l.sources_json AS sources_json
        """
    )
    quizzes = neo4j_db.execute_query(
        "MATCH (q:Quiz) RETURN q.key AS key, q.generation_ms AS generation_ms, q.hits AS hits, q.candidates AS candidates"
    )
    report = summarise(lessons, quizzes)

    print(f"Lessons stored: {report['lessons']}, served from store {report['lesson_hits']} time(s), "
          f"median generation {report['lesson_generation']['median_ms']} ms")
    print(f"  citing at least one syllabus note: {report['citing_lessons']} of {report['lessons']}")
    print(f"Quizzes stored: {report['quizzes']}, served from store {report['quiz_hits']} time(s), "
          f"median generation {report['quiz_generation']['median_ms']} ms")
    print(f"  median markable questions per generation: {report['markable_questions_median']} (8 are kept)")
    coverage = report["new_student_coverage"]
    print(f"New-student lessons ready: {coverage['covered']} of {coverage['of']} (mistake x cognitive state)")
    for error_type, state in coverage["missing"][:10]:
        print(f"  missing: {error_type} / {state}")
    if len(coverage["missing"]) > 10:
        print(f"  ...and {len(coverage['missing']) - 10} more. dev_tools/pregenerate_content.py writes them.")


if __name__ == "__main__":
    main()
