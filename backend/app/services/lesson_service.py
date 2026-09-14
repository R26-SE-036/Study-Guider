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
import time
from dataclasses import dataclass

from app.core.config import settings
from app.db.neo4j_connection import GraphUnavailable, neo4j_db
from app.services.llm import LLMUnavailable, generate, strip_code_fence
from app.services import content_store, learning_path_service, progress_service
from app.services.ml_service import predict_cognitive_state
from app.services.rag_service import FOUND, UNAVAILABLE, RetrievedNotes, retrieve_notes

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

"incorrectCode" and "correctCode" must be the SAME few lines of code, once
broken and once fixed, so they can be read side by side. Put no `//` comment
markers in front of the code itself in either field - the interface labels which
is which and colours them, so commenting the broken version out makes it
unreadable and hides the very thing the student is meant to look at. A short
explanatory comment INSIDE the code is fine where it earns its place.

Respond with JSON only, exactly in this shape:
{{
    "issue": "A specific 1-sentence title about {error_type}",
    "explanation": "A detailed, step-by-step explanation (MINIMUM 150 words) adapted to the cognitive state and this specific error.",
    "incorrectCode": "ONLY the broken code, as real runnable-looking Java. Do NOT comment it out. Do NOT include the fix.",
    "correctCode": "ONLY the corrected version of the same code. Do NOT comment it out. Do NOT include the broken version.",
    "mermaidDiagram": "graph TD\\n A[Step 1] --> B[Step 2]",
    "videoUrl": "A YouTube URL relevant to {error_type}",
    "referenceLink": "A documentation link relevant to {error_type}",
    "hint": "A guiding question specific to {error_type}"
}}
"""

REQUIRED_FIELDS = ("issue", "explanation")


def split_legacy_example(example: str) -> tuple[str, str]:
    """Separate a pre-2026-09 `exampleCode` blob into (incorrect, correct).

    ── Why this exists ─────────────────────────────────────────────────────
    The prompt used to ask for "the student's incorrect code as a comment, and
    the correct way underneath", so a lesson arrived as one block in which the
    broken version was commented out:

        // Incorrect: missing break causes fall-through
        // switch (day) {
        //     case 1:
        // }

        switch (day) {
            case 1:
                break;
        }

    Rendered as a single grey block that is genuinely hard to read: the part the
    student most needs to look at is the part styled as a comment, and nothing
    says which half is which.

    New lessons carry `incorrectCode` and `correctCode` separately. This exists
    only for the ones already cached in the graph - up to seven days of them -
    and for any that a model still returns in the old shape. It is a heuristic
    on purpose: a lesson from the old format is worth showing well, but not
    worth building a Java parser for.

    Returns ("", "") when the blob has no commented section, because a blob that
    is entirely live code cannot be split into a wrong half and a right half,
    and inventing a division would be worse than showing it unchanged.
    """
    if not example:
        return "", ""

    commented: list[str] = []
    plain: list[str] = []

    for raw in example.splitlines():
        stripped = raw.strip()

        if stripped.startswith("//"):
            # Drop the marker and at most ONE following space - the space the
            # comment convention adds. Everything after it is the code's own
            # indentation, and flattening it turns a nested switch into a list
            # of unrelated lines, which is most of what made the old rendering
            # hard to read in the first place.
            body = stripped[2:]
            if body.startswith(" "):
                body = body[1:]

            # A label line ("Incorrect: ...", "Correct: ...") is prose about the
            # code rather than code, and the interface supplies its own heading.
            if _is_label(body.lstrip()):
                continue

            commented.append(body)
        else:
            plain.append(raw)

    if not commented:
        return "", ""

    return ("\n".join(commented).strip(), "\n".join(plain).strip())


_LABEL_PREFIXES = (
    "incorrect",
    "correct",
    "wrong",
    "right",
    "bad",
    "good",
    "before",
    "after",
    "fixed",
    "broken",
)


def _is_label(comment_body: str) -> bool:
    """Is this comment a heading for the block rather than part of the code?"""
    lowered = comment_body.lower()
    return any(
        lowered.startswith(prefix) and (":" in lowered[: len(prefix) + 2] or lowered == prefix)
        for prefix in _LABEL_PREFIXES
    )


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
    try:
        rows = neo4j_db.execute_query(
            """
            MATCH (:Student {student_id: $student_id})-[a:ATTEMPTED]->(:Concept)
            RETURN avg(a.percentage) AS average
            """,
            {"student_id": student_id},
        )
    except GraphUnavailable:
        # Unknown rather than "no history", but the cognitive-state rubric needs
        # a number, and the neutral midpoint is the one that sways it least. The
        # lesson already reports that the student's record could not be read.
        return 50

    average = (rows or [{}])[0].get("average") if rows else None
    return int(average) if average is not None else 50


# Bump when PROMPT changes in a way that should retire the lessons already
# stored. It is part of every lesson's key, so old lessons simply stop matching.
PROMPT_VERSION = "2026-09-14"

# Whether the student's record was actually read, for the lesson's grounding.
RECORD_READ = "read"
RECORD_UNAVAILABLE = "unavailable"
RECORD_NOT_LOOKED_UP = "no_concept"

# Knowledge-tracing belief below this reads as "still finds it hard".
EARLY_BELIEF = 0.5


@dataclass(frozen=True)
class StudentSituation:
    """What a lesson may assume about a student, at a grain students can share.

    ── Why bands, not numbers ──────────────────────────────────────────────
    The prompt used to carry "3 quiz attempts, average 55%, 41% belief". That
    made every lesson one student's, so none could be reused - and at twenty
    generations a day for the whole project, a lesson per student per mistake
    is most of the budget gone by the tenth student.

    A band is what the lesson actually changes on: never quizzed, still finds
    it hard, part of the way there, or probably a slip. Together with the
    prerequisites they have not mastered, it is everything the lesson needs to
    be pitched right, and it is the same for every student in it.
    """

    record: str
    band: str = "unknown"
    gaps: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        return f"{self.record}|{self.band}|{','.join(self.gaps)}"


def student_situation(student_id: str, concept_tag: str) -> StudentSituation:
    """This student's situation on this concept, from the knowledge graph.

    The "Graph" half of Graph RAG: how well BKT believes they know the concept,
    and which of its prerequisites they have not mastered. The second is the
    more useful, because a student failing at array indexing because they never
    got loop boundaries needs loop boundaries taught, and no amount of
    explaining array indexing will do it.

    "Could not read it" is its own situation. It used to come out as "no quiz
    attempts yet - this is the first time they are being taught it", so while
    the graph was unreachable a student with six attempts was taught from
    scratch, and told so.
    """
    if not concept_tag:
        return StudentSituation(RECORD_NOT_LOOKED_UP)

    try:
        mastery = progress_service.get_concept_mastery(student_id, concept_tag)
        gaps = learning_path_service.unmastered_prerequisites(student_id, concept_tag)
    except Exception as error:  # the lesson matters more than the record
        print(f"⚠️ Student record unavailable for the prompt: {error}")
        return StudentSituation(RECORD_UNAVAILABLE)

    if not mastery:
        band = "none"
    elif mastery["mastered"]:
        band = "mastered"
    elif mastery["probability_known"] < EARLY_BELIEF:
        band = "early"
    else:
        band = "developing"

    return StudentSituation(
        RECORD_READ,
        band,
        tuple(sorted({gap["concept"] for gap in gaps})),
    )


_BAND_PROMPT = {
    "none": "- They have not taken a quiz on '{concept}' yet, so teach it as new.",
    "early": (
        "- They have met '{concept}' before and still find it hard: knowledge "
        "tracing believes they probably do not know it yet. Say that they have "
        "seen it before, and rebuild it from the ground up."
    ),
    "developing": (
        "- They have met '{concept}' before and are part of the way there: "
        "knowledge tracing is not yet confident they know it. Say so, and "
        "concentrate on the part that still trips them up."
    ),
    "mastered": (
        "- Knowledge tracing believes they know '{concept}', so this is probably "
        "a slip. Keep the lesson short and direct."
    ),
}


def situation_prompt(concept_tag: str, situation: StudentSituation) -> str:
    """The student's record in words that stay true for everyone sharing the lesson."""
    if situation.record == RECORD_NOT_LOOKED_UP:
        return "No concept tag was supplied, so no record could be looked up."
    if situation.record == RECORD_UNAVAILABLE:
        return (
            "- This student's record could not be read, so nothing is known about "
            "their history with this concept. Do not assume this is their first "
            "time, and do not mention past attempts, progress or prerequisites."
        )

    lines = [_BAND_PROMPT[situation.band].format(concept=concept_tag)]
    if situation.gaps:
        lines.append(f"- Prerequisites they have NOT mastered: {', '.join(situation.gaps)}.")
    else:
        lines.append("- No unmastered prerequisites stand in front of this concept.")
    return "\n".join(lines)


