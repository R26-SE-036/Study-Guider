"""The language model Study Guider generates lessons and quizzes with.

============================ WHY THIS FILE EXISTS ============================
It has been rewritten twice, for reasons worth keeping.

FIRST: the model was `openai/gpt-oss-20b:free` on OpenRouter. That slug stopped
existing and the account had no credits, so every generation failed - and every
failure fell into a hardcoded fallback that returned invented lesson text and
four canned quiz questions with a 200. The service looked healthy while serving
nothing it had generated. Gemini replaced it and the fallbacks were deleted
rather than repaired.

SECOND: this called Gemini through `langchain_google_genai`. That broke on the
current models. Gemini 3.x are *thinking* models: their response parts carry a
`thoughtSignature`, and the wrapper treats such parts as internal reasoning and
strips them - so `response.content` came back as an empty string and the caller
raised "the language model returned an empty response". The model was answering
perfectly; the text was being discarded on the way out. Verified against the
REST API, which returned `finishReason: STOP` and the text intact.

So generation now uses `google-genai`, Google's own SDK, directly. One less
abstraction over an API that is changing quickly, and the response parsing is
explicit here rather than somewhere it can silently change under us.

Embeddings still go through langchain in app/db/vector_index.py, because that
path works and shares the same key.

THIRD: the free Gemini tier answers 503 "high demand" in bursts. A quiz, written
live and the longest generation, failed on every lesson in user testing. Two
changes: a Gemini 503 is retried briefly before giving up, and LLM_PROVIDER=openai
writes with OpenAI instead - paid credit that is cheaper than Gemini's prepay
minimum. Embeddings stay on Gemini either way.

Nothing here falls back. If the model cannot answer, the caller raises and the
API returns 503. A student is told the lesson could not be generated, which is
true, instead of being shown something invented, which is not.
==============================================================================
"""

from __future__ import annotations

import time

from app.core.config import settings


class LLMUnavailable(RuntimeError):
    """Generation could not happen. Never substitute content for this."""


class LLMQuotaExhausted(LLMUnavailable):
    """The provider's usage limit is used up. Waiting, not retrying, fixes it.

    Its own type because the student needs to be told something different. "Try
    again shortly" is wrong advice when the free tier allows twenty generations
    a day for the whole project: shortly, it fails the same way.
    """


# What a student is told when the daily limit is reached. Not a time: the
# allowance resets on the provider's clock, and a promise of "tomorrow morning"
# would be wrong for most of the day.
DAILY_LIMIT_MESSAGE = (
    "Code Guru has used up today's allowance for writing new lessons and quizzes. "
    "Anything you have already opened still works, and new ones can be written "
    "again when the daily allowance resets."
)


_client = None


def get_client():
    """The Gemini client, or raise LLMUnavailable.

    Built once and reused. Raising rather than returning None is deliberate: a
    None that callers have to remember to check is how the fallbacks got there
    in the first place.
    """
    global _client

    if _client is not None:
        return _client

    if not settings.GEMINI_API_KEY:
        raise LLMUnavailable(
            "GEMINI_API_KEY is not set, so lessons and quizzes cannot be generated."
        )

    try:
        from google import genai

        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
        return _client
    except Exception as error:
        raise LLMUnavailable(f"Could not initialise the language model: {error}") from error


def _text_from(response) -> str:
    """Pull the answer out of a response, thinking models included.

    `response.text` is the normal path. It is not always populated on a
    thinking model, so the parts are walked as a fallback - skipping any part
    flagged as internal reasoning, and keeping the rest.

    This function is the whole reason for dropping the previous wrapper: the
    old one silently returned "" here, which is indistinguishable from the
    model refusing to answer, and sent the caller down a 503 path for a
    response that had actually succeeded.
    """
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text

    collected: list[str] = []
    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            # `thought=True` marks a reasoning part, which is not the answer.
            # A part carrying only a thoughtSignature alongside real text is
            # still the answer, which is exactly what the old wrapper got wrong.
            if getattr(part, "thought", False):
                continue
            part_text = getattr(part, "text", None)
            if isinstance(part_text, str) and part_text.strip():
                collected.append(part_text)

    return "".join(collected)


def _is_quota_error(error: Exception) -> bool:
    """A 429 / RESOURCE_EXHAUSTED from Gemini (google.genai.errors.ClientError)."""
    return getattr(error, "code", None) == 429 or str(getattr(error, "status", "")) == "RESOURCE_EXHAUSTED"


def _is_busy_error(error: Exception) -> bool:
    """A 503 UNAVAILABLE ("high demand") or 500 from Gemini: worth one more try.

    Not a 404 or a 400. Those say the request itself is wrong, and asking again
    only makes the student wait longer for the same failure.
    """
    return getattr(error, "code", None) in (500, 503) or str(getattr(error, "status", "")) in (
        "UNAVAILABLE",
        "INTERNAL",
    )


