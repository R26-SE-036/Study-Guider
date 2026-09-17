"""Learning paths: what a student needs to understand before the thing they keep failing.

This is the query the graph database exists for.

Study Guider's other Neo4j usage is two join tables - a student's attempts, and
a cached lesson per error type - and a reviewer is right to ask why that is not
a relational schema. This is the answer: a variable-depth walk backwards up the
prerequisite chain, returning whole paths rather than rows.

    MATCH path = (prereq:Concept)-[:PREREQUISITE_OF*1..4]->(target:Concept)

In SQL that is a recursive CTE that re-joins the table once per level and still
cannot return the path as a first-class value. In Cypher it is the few lines
below.
"""

from app.core.concepts import normalise_concept
from app.db.neo4j_connection import neo4j_db
from app.services import progress_service

# How far back up the chain to look.
#
# The graph is four layers deep (assignment_logic -> boolean_logic ->
# conditional_logic -> loop_initialization -> loop_control -> ...), so 4 reaches
# the root from anywhere in it. Unbounded `*` would work today and become a
# performance question the moment the graph grows, and an unbounded traversal
# over a cyclic graph does not terminate at all - the bootstrap script checks
# for cycles, but the bound is what makes that a safety net rather than the only
# defence.
MAX_PREREQUISITE_DEPTH = 4


def mastered_concepts(student_id: str) -> set[str]:
    """Concepts knowledge tracing believes this student knows.

    ── One meaning of "mastered" ───────────────────────────────────────────
    This used to be a Cypher filter: any single attempt at 50% or more cleared a
    prerequisite. Everywhere else - the curriculum map, the lesson's mastery
    band - mastered means knowledge tracing's belief is at least 0.95. So one
    4/8 quiz took loop_boundaries off a lesson's "not yet mastered" list while
    the learning map on the progress page still showed it In progress, and the
    lesson and the map disagreed about the same student.

    Read in Python rather than in the traversal because BKT is sequential over
    every question answered; it is not a property one attempt row carries.
    """
    estimates = progress_service.get_mastery_estimates(student_id).get("data") or []
    return {estimate["concept"] for estimate in estimates if estimate.get("mastered")}


def get_learning_path(student_id: str, concept: str):
    """Un-mastered prerequisites for `concept`, nearest first.

    Returns the concepts standing between this student and the one they are
    stuck on - skipping any knowledge tracing says they already know - so the
    caller can teach the earliest gap rather than re-teaching the symptom.
    """
    target = normalise_concept(concept)
    if not target:
        return {"success": False, "error": "A concept is required."}

    # The path is returned reversed because the traversal runs from prerequisite
    # to target, and a student wants to read it in the order they should study.
    query = f"""
    MATCH path = (prereq:Concept)-[:PREREQUISITE_OF*1..{MAX_PREREQUISITE_DEPTH}]->(target:Concept)
    WHERE target.name = $target
    RETURN prereq.name AS concept,
           length(path) AS steps_away
    ORDER BY steps_away ASC, concept ASC
    """

    # GraphUnavailable propagates and main.py answers 503. Saying "no
    # prerequisites" here instead would read as "you are ready for this".
    rows = neo4j_db.execute_query(query, {"target": target})
    mastered = mastered_concepts(student_id)

    # One concept can sit on several paths to the target at different depths
    # (arithmetic_operations reaches loop_boundaries directly and via
    # assignment_logic). Keep the shortest, which the ORDER BY has put first.
    seen, prerequisites = set(), []
    for row in rows:
        name = row.get("concept")
        if name and name not in seen and name not in mastered:
            seen.add(name)
            prerequisites.append({"concept": name, "steps_away": row.get("steps_away")})

    return {
        "success": True,
        "data": {
            "concept": target,
            "unmastered_prerequisites": prerequisites,
            # The earliest gap - where teaching should actually start. Deepest
            # in the chain, so last in the list.
            "start_here": prerequisites[-1]["concept"] if prerequisites else target,
        },
    }


def unmastered_prerequisites(student_id: str, concept: str) -> list[dict]:
    """Just the gaps, for callers that do not need the whole envelope.

    Used by the lesson prompt. Raises GraphUnavailable when the graph cannot be
    reached, so the caller can tell "no gaps" from "could not look" - and the
    lesson reports which one it was written with.
    """
    result = get_learning_path(student_id, concept)
    if not result.get("success"):
        return []
    return result["data"]["unmastered_prerequisites"]
