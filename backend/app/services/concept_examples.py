"""Representative Java snippets, one per Code Coach error type.

Why these exist:

A remediation trigger tells Study Guider *which concept* a student keeps
getting wrong, but not what they actually typed. Code Coach stores only a
SHA-256 prefix of the code context around each diagnostic
(`codeContextHash` in code_coach_service.py), never the source itself — a
deliberate privacy choice, and not one to work around.

So when a lesson is generated from a trigger rather than from a live editor
session, there is no student code to feed the model. An empty snippet produces
a vague, abstract lesson. A short canonical example of the same mistake gives
the model something concrete to explain while being honest about what it is:
an illustration, not the student's own work. The UI labels it that way.

Keyed by Code Coach's error_type values (see its knowledge_base/
code_coach_errors.json).
"""

CONCEPT_EXAMPLES: dict[str, str] = {
    "ARRAY_LENGTH_INDEX_MISUSE": (
        "int[] marks = new int[5];\n"
        "// length is 5, so the last valid index is 4\n"
        "System.out.println(marks[marks.length]);"
    ),
    "OFF_BY_ONE_LOOP_BOUNDARY": (
        "int[] marks = new int[5];\n"
        "// <= runs one iteration too many\n"
        "for (int i = 0; i <= marks.length; i++) {\n"
        "    System.out.println(marks[i]);\n"
        "}"
    ),
    "INCORRECT_CONDITIONAL_OPERATOR": (
        "int total = 0;\n"
        "// = assigns, == compares\n"
        "if (total = 10) {\n"
        "    System.out.println(\"Total is ten\");\n"
        "}"
    ),
    "MISSING_BREAK": (
        "switch (grade) {\n"
        "    case 'A':\n"
        "        System.out.println(\"Excellent\");\n"
        "        // no break, so execution falls into the next case\n"
        "    case 'B':\n"
        "        System.out.println(\"Good\");\n"
        "        break;\n"
        "}"
    ),
    "WHILE_NOT_UPDATED": (
        "int count = 0;\n"
        "// count never changes, so this never ends\n"
        "while (count < 5) {\n"
        "    System.out.println(count);\n"
        "}"
    ),
}

DEFAULT_EXAMPLE = (
    "int[] values = new int[3];\n"
    "for (int i = 0; i <= values.length; i++) {\n"
    "    System.out.println(values[i]);\n"
    "}"
)


def example_for(error_type: str) -> str:
    """A short snippet showing the mistake this error type describes."""
    return CONCEPT_EXAMPLES.get(error_type, DEFAULT_EXAMPLE)
