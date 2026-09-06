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
from datetime import datetime, timezone

from app.core.config import settings
from app.db.neo4j_connection import neo4j_db
from app.services.llm import LLMUnavailable, generate, strip_code_fence
from app.services import learning_path_service, progress_service
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

=== THIS STUDENT'S RECORD (from the knowledge graph) ===
{graph_context}
INSTRUCTION: Use this to pitch the lesson. If a prerequisite below is listed as
not yet mastered, explain that idea briefly BEFORE the error itself - the error
is a symptom of the gap, not the gap. If they have attempted this concept
before, acknowledge it rather than teaching it as if for the first time.
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


def build_graph_context(student_id: str, concept_tag: str) -> str:
    """What the knowledge graph knows about THIS student and THIS concept.

    This is the "Graph" half of Graph RAG, and it was missing. The pipeline
    retrieved syllabus text and stopped there, so every student with the same
    error got the same lesson - which is retrieval-augmented, but not
    personalised, and the proposal claims both.

    Two things go in: how well BKT believes they know the concept, and which of
    its prerequisites they have not mastered. The second is the more useful of
    the two, because a student failing at array indexing because they never got
    loop boundaries needs to be taught loop boundaries, and no amount of
    explaining array indexing will do it.

    Returns plain prose rather than JSON: it is going into a prompt, and a
    model reads a sentence more reliably than it reads a nested object.
    """
    if not concept_tag:
        return "No concept tag was supplied, so no record could be looked up."

    lines: list[str] = []

    try:
        mastery = progress_service.get_concept_mastery(student_id, concept_tag)
    except Exception as error:  # pragma: no cover - the lesson matters more
        print(f"⚠️ Could not read mastery for the prompt: {error}")
        mastery = None

    if mastery:
        lines.append(
            f"- Concept '{concept_tag}': {mastery['attempts']} quiz attempt(s), "
            f"average {mastery['average_percentage']}%. Knowledge-tracing belief "
            f"they know it: {mastery['probability_known']:.0%}"
            f"{' (mastered)' if mastery['mastered'] else ' (not yet mastered)'}."
        )
    else:
        lines.append(
            f"- Concept '{concept_tag}': no quiz attempts yet. This is the first "
            "time they are being taught it."
        )

    try:
        gaps = learning_path_service.unmastered_prerequisites(student_id, concept_tag)
    except Exception as error:  # pragma: no cover
        print(f"⚠️ Could not read prerequisites for the prompt: {error}")
        gaps = []

    if gaps:
        listed = ", ".join(gap["concept"] for gap in gaps)
        lines.append(f"- Prerequisites they have NOT mastered: {listed}.")
    else:
        lines.append("- No unmastered prerequisites stand in front of this concept.")

    return "\n".join(lines)


