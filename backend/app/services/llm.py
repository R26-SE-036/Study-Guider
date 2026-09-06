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

Nothing here falls back. If the model cannot answer, the caller raises and the
API returns 503. A student is told the lesson could not be generated, which is
true, instead of being shown something invented, which is not.
==============================================================================
"""

from __future__ import annotations

from app.core.config import settings


class LLMUnavailable(RuntimeError):
    """Generation could not happen. Never substitute content for this."""


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


def generate(prompt: str) -> str:
    """Run a prompt and return the text, or raise LLMUnavailable."""
    client = get_client()

    try:
        response = client.models.generate_content(
            model=settings.MODEL_NAME,
            contents=prompt,
        )
    except Exception as error:
        # Quota, network, a model id that is no longer served to this key. All
        # the same to the caller: no content was generated, and none should be
        # invented.
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
