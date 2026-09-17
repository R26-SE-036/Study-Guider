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
    # These two were keyed MISSING_BREAK and WHILE_NOT_UPDATED - names Code
    # Coach has never sent - so both lessons silently taught from the default
    # off-by-one example instead. tests/test_concept_examples.py now holds
    # every key to a real error type.
    "MISSING_BREAK_IN_SWITCH": (
        "switch (grade) {\n"
        "    case 'A':\n"
        "        System.out.println(\"Excellent\");\n"
        "        // no break, so execution falls into the next case\n"
        "    case 'B':\n"
        "        System.out.println(\"Good\");\n"
        "        break;\n"
        "}"
    ),
    "WHILE_VARIABLE_NOT_UPDATED": (
        "int count = 0;\n"
        "// count never changes, so this never ends\n"
        "while (count < 5) {\n"
        "    System.out.println(count);\n"
        "}"
    ),
    "INTEGER_DIVISION_IN_DECIMAL_CONTEXT": (
        "int total = 7;\n"
        "int count = 2;\n"
        "// both are ints, so 7 / 2 is 3 before it ever becomes a double\n"
        "double average = total / count;"
    ),
    "DECIMAL_EQUALITY_COMPARISON": (
        "double price = 0.1 + 0.2;\n"
        "// 0.1 + 0.2 is 0.30000000000000004, not exactly 0.3\n"
        "if (price == 0.3) {\n"
        "    System.out.println(\"Exactly thirty cents\");\n"
        "}"
    ),
    "POSTFIX_INCREMENT_ASSIGNED_BACK": (
        "int count = 0;\n"
        "// count++ hands back the old value, which is stored straight back\n"
        "count = count++;\n"
        "System.out.println(count);"
    ),
    "ALWAYS_FALSE_AND_CONDITION": (
        "int age = 20;\n"
        "// no age is both over 65 and under 18\n"
        "if (age > 65 && age < 18) {\n"
        "    System.out.println(\"Discount applies\");\n"
        "}"
    ),
    # The ten below were taught from DEFAULT_EXAMPLE - an off-by-one for loop -
    # so a lesson on string comparison or unreachable code was illustrated with
    # a loop boundary. Every mapped error type now has its own.
    "ALWAYS_TRUE_OR_CONDITION": (
        "int score = 40;\n"
        "// every score is above 0 or below 100, so this is always true\n"
        "if (score > 0 || score < 100) {\n"
        "    System.out.println(\"Valid score\");\n"
        "}"
    ),
    "CONSTANT_FALSE_LOOP_CONDITION": (
        "// i starts at 10, which is not less than 0, so the body never runs\n"
        "for (int i = 10; i < 0; i++) {\n"
        "    System.out.println(i);\n"
        "}"
    ),
    "DIVISION_BY_ZERO_LITERAL": (
        "int total = 90;\n"
        "// dividing an int by 0 throws ArithmeticException\n"
        "int average = total / 0;"
    ),
    "DUPLICATE_IF_ELSE_CONDITION": (
        "int mark = 75;\n"
        "if (mark >= 50) {\n"
        "    System.out.println(\"Pass\");\n"
        "} else if (mark >= 50) {\n"
        "    // the same test again, so this branch can never run\n"
        "    System.out.println(\"Merit\");\n"
        "}"
    ),
    "EMPTY_CONDITIONAL_BODY": (
        "int age = 15;\n"
        "// the semicolon ends the if, so the block below always runs\n"
        "if (age >= 18);\n"
        "{\n"
        "    System.out.println(\"Allowed to vote\");\n"
        "}"
    ),
    "IGNORED_STRING_METHOD_RESULT": (
        "String name = \"  ada  \";\n"
        "// trim() returns a new string; this one is thrown away\n"
        "name.trim();\n"
        "System.out.println(\"[\" + name + \"]\");"
    ),
    "LOOP_UPDATE_WRONG_DIRECTION": (
        "// i starts below 10 and counts down, so it never reaches 10\n"
        "for (int i = 0; i < 10; i--) {\n"
        "    System.out.println(i);\n"
        "}"
    ),
    "SELF_ASSIGNMENT": (
        "public class Student {\n"
        "    private String name;\n"
        "\n"
        "    public Student(String name) {\n"
        "        // assigns the parameter to itself; the field stays null\n"
        "        name = name;\n"
        "    }\n"
        "}"
    ),
    "STRING_EQUALITY_WITH_OPERATOR": (
        "Scanner input = new Scanner(System.in);\n"
        "String answer = input.nextLine();\n"
        "// == compares references, not the characters\n"
        "if (answer == \"yes\") {\n"
        "    System.out.println(\"Confirmed\");\n"
        "}"
    ),
    "UNREACHABLE_CODE_AFTER_RETURN": (
        "static int square(int n) {\n"
        "    return n * n;\n"
        "    // the method has already returned, so this never runs\n"
        "    System.out.println(\"Squared \" + n);\n"
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
