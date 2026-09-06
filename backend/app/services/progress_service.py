from app.db.neo4j_connection import neo4j_db
from app.core.concepts import CONCEPT_TAGS, PREREQUISITE_EDGES, normalise_concept
from app.services import knowledge_tracing
from collections import Counter
from datetime import datetime, timezone

# The platform pass mark, matching Code Coach.
#
# This was 50 here while Code Coach passes at 70 (api/routes/remediation.py and
# gamification.py both use `score_percent >= 70`). So a 2/4 was recorded as
# MASTERED in the progress graph while the very same quiz left the remediation
# trigger unresolved - the dashboard said "Passed" and the student kept being
# told to study it. Two services disagreeing about what passing means is worse
# than either threshold being wrong.
#
# Code Coach owns the decision, so this follows it rather than the reverse.
PASS_MARK_PERCENT = 70


def update_student_progress(student_id: str, concept: str, score: int, total: int):
    """
    Saves a new Quiz Attempt node for the student to maintain a history of their progress,
    instead of overwriting the previous score.
    """
    # The quiz UI posts an error type here (ValidationQuiz.jsx sends
    # `concept: errorType`) while struggle detection uses concept tags, so the
    # graph accumulated Concept nodes under both vocabularies and a student's
    # history split across them. Normalising here rather than at the caller
    # means every writer lands on the same node whichever name it knows.
    concept = normalise_concept(concept)

    percentage = (score / total) * 100 if total > 0 else 0
    status = "MASTERED" if percentage >= PASS_MARK_PERCENT else "NEEDS_REVIEW"

    # UTC, and explicitly marked as such. datetime.now() returned a naive local
    # timestamp, so attempts recorded in different timezones sorted against each
    # other incorrectly on the dashboard timeline - and there was nothing in the
    # stored string to say which zone it had been.
    timestamp = datetime.now(timezone.utc).isoformat()

    # FR-07: how long they spent on the lesson before taking this quiz. None
    # when no lesson-open was recorded, which is a different finding from zero.
    seconds_on_lesson = _seconds_on_lesson(student_id, concept)

    query = """
    MERGE (s:Student {student_id: $student_id})
    MERGE (c:Concept {name: $concept})
    CREATE (s)-[a:ATTEMPTED {
        score: $score,
        total: $total,
        percentage: $percentage,
        status: $status,
        timestamp: $timestamp,
        seconds_on_lesson: $seconds_on_lesson
    }]->(c)
    RETURN a
    """
    
    parameters = {
        "student_id": student_id,
        "concept": concept,
        "score": score,
        "total": total,
        "percentage": percentage,
        "status": status,
        "timestamp": timestamp,
        "seconds_on_lesson": seconds_on_lesson,
    }
    
    try:
        result = neo4j_db.execute_query(query, parameters)
        return {"success": True, "data": result}
    except Exception as e:
        print(f"❌ Progress Update Error: {e}")
        return {"success": False, "error": str(e)}

def get_student_progress(student_id: str):
    """Retrieves all past attempts for the dashboard timeline."""
    query = """
    MATCH (s:Student {student_id: $student_id})-[a:ATTEMPTED]->(c:Concept)
    RETURN c.name AS concept, a.score AS score, a.total AS total,
           a.percentage AS percentage, a.status AS status,
           a.timestamp AS last_updated,
           // FR-07. Written on every attempt but not returned until now, so
           // the dashboard had no way to show it.
           a.seconds_on_lesson AS seconds_on_lesson
    ORDER BY a.timestamp DESC
    """
    try:
        result = neo4j_db.execute_query(query, {"student_id": student_id})
        return {"success": True, "data": result}
    except Exception as e:
        print(f"❌ Progress Fetch Error: {e}")
        return {"success": False, "error": str(e)}

