"""Generate a micro-lesson for one student's specific mistake.

The lesson is GENERATED, every time, by a language model, using the student's
cognitive state and the retrieved syllabus context. There is no template and no
fallback: if it cannot be generated, the caller is told so.

============================ WHAT CHANGED, AND WHY ============================
This module used to end every failure path in `get_smart_fallback`, which
returned invented lesson text - a title of "Logical Issue Detected: {error_type}",
an explanation reading "Hello {student_id}, we noticed a struggle with...", a
fixed Mermaid diagram, and a YouTube *search* URL dressed as a reference.

That fallback was being served in place of real output, because the configured
model (`openai/gpt-oss-20b:free` on OpenRouter) no longer exists and the account
has no credits. The endpoint answered 200 the whole time, so it looked like it
was working. It was not.

Both problems are removed together: generation moves to Gemini, which the
platform already uses for embeddings, and the fallback is deleted rather than
repaired. Invented content that reaches a student, a screenshot or a viva is
worse than an honest failure - and an honest failure is the only thing that
makes a broken API key visible.
==============================================================================
"""

import json

from app.core.config import settings
from app.db.neo4j_connection import neo4j_db
from app.services.llm import LLMUnavailable, generate, strip_code_fence
from app.services.ml_service import predict_cognitive_state
from app.services.rag_service import retrieve_context

PROMPT = """
You are 'Code Guru', an expert computer science tutor for first-year IT students.

CRITICAL: You MUST focus ONLY on this specific error: "{error_type}"
Student's Code: "{code_snippet}"

=== MACHINE LEARNING COGNITIVE ANALYSIS ===
Predicted Student Cognitive State: "{cognitive_state}"
INSTRUCTION: If the state is "High Cognitive Load" or "Needs Simple Basics",
explain it extremely simply, step-by-step. If "Minor Syntax Error", give a quick
direct correction.

=== SYLLABUS NOTES (Use ONLY as background context) ===
{context}
======================

Generate a DETAILED, COMPREHENSIVE micro-lesson specifically addressing the
"{error_type}". The "explanation" field MUST be at least 150-200 words. Break
down exactly why the error happens and how to think about the logic correctly.
Do NOT give a generic lesson - it must be specific to the code provided.

Also generate a simple Mermaid.js chart (graph TD) showing the visual breakdown
of THIS specific error. Emit clean mermaid, with no markdown backticks.
Node labels must be plain words only - no parentheses, brackets, braces or
quotes inside a label. Mermaid treats those as syntax and refuses to parse the
whole diagram, so "A[Check index (i)]" loses the student the entire chart.
Write "A[Check the index i]" instead.

Respond with JSON only, exactly in this shape:
{{
    "issue": "A specific 1-sentence title about {error_type}",
    "explanation": "A detailed, step-by-step explanation (MINIMUM 150 words) adapted to the cognitive state and this specific error.",
    "exampleCode": "The student's incorrect code as a comment, and the correct way underneath.",
    "mermaidDiagram": "graph TD\\n A[Step 1] --> B[Step 2]",
    "videoUrl": "A YouTube URL relevant to {error_type}",
    "referenceLink": "A documentation link relevant to {error_type}",
    "hint": "A guiding question specific to {error_type}"
}}
"""

REQUIRED_FIELDS = ("issue", "explanation")


def _extract_json(text: str) -> dict:
    """Pull the JSON object out of a chat response.

    Models wrap JSON in prose and code fences even when told not to, so the
    outermost braces are located rather than trusting the whole response to
    parse. A response that yields no object is a generation failure, not
    something to paper over.
    """
    cleaned = strip_code_fence(text)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise LLMUnavailable("The model did not return a JSON object.")

    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as error:
        raise LLMUnavailable(f"The model returned malformed JSON: {error}") from error


def past_score_for(student_id: str) -> int:
    """The student's average quiz score so far, as a percentage.

    Read from their actual attempt history in the graph. This used to be a
    constant chosen by string-matching the error type - "LOOP" in the name gave
    30, "ARRAY" gave 60, anything else 80 - which meant the cognitive-state
    model's inputs never varied by student and its output was a three-branch
    lookup table wearing a model's name.

    50 for a student with no history: neutral, and the same midpoint the rest of
    the platform treats as the pass mark.
    """
    if not neo4j_db.driver:
        return 50

    rows = neo4j_db.execute_query(
        """
        MATCH (:Student {student_id: $student_id})-[a:ATTEMPTED]->(:Concept)
        RETURN avg(a.percentage) AS average
        """,
        {"student_id": student_id},
    )

    average = (rows or [{}])[0].get("average") if rows else None
    return int(average) if average is not None else 50


def generate_real_lesson(
    student_id: str,
    error_type: str,
    code_snippet: str,
    error_count: int,
) -> dict:
    """Build a lesson, or raise LLMUnavailable.

    Raises rather than returning a placeholder. The API layer turns this into a
    503, so a student is told the lesson could not be built - which is true -
    instead of being shown something invented, which is not.

    `error_count` is the real repeat count behind the trigger, passed down from
    the caller, and `past_score` comes from this student's own attempt history.
    Both used to be constants derived from the error type's spelling.
    """
    cognitive_state = predict_cognitive_state(
        error_count, code_snippet, past_score_for(student_id)
    )
    context = retrieve_context(f"{error_type} {code_snippet}", k=2)

    text = generate(
        PROMPT.format(
            error_type=error_type,
            code_snippet=code_snippet,
            cognitive_state=cognitive_state,
            context=context,
        )
    )

    lesson = _extract_json(text)

    missing = [field for field in REQUIRED_FIELDS if not lesson.get(field)]
    if missing:
        # A response missing the fields the lesson is made of is not a lesson.
        # Filling the gaps with defaults is how a half-generated answer starts
        # looking like a whole one.
        raise LLMUnavailable(f"The generated lesson was missing: {', '.join(missing)}")

    result = {
        "issue": lesson.get("issue", ""),
        "explanation": lesson.get("explanation", ""),
        "exampleCode": lesson.get("exampleCode", ""),
        "mermaidDiagram": lesson.get("mermaidDiagram", ""),
        "videoUrl": lesson.get("videoUrl", ""),
        "referenceLink": lesson.get("referenceLink", ""),
        "hint": lesson.get("hint", ""),
        "cognitive_state": cognitive_state,
    }

    _cache_lesson(error_type, result)
    return result


def _cache_lesson(error_type: str, lesson: dict) -> None:
    """Record the lesson against its error type in the graph.

    Best effort. A cache write that fails must not cost the student the lesson
    that was just generated for them.

    This was commented out with a note about wanting a fresh lesson every time
    while testing. It is back on, because with generation working the cache is
    the difference between one model call and one per view.
    """
    if not neo4j_db.driver:
        return

    try:
        neo4j_db.execute_query(
            """
            MERGE (e:ErrorType {name: $error_type})
            MERGE (l:Lesson {
                issue: $issue,
                explanation: $explanation,
                exampleCode: $exampleCode,
                mermaidDiagram: $mermaidDiagram,
                videoUrl: $videoUrl,
                referenceLink: $referenceLink,
                hint: $hint
            })
            MERGE (e)-[:HAS_LESSON]->(l)
            """,
            {"error_type": error_type, **{k: lesson.get(k, "") for k in (
                "issue", "explanation", "exampleCode", "mermaidDiagram",
                "videoUrl", "referenceLink", "hint")}},
        )
    except Exception as error:  # pragma: no cover - cache is not load-bearing
        print(f"⚠️ Could not cache the lesson: {error}")
