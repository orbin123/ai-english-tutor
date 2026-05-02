"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Central configuration object.

    Reads values from .env file at project root.
    All fields are type-validated on startup - missing/wrong values
    will crash the app immediately with a clear error.
    """

    # Application
    environment: str = "development"
    debug: bool = True
    log_level: str = "info"

    # Database
    database_url: str 

    # Redis
    redis_url: str

    # Auth
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"

    # Frontend
    frontend_url: str = "http://localhost:3000"

    # AI / LLM
    OPENAI_API_KEY: str
    LANGCHAIN_TRACING_V2: bool = True
    LANGCHAIN_API_KEY: str
    LANGCHAIN_PROJECT: str = "ai-english-coach"
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"

    # Vector DB (Pinecone)
    PINECONE_API_KEY: str
    PINECONE_INDEX_NAME: str = "lingosai-responses"
    PINECONE_CLOUD: str = "aws"
    PINECONE_REGION: str = "us-east-1"

    # Embeddings (HuggingFace)
    HF_API_KEY: str
    HF_EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION: int = 384

    # Find and read .env file
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )



# Single shared instance
settings = Settings()