def generate_real_lesson(
    student_id: str,
    error_type: str,
    code_snippet: str,
    error_count: int,
    concept_tag: str = "",
    force_regenerate: bool = False,
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

    # Before spending a model call, check whether this exact lesson already
    # exists. Lessons were being cached and never read, so a page refresh cost
    # a full generation - which is where most of the API quota was going.
    if not force_regenerate:
        cached = _cached_lesson(student_id, error_type, cognitive_state)
        if cached:
            print(f"Lesson cache HIT for {error_type} / {cognitive_state}")
            return {**cached, "cognitive_state": cognitive_state, "cached": True}

    context = retrieve_context(f"{error_type} {code_snippet}", k=2)
    graph_context = build_graph_context(student_id, concept_tag)

    text = generate(
        PROMPT.format(
            error_type=error_type,
            code_snippet=code_snippet,
            cognitive_state=cognitive_state,
            context=context,
            graph_context=graph_context,
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
        "cached": False,
        "issue": lesson.get("issue", ""),
        "explanation": lesson.get("explanation", ""),
        "exampleCode": lesson.get("exampleCode", ""),
        "mermaidDiagram": lesson.get("mermaidDiagram", ""),
        "videoUrl": lesson.get("videoUrl", ""),
        "referenceLink": lesson.get("referenceLink", ""),
        "hint": lesson.get("hint", ""),
        "cognitive_state": cognitive_state,
    }

    _cache_lesson(student_id, error_type, cognitive_state, result)
    return result


# How long a cached lesson stays usable. Seven days: long enough that a student
# working through one concept over a week never pays for regeneration, short
# enough that a change to the prompt or the syllabus reaches everyone quickly.
CACHE_TTL_SECONDS = 7 * 24 * 60 * 60

# Fields that make up a lesson, in one place so the read and the write cannot
# disagree about what a cached lesson contains.
LESSON_FIELDS = (
    "issue",
    "explanation",
    "exampleCode",
    "mermaidDiagram",
    "videoUrl",
    "referenceLink",
    "hint",
)


def _cached_lesson(student_id: str, error_type: str, cognitive_state: str) -> dict | None:
    """A lesson already generated for this student, error and state.

    ── Why this function did not exist, and why it matters ──────────────────
    Lessons were being WRITTEN to the graph and never read back. Every request
    called the model, including a page refresh on a lesson the student had just
    read - so re-opening a lesson cost a full generation, and the API quota was
    being spent on content that already existed.

    ── Why the key includes the student ─────────────────────────────────────
    It would be cheaper to cache per error type alone, and that is what the
    write did. It is now wrong to: the prompt carries this student's mastery
    and their unmastered prerequisites, so a generated lesson can open with
    "you have practiced this before". Serving that to a different student would
    be a lie the cache invented, which is worse than the cost it saves.

    Cognitive state is in the key for the same reason - it changes how the
    lesson is pitched, so a lesson written for "Needs Simple Basics" is not the
    one to hand back when the student is now on "Minor Syntax Error".
    """
    if not neo4j_db.driver:
        return None

    try:
        rows = neo4j_db.execute_query(
            """
            MATCH (s:Student {student_id: $student_id})
                  -[c:CACHED_LESSON {error_type: $error_type,
                                     cognitive_state: $cognitive_state}]->(l:Lesson)
            RETURN l AS lesson, c.generated_at AS generated_at
            ORDER BY c.generated_at DESC
            LIMIT 1
            """,
            {
                "student_id": student_id,
                "error_type": error_type,
                "cognitive_state": cognitive_state,
            },
        )
    except Exception as error:  # pragma: no cover - a cache miss is not fatal
        print(f"⚠️ Could not read the lesson cache: {error}")
        return None

    row = (rows or [None])[0]
    if not row or not row.get("lesson"):
        return None

    generated_at = row.get("generated_at")
    if generated_at:
        try:
            age = (
                datetime.now(timezone.utc) - datetime.fromisoformat(generated_at)
            ).total_seconds()
            if age > CACHE_TTL_SECONDS:
                return None
        except (TypeError, ValueError):
            # An unparseable timestamp means we cannot prove it is fresh, and a
            # stale lesson is worse than paying for a new one.
            return None

    lesson = dict(row["lesson"])
    return {field: lesson.get(field, "") for field in LESSON_FIELDS}


def _cache_lesson(
    student_id: str, error_type: str, cognitive_state: str, lesson: dict
) -> None:
    """Record the lesson so the next request does not have to generate it.

    Best effort. A cache write that fails must not cost the student the lesson
    that was just generated for them.
    """
    if not neo4j_db.driver:
        return

    try:
        neo4j_db.execute_query(
            """
            MERGE (s:Student {student_id: $student_id})
            CREATE (l:Lesson {
                issue: $issue,
                explanation: $explanation,
                exampleCode: $exampleCode,
                mermaidDiagram: $mermaidDiagram,
                videoUrl: $videoUrl,
                referenceLink: $referenceLink,
                hint: $hint
            })
            CREATE (s)-[:CACHED_LESSON {
                error_type: $error_type,
                cognitive_state: $cognitive_state,
                generated_at: $generated_at
            }]->(l)
            """,
            {
                "student_id": student_id,
                "error_type": error_type,
                "cognitive_state": cognitive_state,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                **{field: lesson.get(field, "") for field in LESSON_FIELDS},
            },
        )
    except Exception as error:  # pragma: no cover - cache is not load-bearing
        print(f"⚠️ Could not cache the lesson: {error}")
