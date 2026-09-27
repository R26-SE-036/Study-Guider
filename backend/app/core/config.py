import os
from dotenv import load_dotenv

# Base directory paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENV_PATH = os.path.join(BASE_DIR, '.env')

# Load environment variables
load_dotenv(ENV_PATH)

class Settings:
    """Application configuration settings loaded from environment variables."""
    # API Keys
    # Gemini's key is needed whichever provider writes the lessons: the
    # syllabus embeddings behind the Neo4j vector index are Gemini's, and
    # switching them would mean re-embedding every note.
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip() or None

    # Who writes lessons, quizzes and session reviews: "gemini" or "openai".
    # The free Gemini tier turns requests away with 503 "high demand" when
    # Google is busy - a quiz failed for every lesson during testing - and paid
    # OpenAI credit is the cheaper way out than Gemini's prepay minimum.
    LLM_PROVIDER = (os.getenv("LLM_PROVIDER") or "gemini").strip().lower()

    # How hard an OpenAI reasoning model thinks: "low", "medium" or "high".
    # Unset, the model's own default. Reasoning tokens are billed as output and
    # were three quarters of every generation's cost, so this is the cost knob.
    OPENAI_REASONING_EFFORT = (os.getenv("OPENAI_REASONING_EFFORT") or "").strip().lower() or None

    # Neo4j Database
    NEO4J_URI = os.getenv("NEO4J_URI")
    NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
    # An Aura instance has exactly one database, "neo4j". Naming it saves the
    # driver a routing round trip to discover the home database on every
    # session; unset, the server's default is used.
    NEO4J_DATABASE = os.getenv("NEO4J_DATABASE") or None

    # The Gemini model used for lessons and quizzes.
    #
    # This was "openai/gpt-oss-20b:free" on OpenRouter. That slug no longer
    # exists - OpenRouter answers 404, "unavailable for free" - and the account
    # has no credits, so the paid slug answers 402. Every generation had been
    # failing into a hardcoded fallback that still returned 200.
    #
    # Gemini instead, using the key that already powers the embeddings behind
    # the Neo4j vector index. One provider, one key, one thing to configure.
    # gemini-2.5-flash was the default until the API started answering
    # 404 NOT_FOUND for it: "no longer available to new users. Please
    # update your code to use models/gemini-3.6-flash". An older key
    # keeps working, so this only bites on a newly issued one - which is
    # exactly when someone is least likely to suspect the model name.
    #
    # With LLM_PROVIDER=openai the default is gpt-6-luna, OpenAI's cheapest
    # current model: about $0.002 a lesson or quiz against Gemini's $0.012.
    MODEL_NAME = os.getenv("MODEL_NAME") or (
        "gpt-6-luna" if LLM_PROVIDER == "openai" else "gemini-3.6-flash"
    )

    # Directory paths.
    # CHROMA_DB_DIR is gone with Chroma: the syllabus vectors live in Neo4j's
    # vector index now, so there is no longer a directory on local disk that
    # has to survive a container restart.
    DATA_DIR = os.path.join(BASE_DIR, "data")

    # ── Code Coach (the platform's identity provider) ──
    # Study Guider has no accounts of its own. It verifies the bearer token on
    # every request against Code Coach, and reads its remediation triggers from
    # there. Nothing in this service works without it.
    CODE_COACH_URL = os.getenv("CODE_COACH_URL", "http://127.0.0.1:8000")
    CODE_COACH_TIMEOUT_SECONDS = float(os.getenv("CODE_COACH_TIMEOUT_SECONDS", "10"))

    # How long a verified token stays trusted without re-asking Code Coach.
    # Trades a little revocation latency for not paying a round trip per
    # request; see app/core/auth.py.
    AUTH_CACHE_TTL_SECONDS = float(os.getenv("AUTH_CACHE_TTL_SECONDS", "60"))

    # ── Calls from other Code Guru services ──
    # PairPath asks for the review a student sees after a pair session. That
    # request carries the exercise's model solution, so it comes from PairPath's
    # server rather than from a browser, and proves it with this shared key.
    # Unset, the session-review endpoint answers 503 and PairPath falls back to
    # the exercise's fixed review questions. See app/core/internal_auth.py.
    INTERNAL_SERVICE_KEY = (os.getenv("INTERNAL_SERVICE_KEY") or "").strip() or None


# Global settings instance
settings = Settings()