def get_mastery_estimates(student_id: str) -> dict:
    """Per-concept Knowledge Tracing estimates for this student.

    Replaces "average the percentages" as the answer to "how well does this
    student know X". The average is still available on each concept for the
    dashboard, but the number that decides mastery is now BKT's belief - see
    app/services/knowledge_tracing.py for why an average cannot answer the
    question FR-08 asks.
    """
    query = """
    MATCH (s:Student {student_id: $student_id})-[a:ATTEMPTED]->(c:Concept)
    RETURN c.name AS concept, a.score AS score, a.total AS total,
           a.percentage AS percentage, a.timestamp AS timestamp
    ORDER BY a.timestamp ASC
    """

    try:
        rows = neo4j_db.execute_query(query, {"student_id": student_id}) or []
    except Exception as e:
        print(f"❌ Mastery Fetch Error: {e}")
        return {"success": False, "error": str(e)}

    # ORDER BY above is ASC on purpose and load-bearing: BKT is sequential, so
    # feeding it newest-first would trace the student's history backwards and
    # report a learner as a forgetter.
    by_concept: dict[str, list[dict]] = {}
    for row in rows:
        by_concept.setdefault(row["concept"], []).append(row)

    estimates = []
    for concept, attempts in by_concept.items():
        estimate = knowledge_tracing.estimate(concept, attempts).as_dict()
        percentages = [a["percentage"] for a in attempts if a.get("percentage") is not None]
        estimate["average_percentage"] = (
            round(sum(percentages) / len(percentages), 1) if percentages else None
        )
        estimate["attempts"] = len(attempts)
        estimates.append(estimate)

    estimates.sort(key=lambda item: item["probability_known"])
    return {"success": True, "data": estimates}


def get_concept_mastery(student_id: str, concept: str):
    """BKT estimate for a single concept. Used to personalise the lesson prompt."""
    concept = normalise_concept(concept)
    result = get_mastery_estimates(student_id)
    if not result.get("success"):
        return None

    for estimate in result["data"]:
        if estimate["concept"] == concept:
            return estimate
    return None


