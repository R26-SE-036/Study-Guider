"""Learning paths: what a student needs to understand before the thing they keep failing.

This is the query the graph database exists for.

Study Guider's other Neo4j usage is two join tables - a student's attempts, and
a cached lesson per error type - and a reviewer is right to ask why that is not
a relational schema. This is the answer: a variable-depth walk backwards up the
prerequisite chain, filtered at every level against the same student's own
history, returning whole paths rather than rows.

    MATCH path = (prereq:Concept)-[:PREREQUISITE_OF*1..4]->(target:Concept)

In SQL that is a recursive CTE that re-joins the attempt table once per level
and still cannot return the path as a first-class value. In Cypher it is the
five lines below.
"""

from app.core.concepts import normalise_concept
from app.db.neo4j_connection import neo4j_db

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

# Below this, a concept is not considered understood. Matches the pass mark
# progress_service applies when it writes the attempt.
MASTERY_PERCENTAGE = 50


def get_learning_path(student_id: str, concept: str):
    """Un-mastered prerequisites for `concept`, nearest first.

    Returns the concepts standing between this student and the one they are
    stuck on - skipping any they have already demonstrated - so the caller can
    teach the earliest gap rather than re-teaching the symptom.
    """
    target = normalise_concept(concept)
    if not target:
        return {"success": False, "error": "A concept is required."}

    # `NOT EXISTS { ... }` rather than an OPTIONAL MATCH and a null check: this
    # is an anti-join, and writing it as one lets Neo4j stop at the first
    # matching attempt instead of collecting them all to discard them.
    #
    # The path is returned reversed because the traversal runs from prerequisite
    # to target, and a student wants to read it in the order they should study.
    query = f"""
    MATCH path = (prereq:Concept)-[:PREREQUISITE_OF*1..{MAX_PREREQUISITE_DEPTH}]->(target:Concept)
    WHERE target.name = $target
      AND NOT EXISTS {{
        (:Student {{student_id: $student_id}})
          -[a:ATTEMPTED]->(prereq)
        WHERE a.percentage >= {MASTERY_PERCENTAGE}
      }}
    RETURN prereq.name AS concept,
           length(path) AS steps_away
    ORDER BY steps_away ASC, concept ASC
    """

    try:
        rows = neo4j_db.execute_query(
            query, {"target": target, "student_id": student_id}
        )
    except Exception as error:  # pragma: no cover - driver/network failure
        print(f"❌ Learning Path Error: {error}")
        return {"success": False, "error": str(error)}

    if rows is None:
        # execute_query returns None when the driver is absent - a
        # configuration or connectivity failure, not an empty result. Saying
        # "no prerequisites" here would read as "you are ready for this".
        return {"success": False, "error": "Graph database unavailable."}

    # One concept can sit on several paths to the target at different depths
    # (arithmetic_operations reaches loop_boundaries directly and via
    # assignment_logic). Keep the shortest, which the ORDER BY has put first.
    seen, prerequisites = set(), []
    for row in rows:
        name = row.get("concept")
        if name and name not in seen:
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
