"""Generated lessons and quizzes, kept so each is written once and used many times.

============================ WHY THIS EXISTS ============================
The free Gemini tier allows twenty generations a day for the whole project,
and every lesson and every quiz is one. Lessons were cached per student, so the
same mistake cost a new lesson for every student who made it, and quizzes were
not kept at all - a new browser session wrote a new one. At twenty a day that
is about ten students' worth of study, in total.

A lesson is now kept under what it was written FOR rather than WHO it was
written for: the mistake, the cognitive state, the code it explains, and the
student's situation at band level (see lesson_service.StudentSituation). Two
students in the same situation get the same lesson, and because the prompt only
describes the band, the lesson says nothing that is true of one and not the
other. Quizzes hang off the lesson they test, a few versions each, so a retake
gets questions the student has not already seen.

    (:Student)-[:WAS_TAUGHT {error_type, at}]->(:Lesson {key, ...})
    (:Lesson)-[:HAS_QUIZ]->(:Quiz {key, variant, questions_json, ...})
    (:Student)-[:WAS_QUIZZED {at}]->(:Quiz)

Every lesson and quiz records how long it took to generate and how many times
it has been served from here instead, which is what dev_tools/content_report.py
reads.

Every function may raise GraphUnavailable. The callers decide what a missing
store costs; none of them treats it as empty.
==========================================================================
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from app.db.neo4j_connection import neo4j_db

# How long a stored lesson is served. Seven days: long enough that a class
# working through one concept over a week shares it, short enough that a change
# to the syllabus notes reaches everyone soon. A prompt change should bump
# lesson_service.PROMPT_VERSION, which retires stored lessons at once.
LESSON_TTL_SECONDS = 7 * 24 * 60 * 60

# Versions of the quiz kept per lesson. Enough that two retakes see new
# questions; few enough that most students are served a stored one.
MAX_QUIZ_VARIANTS = 3

# The fields a lesson is made of, in one place so the write and the read cannot
# disagree about what a stored lesson contains.
LESSON_FIELDS = (
    "issue",
    "explanation",
    "incorrectCode",
    "correctCode",
    "exampleCode",
    "mermaidDiagram",
    "videoUrl",
    "referenceLink",
    "hint",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def age_seconds(moment: str | None) -> float | None:
    """Seconds since an ISO timestamp, or None when there is none to read."""
    if not moment:
        return None
    try:
        parsed = datetime.fromisoformat(moment)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - parsed).total_seconds()


def lesson_key(
    prompt_version: str,
    error_type: str,
    cognitive_state: str,
    code_snippet: str,
    situation_key: str,
) -> str:
    """Everything a lesson was written for, and nothing about who asked."""
    raw = "|".join(
        [
            prompt_version,
            error_type,
            cognitive_state,
            " ".join((code_snippet or "").split()),
            situation_key,
        ]
    )
    return "lesson_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def find_lesson(key: str) -> dict | None:
    """A stored lesson still within its TTL, counting the hit. None otherwise."""
    rows = neo4j_db.execute_query(
        "MATCH (l:Lesson {key: $key}) RETURN l AS lesson",
        {"key": key},
    )
    if not rows:
        return None

    lesson = dict(rows[0]["lesson"])
    age = age_seconds(lesson.get("generated_at"))
    # No readable timestamp means freshness cannot be shown, and a stale lesson
    # is worse than paying for a new one.
    if age is None or age > LESSON_TTL_SECONDS:
        return None

    neo4j_db.execute_query(
        "MATCH (l:Lesson {key: $key}) SET l.hits = coalesce(l.hits, 0) + 1",
        {"key": key},
    )
    return lesson


def save_lesson(key: str, properties: dict) -> None:
    neo4j_db.execute_query(
        """
        MERGE (l:Lesson {key: $key})
        SET l += $properties, l.generated_at = $generated_at, l.hits = 0
        """,
        {"key": key, "properties": properties, "generated_at": _now()},
    )


def record_taught(student_id: str, key: str, error_type: str) -> None:
    """Remember which lesson this student was given, so their quiz can test it."""
    neo4j_db.execute_query(
        """
        MATCH (l:Lesson {key: $key})
        MERGE (s:Student {student_id: $student_id})
        MERGE (s)-[t:WAS_TAUGHT {error_type: $error_type}]->(l)
        SET t.at = $at
        """,
        {"key": key, "student_id": student_id, "error_type": error_type, "at": _now()},
    )


def lesson_taught(student_id: str, error_type: str) -> dict | None:
    """The lesson this student was most recently given for this mistake."""
    rows = neo4j_db.execute_query(
        """
        MATCH (:Student {student_id: $student_id})
              -[t:WAS_TAUGHT {error_type: $error_type}]->(l:Lesson)
        RETURN l AS lesson
        ORDER BY t.at DESC
        LIMIT 1
        """,
        {"student_id": student_id, "error_type": error_type},
    )
    return dict(rows[0]["lesson"]) if rows else None


def quiz_variants(lesson_key_value: str, student_id: str) -> list[dict]:
    """Every stored version of this lesson's quiz, and when this student was given each."""
    rows = neo4j_db.execute_query(
        """
        MATCH (:Lesson {key: $lesson_key})-[:HAS_QUIZ]->(q:Quiz)
        OPTIONAL MATCH (:Student {student_id: $student_id})-[w:WAS_QUIZZED]->(q)
        RETURN q AS quiz, w.at AS served_at
        ORDER BY q.variant ASC
        """,
        {"lesson_key": lesson_key_value, "student_id": student_id},
    )
    variants = []
    for row in rows:
        quiz = dict(row["quiz"])
        quiz["served_at"] = row.get("served_at")
        quiz["questions"] = json.loads(quiz.get("questions_json") or "[]")
        variants.append(quiz)
    return variants


def save_quiz(lesson_key_value: str, variant: int, questions: list[dict], generation_ms: int) -> str:
    key = f"{lesson_key_value}_quiz{variant}"
    neo4j_db.execute_query(
        """
        MATCH (l:Lesson {key: $lesson_key})
        MERGE (q:Quiz {key: $key})
        SET q.variant = $variant,
            q.questions_json = $questions_json,
            q.question_count = $question_count,
            q.generated_at = $generated_at,
            q.generation_ms = $generation_ms,
            q.hits = 0
        MERGE (l)-[:HAS_QUIZ]->(q)
        """,
        {
            "lesson_key": lesson_key_value,
            "key": key,
            "variant": variant,
            "questions_json": json.dumps(questions),
            "question_count": len(questions),
            "generated_at": _now(),
            "generation_ms": generation_ms,
        },
    )
    return key


def record_quizzed(student_id: str, quiz_key: str, *, from_store: bool) -> None:
    """Remember this student was given this version; count it when it was not newly written."""
    neo4j_db.execute_query(
        """
        MATCH (q:Quiz {key: $key})
        MERGE (s:Student {student_id: $student_id})
        MERGE (s)-[w:WAS_QUIZZED]->(q)
        SET w.at = $at
        FOREACH (_ IN CASE WHEN $from_store THEN [1] ELSE [] END |
            SET q.hits = coalesce(q.hits, 0) + 1)
        """,
        {"key": quiz_key, "student_id": student_id, "at": _now(), "from_store": from_store},
    )