def record_lesson_opened(student_id: str, concept: str) -> dict:
    """Stamp when this student opened the lesson for this concept.

    FR-07 asks the system to monitor "how the student follows the remediation
    by tracking time spent on the lesson and their accuracy in the associated
    quiz". Accuracy was already recorded; the time was not, because nothing
    stored an opening timestamp to measure from.

    One open time per student and concept, overwritten each time. Re-opening a
    lesson restarts the clock rather than accumulating, which is the reading
    that matches the question being asked: how long did they spend on the
    lesson before attempting the quiz - not how long across all visits, where
    a tab left open overnight would dominate the number.
    """
    concept = normalise_concept(concept)

    query = """
    MERGE (s:Student {student_id: $student_id})
    MERGE (c:Concept {name: $concept})
    MERGE (s)-[v:VIEWED_LESSON]->(c)
    SET v.opened_at = $opened_at
    RETURN v.opened_at AS opened_at
    """

    try:
        neo4j_db.execute_query(
            query,
            {
                "student_id": student_id,
                "concept": concept,
                "opened_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return {"success": True}
    except Exception as e:
        # Best effort. Losing the timing must never cost the student the lesson
        # that was just generated for them.
        print(f"⚠️ Could not record lesson-opened: {e}")
        return {"success": False, "error": str(e)}


def _seconds_on_lesson(student_id: str, concept: str) -> float | None:
    """How long between opening the lesson and finishing the quiz, in seconds.

    None when there is no recorded open - a quiz taken without the lesson, or
    one taken before this was ever recorded. None rather than 0, because "did
    not read it" and "no measurement" are different findings and averaging
    zeros into the first would be wrong.
    """
    query = """
    MATCH (:Student {student_id: $student_id})-[v:VIEWED_LESSON]->(:Concept {name: $concept})
    RETURN v.opened_at AS opened_at
    """

    try:
        rows = neo4j_db.execute_query(query, {"student_id": student_id, "concept": concept})
    except Exception as e:
        print(f"⚠️ Could not read lesson-opened: {e}")
        return None

    opened_at = (rows or [{}])[0].get("opened_at") if rows else None
    if not opened_at:
        return None

    try:
        opened = datetime.fromisoformat(opened_at)
    except (TypeError, ValueError):
        return None

    if opened.tzinfo is None:
        opened = opened.replace(tzinfo=timezone.utc)

    elapsed = (datetime.now(timezone.utc) - opened).total_seconds()

    # A negative value means clock skew; a very large one means a tab left open
    # for a day. Neither is time spent studying, and both would poison an
    # average, so they are reported as no measurement rather than as data.
    if elapsed < 0 or elapsed > 6 * 60 * 60:
        return None

    return round(elapsed, 1)


def get_curriculum(student_id: str) -> dict:
    """Every concept, where the student stands on it, and what it depends on.

    ── Why this exists ─────────────────────────────────────────────────────
    The dashboard only knew about concepts the student had already been
    quizzed on. On a new account that is one row, sometimes none, and the page
    reads as broken when it is simply empty - there is no sense of how much
    there is to learn, where the student is in it, or what to do next.

    This returns all fourteen. Concepts with attempts carry their knowledge
    tracing estimate; the rest are reported honestly as not started rather than
    given a made-up score.

    ── The four states ─────────────────────────────────────────────────────
      mastered     attempted, and knowledge tracing believes it is known
      in_progress  attempted, not yet believed
      ready        not attempted, and every prerequisite is mastered
      locked       not attempted, and something it depends on is not

    "locked" is descriptive, not a restriction - nothing stops a student
    opening it. It answers "why is this not the thing to do next", which a flat
    list of fourteen names cannot.
    """
    estimates_result = get_mastery_estimates(student_id)
    estimates = {
        item["concept"]: item
        for item in (estimates_result.get("data") or [])
    }

    # Direct prerequisites per concept, from the same hand-written edges that
    # are seeded into the graph - read here rather than queried so the page
    # still renders the map when Neo4j is unreachable.
    prerequisites: dict[str, list[str]] = {tag: [] for tag in CONCEPT_TAGS}
    for prereq, dependent in PREREQUISITE_EDGES:
        prerequisites.setdefault(dependent, []).append(prereq)

    concepts = []
    for tag in CONCEPT_TAGS:
        estimate = estimates.get(tag)
        needs = prerequisites.get(tag, [])
        unmet = [
            name
            for name in needs
            if not (estimates.get(name) or {}).get("mastered", False)
        ]

        if estimate and estimate["mastered"]:
            state = "mastered"
        elif estimate:
            state = "in_progress"
        elif unmet:
            state = "locked"
        else:
            state = "ready"

        concepts.append(
            {
                "concept": tag,
                "state": state,
                "prerequisites": needs,
                "unmet_prerequisites": unmet,
                # None, not 0, when never attempted. A zero here would place an
                # untouched concept alongside one the student has failed twice,
                # and those are not the same situation.
                "probability_known": estimate["probability_known"] if estimate else None,
                "predicted_correct": estimate["predicted_correct"] if estimate else None,
                "attempts": estimate["attempts"] if estimate else 0,
                "observations": estimate["observations"] if estimate else 0,
                "average_percentage": estimate["average_percentage"] if estimate else None,
            }
        )

    counts = Counter(item["state"] for item in concepts)

    return {
        "success": True,
        "data": {
            "concepts": concepts,
            "total": len(concepts),
            "counts": {
                "mastered": counts["mastered"],
                "in_progress": counts["in_progress"],
                "ready": counts["ready"],
                "locked": counts["locked"],
            },
            # What to do next: a ready concept the student has not started,
            # earliest in the dependency order. Falls back to whatever they are
            # part-way through when everything available is already underway.
            "suggested_next": next(
                (c["concept"] for c in concepts if c["state"] == "ready"),
                next((c["concept"] for c in concepts if c["state"] == "in_progress"), None),
            ),
        },
    }
