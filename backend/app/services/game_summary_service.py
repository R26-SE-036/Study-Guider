"""Game session summaries from the Adaptive Gamification Engine.

============================== WHY THIS IS SEPARATE ==============================
FR-12 of the gamification proposal asks that engine to "transmit a performance
summary to the external Progress Tracker component via a defined REST API after
every session". This is the receiving end.

Game summaries are stored as `:GamePlay` nodes with their own relationship type,
`PLAYED`, and they are DELIBERATELY NOT part of the `ATTEMPTED` path that the
progress dashboard and knowledge tracing read.

That separation is the whole point, and it is worth being precise about why.
`progress_service.get_mastery_estimates` runs Bayesian Knowledge Tracing over
`ATTEMPTED` relationships, treating every quiz question as one observation of
"does this student know the concept". A game round is not the same kind of
evidence:

  * Its score is not a proportion of questions answered correctly. It is
    100 minus 15 per hint minus 10 per extra attempt, so a student who gets the
    right answer after two hints scores 70 - a number BKT would read as "seven
    questions in ten correct", which is not what happened.
  * Difficulty varies per round by design, and BKT has no notion of it.
  * Hints are free help inside a game and absent from a quiz.

Mixing them would not enrich the mastery estimate, it would corrupt it, and the
corruption would be invisible - the numbers would still look like probabilities.
So the games get their own store, their own read path, and no edge into the one
the dashboard uses.

============================== WHAT IT IS FOR ==============================
Two things, neither of which needs to touch mastery:

  1. The engine can satisfy FR-12 by transmitting to a component that keeps the
     record, rather than relying on a browser to do it.
  2. Study Guider can eventually show "you have practised this concept in the
     games" alongside its own lessons, as context rather than as evidence.
"""

from datetime import datetime, timezone

from app.core.concepts import normalise_concept
from app.db.neo4j_connection import neo4j_db

# The engine's own vocabulary, accepted as-is. Study Guider does not validate
# the game type against a list: the engine owns that vocabulary and adds to it
# (CodeFix arrived after this integration was designed), and rejecting an
# unrecognised value here would mean a new game silently stops being recorded.
MAX_SUMMARIES = 100


def record_game_summary(student_id: str, summary: dict) -> dict:
    """Store one completed game round.

    The concept is normalised through the same table the quiz path uses, so a
    game on `loop_boundaries` and a quiz on `OFF_BY_ONE_LOOP_BOUNDARY` land on
    one `Concept` node rather than two. That is the one thing the two paths do
    share - what a concept IS - and keeping it consistent is what allows the two
    records to be read side by side later without a join that guesses.
    """
    concept = normalise_concept(summary.get("concept_tag"))
    if not concept:
        return {"success": False, "error": "concept_tag is required"}

    game_session_id = summary.get("game_session_id")
    if not game_session_id:
        return {"success": False, "error": "game_session_id is required"}

    parameters = {
        "student_id": student_id,
        "concept": concept,
        "game_session_id": game_session_id,
        "game_type": summary.get("game_type") or "",
        "difficulty_level": summary.get("difficulty_level") or "",
        "score": _number(summary.get("score")),
        "error_count": _number(summary.get("error_count")),
        "hint_usage": _number(summary.get("hint_usage")),
        "attempt_count": _number(summary.get("attempt_count")),
        "time_taken_seconds": _number(summary.get("time_taken_seconds")),
        # Provenance, carried through rather than recomputed. The engine knows
        # whether it measured these or took the client's word; discarding that
        # here would leave Study Guider unable to tell a counted error from a
        # 0/1 flag.
        "error_count_measured": bool(summary.get("error_count_measured")),
        "hint_usage_measured": bool(summary.get("hint_usage_measured")),
        "was_exploratory": bool(summary.get("was_exploratory")),
        "data_source": summary.get("data_source") or "real",
        "support_action": summary.get("support_action") or "",
        "played_at": summary.get("played_at") or datetime.now(timezone.utc).isoformat(),
        "received_at": datetime.now(timezone.utc).isoformat(),
    }

    # MERGE on game_session_id, not CREATE. The engine sends this after every
    # round and a retry must not double-count; the id is the engine's own and
    # unique per session.
    query = """
    MERGE (s:Student {student_id: $student_id})
    MERGE (c:Concept {name: $concept})
    MERGE (g:GamePlay {game_session_id: $game_session_id})
    SET g.game_type = $game_type,
        g.difficulty_level = $difficulty_level,
        g.score = $score,
        g.error_count = $error_count,
        g.hint_usage = $hint_usage,
        g.attempt_count = $attempt_count,
        g.time_taken_seconds = $time_taken_seconds,
        g.error_count_measured = $error_count_measured,
        g.hint_usage_measured = $hint_usage_measured,
        g.was_exploratory = $was_exploratory,
        g.data_source = $data_source,
        g.support_action = $support_action,
        g.played_at = $played_at,
        g.received_at = $received_at
    MERGE (s)-[:PLAYED]->(g)
    MERGE (g)-[:PRACTISED]->(c)
    RETURN g.game_session_id AS game_session_id
    """

    try:
        result = neo4j_db.execute_query(query, parameters)
        return {"success": True, "data": (result or [{}])[0]}
    except Exception as error:
        print(f"❌ Game summary write failed: {error}")
        return {"success": False, "error": str(error)}


def get_game_summaries(student_id: str, limit: int = 50) -> dict:
    """This student's recorded game rounds, newest first.

    Read from `PLAYED`, never from `ATTEMPTED`. A caller wanting mastery asks
    progress_service; a caller wanting "what have they been playing" asks here.
    """
    query = """
    MATCH (s:Student {student_id: $student_id})-[:PLAYED]->(g:GamePlay)-[:PRACTISED]->(c:Concept)
    RETURN c.name AS concept,
           g.game_session_id AS game_session_id,
           g.game_type AS game_type,
           g.difficulty_level AS difficulty_level,
           g.score AS score,
           g.error_count AS error_count,
           g.hint_usage AS hint_usage,
           g.attempt_count AS attempt_count,
           g.time_taken_seconds AS time_taken_seconds,
           g.error_count_measured AS error_count_measured,
           g.hint_usage_measured AS hint_usage_measured,
           g.support_action AS support_action,
           g.played_at AS played_at
    ORDER BY g.played_at DESC
    LIMIT $limit
    """

    try:
        rows = neo4j_db.execute_query(
            query,
            {"student_id": student_id, "limit": min(int(limit or 50), MAX_SUMMARIES)},
        )
        return {"success": True, "data": rows or []}
    except Exception as error:
        print(f"❌ Game summary read failed: {error}")
        return {"success": False, "error": str(error)}


def _number(value) -> float:
    """A finite number, or 0. Never None - Neo4j would store a null property."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if number == number and number not in (float("inf"), float("-inf")) else 0.0
