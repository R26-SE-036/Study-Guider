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
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

    # Neo4j Database
    NEO4J_URI = os.getenv("NEO4J_URI")
    NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

    # 🚀 EXACT OPENROUTER MODEL ID
    MODEL_NAME = "openai/gpt-oss-20b:free"

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
    CODE_COACH_CLIENT_NAME = os.getenv("CODE_COACH_CLIENT_NAME", "codeguru-study-guider")
    CODE_COACH_TIMEOUT_SECONDS = float(os.getenv("CODE_COACH_TIMEOUT_SECONDS", "10"))

    # How long a verified token stays trusted without re-asking Code Coach.
    # Trades a little revocation latency for not paying a round trip per
    # request; see app/core/auth.py.
    AUTH_CACHE_TTL_SECONDS = float(os.getenv("AUTH_CACHE_TTL_SECONDS", "60"))

    # Browsers that may call this API. The Vite dev server is 5173; 4200 is the
    # Code Guru portal, which links students here.
    CORS_ORIGINS = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:4200,http://127.0.0.1:4200",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

# Global settings instance
settings = Settings()