# The waits between tries when Gemini is busy, and the most time retrying may
# add. The web app's proxy gives up after 45 s and a quiz takes about 18 s to
# write, so a retry that starts after 25 s would finish after the student has
# already been shown the error.
GEMINI_RETRY_DELAYS = (2.0, 5.0)
GEMINI_RETRY_BUDGET_SECONDS = 25.0


def generate(prompt: str) -> str:
    """Run a prompt with the configured provider and return the text, or raise LLMUnavailable."""
    if settings.LLM_PROVIDER == "openai":
        return _generate_openai(prompt)
    if settings.LLM_PROVIDER != "gemini":
        raise LLMUnavailable(f"LLM_PROVIDER must be 'gemini' or 'openai', not {settings.LLM_PROVIDER!r}.")
    return _generate_gemini(prompt)


def _generate_gemini(prompt: str) -> str:
    client = get_client()
    started = time.monotonic()

    for attempt in range(len(GEMINI_RETRY_DELAYS) + 1):
        try:
            response = client.models.generate_content(
                model=settings.MODEL_NAME,
                contents=prompt,
            )
            break
        except Exception as error:
            if _is_quota_error(error):
                raise LLMQuotaExhausted(f"The language model's usage limit is reached: {error}") from error
            if _is_busy_error(error) and attempt < len(GEMINI_RETRY_DELAYS):
                delay = GEMINI_RETRY_DELAYS[attempt]
                if time.monotonic() - started + delay < GEMINI_RETRY_BUDGET_SECONDS:
                    print(f"⚠️ Gemini is busy ({getattr(error, 'code', '?')}); trying again in {delay:.0f} s.")
                    time.sleep(delay)
                    continue
            # Network, a model id that is no longer served to this key, a server
            # error. No content was generated, and none should be invented.
            raise LLMUnavailable(f"The language model did not answer: {error}") from error

    text = _text_from(response)
    if not text.strip():
        # Worth naming the finish reason. An empty answer because the model was
        # cut off by a safety filter or a token limit is a different problem
        # from an empty answer because the response was parsed wrongly, and
        # without this they look identical in the logs.
        reason = None
        for candidate in getattr(response, "candidates", None) or []:
            reason = getattr(candidate, "finish_reason", None)
            break
        raise LLMUnavailable(
            f"The language model returned an empty response (finish reason: {reason})."
        )

    return text


_openai_client = None


def get_openai_client():
    """The OpenAI client, or raise LLMUnavailable. Built once and reused."""
    global _openai_client

    if _openai_client is not None:
        return _openai_client

    if not settings.OPENAI_API_KEY:
        raise LLMUnavailable(
            "LLM_PROVIDER is openai but OPENAI_API_KEY is not set, so lessons and quizzes cannot be generated."
        )

    try:
        from openai import OpenAI

        # The SDK already retries a rate limit, a 5xx and a dropped connection,
        # twice with backoff, so there is no retry loop here. 40 s per try keeps
        # one slow answer inside the web app's 45 s proxy limit.
        _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=40.0, max_retries=2)
        return _openai_client
    except Exception as error:
        raise LLMUnavailable(f"Could not initialise the language model: {error}") from error


def _generate_openai(prompt: str) -> str:
    client = get_openai_client()

    options = {}
    if settings.OPENAI_REASONING_EFFORT:
        options["reasoning"] = {"effort": settings.OPENAI_REASONING_EFFORT}

    try:
        response = client.responses.create(model=settings.MODEL_NAME, input=prompt, **options)
    except Exception as error:
        # A 429 that survives the SDK's own retries is either the rate limit
        # held for a while or, more likely, the prepaid credit running out
        # ("insufficient_quota"). Either way waiting is the fix, not retrying.
        if getattr(error, "status_code", None) == 429:
            raise LLMQuotaExhausted(f"The language model's usage limit is reached: {error}") from error
        raise LLMUnavailable(f"The language model did not answer: {error}") from error

    text = getattr(response, "output_text", None) or ""
    if not text.strip():
        # "incomplete" with a reason (max_output_tokens, content_filter) is a
        # different problem from a response that was parsed wrongly.
        details = getattr(response, "incomplete_details", None)
        reason = getattr(details, "reason", None) or getattr(response, "status", None)
        raise LLMUnavailable(f"The language model returned an empty response (status: {reason}).")

    return text


def strip_code_fence(text: str) -> str:
    """Remove the ```json fences models wrap JSON in.

    Kept here rather than in each caller because both the lesson and the quiz
    parse JSON out of a chat response, and both were doing this by hand.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned
        cleaned = cleaned.replace("```json", "").replace("```", "")
    return cleaned.strip()
