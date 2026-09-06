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
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

    # Neo4j Database
    NEO4J_URI = os.getenv("NEO4J_URI")
    NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

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
    MODEL_NAME = os.getenv("MODEL_NAME", "gemini-3.6-flash")

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


# Global settings instance
settings = Settings()
