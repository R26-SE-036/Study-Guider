"""Generate a validation quiz for one student's specific mistake.

Like the lesson, the quiz is generated every time and has no fallback.

============================ WHAT CHANGED, AND WHY ============================
`get_smart_quiz_fallback` returned four fixed multiple-choice questions - the
first being "Regarding '{error_type}', what is the best practice?" with the
answer "Check operators and boundaries carefully". Those questions were being
served instead of generated ones, because the configured model no longer exists
and the account has no credits, and the endpoint answered 200 throughout.

A quiz matters more than a lesson here, because its score decides whether a
remediation trigger resolves. Four canned questions that are the same for every
error type mean the pass mark measures nothing about the concept the student
actually struggled with - and Code Coach then records that concept as mastered.

Generation moves to Gemini and the fallback is deleted.
==============================================================================
"""

import json

from app.services.llm import LLMUnavailable, generate, strip_code_fence

PROMPT = """
You are 'Code Guru', an expert computer science tutor.
The student specifically struggled with this error: "{error_type}"
Their exact code was: "{code_snippet}"

CRITICAL: Generate exactly 4 multiple choice questions testing their
understanding ONLY of "{error_type}". Do not ask generic Java questions. Make
each one specific to the mistake they made.

Respond with a JSON array only, exactly in this shape:
[
    {{
        "question": "Specific question about {error_type}?",
        "options": ["Option A", "Option B", "Option C", "Option D"],
        "correct_answer": "Option B",
        "explanation": "Clear explanation."
    }}
]
"""


def _extract_json(text: str):
    """Pull the JSON array out of a chat response."""
    cleaned = strip_code_fence(text)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # An array, or an object wrapping one.
    for opener, closer in (("[", "]"), ("{", "}")):
        start, end = cleaned.find(opener), cleaned.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                continue

    raise LLMUnavailable("The model did not return valid JSON.")


def _normalise(data) -> list[dict]:
    """Coerce the response into a list of well-formed questions, or raise.

    Models return the array under a `questions` or `quiz` key often enough to be
    worth unwrapping, and name the fields `choices`/`answer` about as often as
    `options`/`correct_answer`. Those are shape differences and worth absorbing.

    A question missing its options or its answer is NOT a shape difference - it
    cannot be asked or marked - so it is dropped, and if nothing survives that
    is a generation failure.
    """
    if isinstance(data, dict):
        data = data.get("questions") or data.get("quiz") or data.get("data")

    if not isinstance(data, list) or not data:
        raise LLMUnavailable("The model did not return a list of questions.")

    questions = []
    for item in data:
        if not isinstance(item, dict):
            continue

        options = item.get("options") or item.get("choices")
        answer = item.get("correct_answer") or item.get("answer")
        question = item.get("question")

        if not question or not isinstance(options, list) or len(options) < 2 or not answer:
            continue

        # An answer that is not among the options makes the question unmarkable:
        # the student cannot pick it, so they cannot be right.
        if not any(str(answer).strip().lower() == str(o).strip().lower() for o in options):
            continue

        questions.append(
            {
                "question": str(question),
                "options": [str(o) for o in options],
                "correct_answer": str(answer),
                "explanation": str(item.get("explanation") or ""),
            }
        )

    if not questions:
        raise LLMUnavailable("No usable questions were generated.")

    return questions


def generate_validation_quiz(
    student_id: str, error_type: str, code_snippet: str = ""
) -> list[dict]:
    """Build a quiz, or raise LLMUnavailable.

    `student_id` is unused in the prompt and kept only because callers pass it;
    the quiz is about the concept, not the person.
    """
    text = generate(PROMPT.format(error_type=error_type, code_snippet=code_snippet))
    return _normalise(_extract_json(text))