def _notes_for_prompt(notes: RetrievedNotes) -> str:
    """The notes, or an instruction not to pretend there were any."""
    if notes.status == FOUND:
        return notes.text
    if notes.status == UNAVAILABLE:
        return (
            "No syllabus notes could be retrieved for this lesson. Explain from "
            "general Java knowledge, and do not refer to the notes, the syllabus "
            "or course material."
        )
    return (
        "The syllabus has no notes on this particular error. Explain from general "
        "Java knowledge, and do not claim to be quoting course material."
    )


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
    return lesson_for(
        student_id,
        error_type,
        code_snippet,
        concept_tag,
        cognitive_state,
        force_regenerate=force_regenerate,
    )


def lesson_for(
    student_id: str,
    error_type: str,
    code_snippet: str,
    concept_tag: str,
    cognitive_state: str,
    *,
    force_regenerate: bool = False,
) -> dict:
    """The lesson for this student's situation: a stored one if there is one.

    Separate from generate_real_lesson so pregeneration can ask for a given
    cognitive state directly and land on exactly the key a real student in that
    state will look up.

    The result carries `grounding` - whether syllabus notes were found, found
    nothing, or could not be reached, and whether the student's record was read -
    and `unmet_prerequisites`, which the lesson page shows as what to look at
    first.
    """
    situation = student_situation(student_id, concept_tag)
    key = content_store.lesson_key(
        PROMPT_VERSION, error_type, cognitive_state, code_snippet, situation.key
    )
    # A lesson written without the student's record cannot be matched to anyone
    # else's situation, so it is neither served from the store nor added to it.
    shareable = situation.record != RECORD_UNAVAILABLE

    if shareable and not force_regenerate:
        stored = _stored_lesson(key)
        if stored:
            print(f"Lesson store HIT for {error_type} / {cognitive_state} / {situation.key}")
            _record_taught(student_id, key, error_type)
            return _lesson_response(stored, cognitive_state, situation, cached=True)

    notes = retrieve_notes(f"{error_type} {code_snippet}", k=2)

    started = time.monotonic()
    text = generate(
        PROMPT.format(
            error_type=error_type,
            code_snippet=code_snippet,
            cognitive_state=cognitive_state,
            context=_notes_for_prompt(notes),
            graph_context=situation_prompt(concept_tag, situation),
        )
    )
    generation_ms = int((time.monotonic() - started) * 1000)

    lesson = _extract_json(text)

    missing = [field for field in REQUIRED_FIELDS if not lesson.get(field)]
    if missing:
        # A response missing the fields the lesson is made of is not a lesson.
        # Filling the gaps with defaults is how a half-generated answer starts
        # looking like a whole one.
        raise LLMUnavailable(f"The generated lesson was missing: {', '.join(missing)}")

    # A model may still answer in the old single-field shape whatever the
    # prompt says, so the split is applied to whatever it returns rather than
    # trusting it to have followed instructions.
    incorrect = lesson.get("incorrectCode", "") or ""
    correct = lesson.get("correctCode", "") or ""
    example = lesson.get("exampleCode", "") or ""

    if not (incorrect and correct) and example:
        incorrect, correct = split_legacy_example(example)

    fields = {
        "issue": lesson.get("issue", ""),
        "explanation": lesson.get("explanation", ""),
        "incorrectCode": incorrect,
        "correctCode": correct,
        # Kept so a client written against the old shape still gets something,
        # and so a blob that could not be split is still shown rather than lost.
        "exampleCode": example,
        "mermaidDiagram": lesson.get("mermaidDiagram", ""),
        "videoUrl": lesson.get("videoUrl", ""),
        "referenceLink": lesson.get("referenceLink", ""),
        "hint": lesson.get("hint", ""),
        "syllabus_notes": notes.status,
        "student_record": situation.record,
    }

    # Only a lesson written with the notes and the student's record in front of
    # it is kept. One written during an outage would otherwise go on being
    # served - still ungrounded - for a week after the graph came back.
    if notes.status == FOUND and shareable:
        _store_lesson(
            key,
            {
                **fields,
                "error_type": error_type,
                "concept_tag": concept_tag,
                "cognitive_state": cognitive_state,
                "situation": situation.key,
                "prompt_version": PROMPT_VERSION,
                "generation_ms": generation_ms,
            },
        )
        _record_taught(student_id, key, error_type)

    return _lesson_response(fields, cognitive_state, situation, cached=False)


