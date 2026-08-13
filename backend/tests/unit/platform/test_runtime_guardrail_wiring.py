"""Runtime wiring for settings-backed CORS and database pooling."""

from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import engine
from app.main import app


def test_cors_middleware_uses_validated_settings() -> None:
    cors = next(item for item in app.user_middleware if item.cls is CORSMiddleware)

    assert cors.kwargs["allow_origins"] == settings.cors_origins_list


def test_database_pool_uses_configured_limits() -> None:
    assert engine.pool.size() == settings.DB_POOL_SIZE
    assert engine.pool.timeout() == settings.DB_POOL_TIMEOUT
    assert engine.pool._max_overflow == settings.DB_MAX_OVERFLOW
