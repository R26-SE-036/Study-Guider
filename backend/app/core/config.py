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
    
    # Directory paths
    DATA_DIR = os.path.join(BASE_DIR, "data")
    CHROMA_DB_DIR = os.path.join(BASE_DIR, "chroma_db")

# Global settings instance
settings = Settings()