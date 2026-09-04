"""The language model Study Guider generates lessons and quizzes with.

============================ WHY THIS FILE EXISTS ============================
Two things were wrong, and they compounded.

The model was `openai/gpt-oss-20b:free` on OpenRouter. That slug no longer
exists - OpenRouter answers 404 with "This model is unavailable for free" - and
the account has no credits, so the paid slug answers 402. Every generation
request failed.

And every failure fell through to a hardcoded `get_smart_fallback` /
`get_smart_quiz_fallback` that returned invented lesson text and four canned
multiple-choice questions. So the service kept answering 200 with content that
looked real. Both were being served in place of generated output for as long as
the model had been unavailable, and nothing in the response said so.

Gemini replaces it. The key was already configured and already in use for the
embeddings behind the Neo4j vector index, so this removes a provider and a
second API key rather than adding one.

Nothing here falls back. If the model cannot answer, the caller raises and the
API returns 503. A student is told the lesson could not be generated, which is
true, instead of being shown something invented, which is not.
==============================================================================
"""

from __future__ import annotations

from app.core.config import settings


class LLMUnavailable(RuntimeError):
    """Generation could not happen. Never substitute content for this."""


_llm = None


def get_llm():
    """The chat model, or raise LLMUnavailable.

    Constructed once and reused. Raising rather than returning None is
    deliberate: a None that callers have to remember to check is how the
    fallbacks got there in the first place.
    """
    global _llm

    if _llm is not None:
        return _llm

    if not settings.GEMINI_API_KEY:
        raise LLMUnavailable(
            "GEMINI_API_KEY is not set, so lessons and quizzes cannot be generated."
        )

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI

        _llm = ChatGoogleGenerativeAI(
            model=settings.MODEL_NAME,
            google_api_key=settings.GEMINI_API_KEY,
            # Low but not zero. These are explanations of a specific mistake,
            # where correctness matters more than variety - but identical
            # wording every time reads as canned, which is the impression this
            # change exists to remove.
            temperature=0.3,
        )
        return _llm
    except Exception as error:
        raise LLMUnavailable(f"Could not initialise the language model: {error}") from error


def generate(prompt: str) -> str:
    """Run a prompt and return the text, or raise LLMUnavailable."""
    try:
        response = get_llm().invoke(prompt)
    except LLMUnavailable:
        raise
    except Exception as error:
        # Quota, network, a model id that no longer exists. All the same to the
        # caller: no content was generated, and none should be invented.
        raise LLMUnavailable(f"The language model did not answer: {error}") from error

    text = getattr(response, "content", None)
    if not isinstance(text, str) or not text.strip():
        raise LLMUnavailable("The language model returned an empty response.")

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
