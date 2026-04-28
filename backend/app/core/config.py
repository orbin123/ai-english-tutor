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

    # AI / LLM
    OPENAI_API_KEY: str
    LANGCHAIN_TRACING_V2: bool = True
    LANGCHAIN_API_KEY: str
    LANGCHAIN_PROJECT: str = "ai-english-coach"
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"

    # Find and read .env file
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )



# Single shared instance
settings = Settings()