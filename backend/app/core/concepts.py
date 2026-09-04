"""The concept vocabulary, and the prerequisite graph over it.

============================ WHY THIS EXISTS ============================
The live graph had `Concept` nodes under two different naming systems:

    ARRAY_LENGTH_INDEX_MISUSE     INCORRECT_CONDITIONAL_OPERATOR
    MISSING_BREAK_IN_SWITCH       loop_boundaries
    conditional_logic

The SCREAMING_CASE ones are Code Coach ERROR TYPES; the snake_case ones are
its CONCEPT TAGS. They are different levels of the same idea - an error type is
a specific mistake, a concept tag is what the student has not understood - and
several error types map onto one concept.

They ended up mixed because the quiz UI posts `concept: errorType` to
/api/progress/update while every other path uses the concept tag. So a
student's quiz result on array indexing was recorded against a node called
ARRAY_LENGTH_INDEX_MISUSE, and their struggle data against `array_indexing`,
and the two never joined. Progress under-reported, silently, and the more a
student used the quizzes the more fragmented their history became.

Normalising at the write boundary rather than in the caller is deliberate: the
frontend is being replaced, and a backend should not trust the caller to pick
the right vocabulary anyway.

The mapping is Code Coach's, from knowledge_base/code_coach_errors.json. It is
duplicated here rather than imported because that file lives in a different
repository and Study Guider must not depend on a sibling's checkout. If Code
Coach adds an error type, add it here too - `normalise_concept` degrades
safely, so the cost of being briefly out of date is a lowercase passthrough
rather than a crash.
=========================================================================
"""

from typing import Optional

# ── Code Coach error type -> the concept it belongs to ──
# Verbatim from code-coach/knowledge_base/code_coach_errors.json.
# Note DUPLICATE_IF_ELSE_CONDITION and INCORRECT_CONDITIONAL_OPERATOR both map
# to conditional_logic: the mapping is many-to-one by design.
ERROR_TYPE_TO_CONCEPT = {
    "OFF_BY_ONE_LOOP_BOUNDARY": "loop_boundaries",
    "INCORRECT_CONDITIONAL_OPERATOR": "conditional_logic",
    "ARRAY_LENGTH_INDEX_MISUSE": "array_indexing",
    "STRING_EQUALITY_WITH_OPERATOR": "string_comparison",
    "LOOP_UPDATE_WRONG_DIRECTION": "loop_control",
    "UNREACHABLE_CODE_AFTER_RETURN": "control_flow",
    "MISSING_BREAK_IN_SWITCH": "switch_statements",
    "EMPTY_CONDITIONAL_BODY": "statement_structure",
    "SELF_ASSIGNMENT": "assignment_logic",
    "ALWAYS_TRUE_OR_CONDITION": "boolean_logic",
    "IGNORED_STRING_METHOD_RESULT": "immutable_strings",
    "DIVISION_BY_ZERO_LITERAL": "arithmetic_operations",
    "CONSTANT_FALSE_LOOP_CONDITION": "loop_initialization",
    "DUPLICATE_IF_ELSE_CONDITION": "conditional_logic",
    "WHILE_VARIABLE_NOT_UPDATED": "loop_termination",
}

# The 14 canonical concept tags - the values above, deduplicated.
CONCEPT_TAGS = sorted(set(ERROR_TYPE_TO_CONCEPT.values()))


def normalise_concept(value: Optional[str]) -> Optional[str]:
    """Return the canonical concept tag for an error type or a concept tag.

    Accepts either vocabulary so callers on both sides of the rename keep
    working, and is idempotent, so running it over already-clean data is safe.

    An unrecognised value is lowercased and returned rather than rejected. A
    concept this service has not heard of is far more likely to be a new one
    Code Coach added than an attack, and refusing it would throw away a
    student's quiz result over a vocabulary lag.
    """
    if not value:
        return None

    text = value.strip()
    if not text:
        return None

    mapped = ERROR_TYPE_TO_CONCEPT.get(text.upper())
    if mapped:
        return mapped

    return text.lower()


# ── The prerequisite graph ──
#
# (prerequisite) -[:PREREQUISITE_OF]-> (dependent)
#
# This is what earns Neo4j its place in this architecture. Everything else the
# service stores in the graph - a student's attempts, a cached lesson - is two
# join tables wearing graph labels, and a reviewer is right to ask why it is
# not a relational schema. The answer has to be a query that SQL expresses
# badly, and this is one:
#
#     "given a concept this student keeps failing, what un-mastered chain of
#      prerequisites leads to it?"
#
# That is a variable-depth traversal with a per-node filter against the same
# student's history. In Cypher it is five lines (see learning_path_service);
# in SQL it is a recursive CTE that has to re-join the attempt table at every
# level.
#
# The ordering below is a pedagogical claim, not a fact - it says roughly what
# a Java beginner needs before what. It is the starting point for review with
# the component owner, not a finding.
PREREQUISITE_EDGES = [
    # Assignment is the root: everything else needs a variable first.
    ("assignment_logic", "arithmetic_operations"),
    ("assignment_logic", "boolean_logic"),

    # Conditions are boolean expressions before they are control flow.
    ("boolean_logic", "conditional_logic"),
    ("conditional_logic", "statement_structure"),
    ("conditional_logic", "control_flow"),
    ("conditional_logic", "switch_statements"),

    # A loop is an assignment plus a condition, then its own concerns.
    ("assignment_logic", "loop_initialization"),
    ("conditional_logic", "loop_initialization"),
    ("loop_initialization", "loop_control"),
    ("loop_control", "loop_termination"),
    ("loop_control", "loop_boundaries"),
    ("arithmetic_operations", "loop_boundaries"),

    # Indexing is where off-by-one stops being abstract.
    ("loop_boundaries", "array_indexing"),

    # Strings: comparison first, then why the result has to be assigned.
    ("boolean_logic", "string_comparison"),
    ("string_comparison", "immutable_strings"),
]


def find_cycles() -> list:
    """Return any cycle in PREREQUISITE_EDGES, as a list of concept names.

    A cycle would make the learning-path traversal below either loop or return
    nonsense ("to learn X, first learn X"), and it is the one way a hand-edited
    ordering can be wrong that is not obvious by reading it. Called by the
    bootstrap script before anything is written to the graph.
    """
    adjacency: dict = {}
    for prereq, dependent in PREREQUISITE_EDGES:
        adjacency.setdefault(prereq, []).append(dependent)

    visiting, done = set(), set()

    def walk(node, trail):
        if node in visiting:
            return trail[trail.index(node):] + [node]
        if node in done:
            return None
        visiting.add(node)
        for nxt in adjacency.get(node, []):
            found = walk(nxt, trail + [node])
            if found:
                return found
        visiting.discard(node)
        done.add(node)
        return None

    for start in list(adjacency):
        cycle = walk(start, [])
        if cycle:
            return cycle
    return []