def _lesson_response(
    stored: dict, cognitive_state: str, situation: StudentSituation, *, cached: bool
) -> dict:
    return {
        "cached": cached,
        **{field: stored.get(field, "") or "" for field in content_store.LESSON_FIELDS},
        "cognitive_state": cognitive_state,
        "grounding": {
            "syllabus_notes": stored.get("syllabus_notes") or "unknown",
            "student_record": stored.get("student_record") or "unknown",
        },
        "unmet_prerequisites": list(situation.gaps),
    }


# ── Best effort around the store ─────────────────────────────────────────────
# A lesson that was just written, or could have been, must never be lost
# because the store could not be read or written. Each failure is logged.
def _stored_lesson(key: str) -> dict | None:
    try:
        return content_store.find_lesson(key)
    except Exception as error:
        print(f"⚠️ Could not read the lesson store: {error}")
        return None


def _store_lesson(key: str, properties: dict) -> None:
    try:
        content_store.save_lesson(key, properties)
    except Exception as error:
        print(f"⚠️ Could not store the lesson: {error}")


def _record_taught(student_id: str, key: str, error_type: str) -> None:
    try:
        content_store.record_taught(student_id, key, error_type)
    except Exception as error:
        print(f"⚠️ Could not record which lesson was taught: {error}")
