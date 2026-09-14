"""Generate a validation quiz for one student's specific mistake.

The quiz has no fallback: if no usable quiz can be written, the caller is told.

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

========================== EIGHT QUESTIONS, FROM THE LESSON =========================
Four questions was too few to mean much: one lucky guess moved the score 25
points, and the 70% pass mark sat between three and four right answers. A quiz
is now eight questions, each checked before it is asked.

It is written from the lesson the student was actually given rather than from
the bare error type, so it tests what they were taught. And it is kept - see
content_store - with a few versions per lesson, so another student in the same
situation is served it without a new generation, and a retake gets questions
the student has not seen.
==============================================================================
"""

import json
import re
import time

from app.services import content_store
from app.services.llm import LLMUnavailable, generate, strip_code_fence

# How many questions a quiz has, and how many to ask for so that the checks can
# drop a bad one or two without the quiz failing.
QUIZ_LENGTH = 8
QUESTIONS_REQUESTED = 10

# A student given a quiz this recently is coming back to it - a refresh, another
# tab - rather than retaking it, and gets the same one.
RESUME_WINDOW_SECONDS = 2 * 60 * 60

QUESTION_SHAPE = """
Every question has exactly 4 options, all different, and exactly one correct.
"correct_answer" must repeat the correct option's text exactly.

Respond with a JSON array only, exactly in this shape:
[
    {{
        "question": "A specific question?",
        "options": ["First", "Second", "Third", "Fourth"],
        "correct_answer": "Second",
        "explanation": "Why that option is right, in one or two sentences."
    }}
]
"""

LESSON_PROMPT = """
You are 'Code Guru', an expert computer science tutor.
A student struggled with this error: "{error_type}"
They have just been taught this lesson:

=== THE LESSON ===
{issue}

{explanation}

The mistake:
{incorrect_code}

The fix:
{correct_code}
==================

Write exactly {count} multiple choice questions that check whether they
understood THIS lesson. Every question must be answerable from the lesson above;
do not test anything it does not teach. Vary them: some should ask what a short
piece of code does or prints, and some should ask which version of a line is
correct.
""" + QUESTION_SHAPE

ERROR_TYPE_PROMPT = """
You are 'Code Guru', an expert computer science tutor.
The student specifically struggled with this error: "{error_type}"
An example of the mistake: "{code_snippet}"

Write exactly {count} multiple choice questions testing their understanding
ONLY of "{error_type}". Do not ask generic Java questions. Make each one
specific to this mistake.
""" + QUESTION_SHAPE


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


def select_questions(questions: list[dict]) -> list[dict]:
    """The first QUIZ_LENGTH questions worth asking, or raise.

    _normalise keeps anything that can be marked. This keeps only what is fair
    to ask: exactly four options that are actually different - two options
    that read the same once labels and backticks go make a question a coin
    toss - and no question asked twice in one quiz.
    """
    kept: list[dict] = []
    seen: set[str] = set()

    for question in questions:
        text = " ".join(question["question"].split()).lower()
        distinct_options = {_strip_label(option) for option in question["options"]}
        if text in seen or len(question["options"]) != 4 or len(distinct_options) != 4:
            continue
        seen.add(text)
        kept.append(question)
        if len(kept) == QUIZ_LENGTH:
            return kept

    raise LLMUnavailable(
        f"Only {len(kept)} usable questions were generated; a quiz needs {QUIZ_LENGTH}."
    )


def _write_quiz(prompt: str) -> tuple[list[dict], int]:
    started = time.monotonic()
    text = generate(prompt)
    generation_ms = int((time.monotonic() - started) * 1000)
    return select_questions(_normalise(_extract_json(text))), generation_ms


def generate_validation_quiz(
    student_id: str, error_type: str, code_snippet: str = ""
) -> list[dict]:
    """The quiz for this student and mistake, or raise LLMUnavailable."""
    questions, _generated = quiz_for(student_id, error_type, code_snippet)
    return questions


def quiz_for(student_id: str, error_type: str, code_snippet: str = "") -> tuple[list[dict], bool]:
    """The questions, and whether a new quiz had to be written for them."""
    lesson = _taught_lesson(student_id, error_type)

    if lesson is None:
        # No lesson on record - the quiz page opened directly, or the lesson
        # could not be stored. Written from the mistake itself, and not kept:
        # there is nothing to hang it on that another student would look up.
        questions, _ = _write_quiz(
            ERROR_TYPE_PROMPT.format(
                error_type=error_type,
                code_snippet=code_snippet,
                count=QUESTIONS_REQUESTED,
            )
        )
        return questions, True

    variants = _variants(lesson["key"], student_id)
    if variants:
        chosen = choose_variant(variants)
        if chosen is not None:
            _record_quizzed(student_id, chosen["key"], from_store=True)
            return chosen["questions"], False

    questions, generation_ms = _write_quiz(
        LESSON_PROMPT.format(
            error_type=error_type,
            issue=lesson.get("issue", ""),
            explanation=lesson.get("explanation", ""),
            incorrect_code=lesson.get("incorrectCode", ""),
            correct_code=lesson.get("correctCode", ""),
            count=QUESTIONS_REQUESTED,
        )
    )

    if variants is not None:
        quiz_key = _save_variant(lesson["key"], len(variants) + 1, questions, generation_ms)
        if quiz_key:
            _record_quizzed(student_id, quiz_key, from_store=False)

    return questions, True


def choose_variant(variants: list[dict]) -> dict | None:
    """Which stored version to hand this student, or None to write a new one."""
    served = [v for v in variants if v.get("served_at")]

    def served_recently(variant: dict) -> bool:
        # An explicit None check. `age or inf` read a quiz served moments ago as
        # never served, because on a coarse clock "moments ago" measures 0.0 -
        # so a student coming straight back was handed a newly written quiz.
        age = content_store.age_seconds(variant["served_at"])
        return age is not None and age < RESUME_WINDOW_SECONDS

    # 1. The one they were given recently: they are coming back to it.
    recent = [v for v in served if served_recently(v)]
    if recent:
        return max(recent, key=lambda v: v["served_at"])

    # 2. A version they have not had.
    unseen = [v for v in variants if not v.get("served_at")]
    if unseen:
        return unseen[0]

    # 3. They have had every version: write another, until there are enough.
    if len(variants) < content_store.MAX_QUIZ_VARIANTS:
        return None

    # 4. Enough versions: the one they saw longest ago.
    return min(served, key=lambda v: v["served_at"])


# ── Best effort around the store ─────────────────────────────────────────────
# Any of these failing costs a stored quiz, never the quiz itself.
def _taught_lesson(student_id: str, error_type: str) -> dict | None:
    try:
        return content_store.lesson_taught(student_id, error_type)
    except Exception as error:
        print(f"⚠️ Could not read which lesson was taught: {error}")
        return None


def _variants(lesson_key: str, student_id: str) -> list[dict] | None:
    try:
        return content_store.quiz_variants(lesson_key, student_id)
    except Exception as error:
        print(f"⚠️ Could not read stored quizzes: {error}")
        return None


def _save_variant(lesson_key: str, variant: int, questions: list[dict], generation_ms: int) -> str | None:
    try:
        return content_store.save_quiz(lesson_key, variant, questions, generation_ms)
    except Exception as error:
        print(f"⚠️ Could not store the quiz: {error}")
        return None


def _record_quizzed(student_id: str, quiz_key: str, *, from_store: bool) -> None:
    try:
        content_store.record_quizzed(student_id, quiz_key, from_store=from_store)
    except Exception as error:
        print(f"⚠️ Could not record which quiz was given: {error}")
