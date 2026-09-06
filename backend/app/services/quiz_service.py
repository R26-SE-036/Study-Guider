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
import re

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


def _resolve_answer(answer, options: list) -> str | None:
    """Return the option `answer` refers to, or None if it refers to none.

    The model does not answer consistently, and the difference is invisible
    until it bites. Asked about a bare error type it replies with the whole
    option text; given a code snippet in the same prompt it replies "B". Both
    are reasonable readings of "correct_answer", and an exact string comparison
    accepts the first and rejects the second - so every question was dropped,
    `_normalise` raised, and the endpoint answered 503. Roughly half the time,
    depending on the prompt.

    Accepted, in order: the option text itself; a letter (B, b, "B)", "(B)");
    a 1-based number; a 0-based index. Anything else is genuinely unusable and
    the question is dropped, because a question whose answer is not among its
    options cannot be marked.
    """
    if answer is None:
        return None

    text = str(answer).strip()
    if not text:
        return None

    # 1. The option text, verbatim.
    for option in options:
        if text.lower() == str(option).strip().lower():
            return str(option)

    # 2. The same text once any A)/B./(C)/"D " label is removed from BOTH
    #    sides. This covers every combination of who carries the label:
    #    the model labels its answer and not the options ("A `for (...)`" vs
    #    "`for (...)`"), or labels the options and not the answer, or labels
    #    both differently.
    #
    #    Comparing stripped-to-stripped is what makes it safe to treat a bare
    #    "A " as a label. An answer that genuinely begins with the article -
    #    "A loop that runs once" - strips to "loop that runs once", and so does
    #    the option it matches, so it still pairs correctly. And step 1 has
    #    already returned for anything that matched exactly.
    stripped = _strip_label(text)
    if stripped:
        for option in options:
            if stripped == _strip_label(str(option)):
                return str(option)

    # 3. A bare label with nothing after it: B, b, "B)", "(B)", "B."
    label = re.match(r"^\(?\s*([A-Za-z])\s*[).:\-]?\s*$", text)
    if label:
        index = ord(label.group(1).upper()) - ord("A")
        if 0 <= index < len(options):
            return str(options[index])

    # 4. A label with text after it that matched no option above - trust the
    #    letter, since the text disagreeing with every option is more likely a
    #    paraphrase than a fifth answer.
    answer_label = re.match(r"^\(?\s*([A-Za-z])\s*[).:\-]\s+\S", text)
    if answer_label:
        index = ord(answer_label.group(1).upper()) - ord("A")
        if 0 <= index < len(options):
            return str(options[index])

    # 5. A number: 1-based first, since a model writing "3" for a four-option
    #    question almost always means the third.
    if text.isdigit():
        number = int(text)
        if 1 <= number <= len(options):
            return str(options[number - 1])
        if 0 <= number < len(options):
            return str(options[number])

    return None


def _strip_label(text: str) -> str:
    """Drop a leading option label, and normalise for comparison.

    Backticks go too: the model routinely writes an answer as `code` and the
    option as plain code, or the reverse, and that difference is presentational
    rather than a different answer.
    """
    without_label = re.sub(r"^\(?\s*[A-Za-z]\s*[).:\-]?\s+", "", text.strip())
    return without_label.replace("`", "").strip().lower()


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

        # An answer that refers to no option makes the question unmarkable: the
        # student cannot pick it, so they cannot be right.
        resolved = _resolve_answer(answer, options)
        if resolved is None:
            continue

        questions.append(
            {
                "question": str(question),
                "options": [str(o) for o in options],
                # The RESOLVED option text, not what the model wrote. The web
                # app marks the quiz by comparing the option the student
                # clicked against this string, so storing a bare "B" here would
                # mark every answer wrong even though the question parsed fine.
                "correct_answer": resolved,
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
