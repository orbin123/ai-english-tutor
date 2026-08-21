"""Production config guard — audit A1/A2/A3/A4 + the prod half of D3.

The app already crashes on missing required vars; the guard extends that to
"unsafe-in-prod" combinations so a single forgotten env override can never
silently ship a dev-only setting. The guard only fires when
ENVIRONMENT=production; dev and tests are untouched.
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

# Required fields with no defaults — supplied explicitly so construction
# reaches the after-validator regardless of ambient env / conftest.
_REQUIRED = dict(
    database_url="sqlite:///./test.db",
    jwt_secret="test-secret",
    OPENAI_API_KEY="test",
    LANGCHAIN_API_KEY="test",
    PINECONE_API_KEY="test",
)

# A fully prod-safe configuration the guard MUST accept.
_SAFE_PROD = dict(
    _env_file=None,  # don't read ../.env; this test is self-contained
    environment="production",
    debug=False,
    sql_echo=False,
    DEV_OTP_BYPASS=False,
    OTP_HASHING_SECRET="a" * 32,
    AUTH_COOKIE_SECURE=True,
    cors_origins="https://app.example.com",
    frontend_url="https://app.example.com",
    STORAGE_BACKEND="azure",
    AZURE_BLOB_PUBLIC_ACCOUNT_URL="https://publicmedia.blob.core.windows.net",
    AZURE_BLOB_PRIVATE_ACCOUNT_URL="https://privatedata.blob.core.windows.net",
    AZURE_BLOB_PUBLIC_CONTAINER_ACCESS="blob",
    AI_RATE_LIMIT_BACKEND="memory",
    redis_url=None,
    WEB_CONCURRENCY=1,
    **_REQUIRED,
)

_AZURE_MANAGED_IDENTITY_PROD = {
    **_SAFE_PROD,
    "DATABASE_AUTH_MODE": "azure-managed-identity",
    "database_url": (
        "postgresql://vm-lingosai-prod@pg-lingosai-prod.postgres.database."
        "azure.com:5432/lingosai?sslmode=require"
    ),
}


def test_safe_production_config_boots() -> None:
    settings = Settings(**_SAFE_PROD)
    assert settings.environment == "production"
    assert settings.cors_origins_list == ["https://app.example.com"]


def test_safe_managed_identity_database_config_boots_without_password() -> None:
    settings = Settings(**_AZURE_MANAGED_IDENTITY_PROD)

    assert settings.DATABASE_AUTH_MODE == "azure-managed-identity"
    assert "://vm-lingosai-prod@" in settings.database_url


@pytest.mark.parametrize(
    "override",
    [
        {"debug": True},
        {"sql_echo": True},
        {"DEV_OTP_BYPASS": True},
        {"OTP_HASHING_SECRET": ""},
        {"AUTH_COOKIE_SECURE": False},
        {"cors_origins": "https://app.example.com,http://localhost:3000"},
        {"cors_origins": "https://app.example.com,http://127.0.0.1:3000"},
        {"cors_origins": ""},
        {"cors_origins": "http://app.example.com"},
        {"cors_origins": "https://*.example.com"},
        {"cors_origins": "https://user@app.example.com"},
        {"cors_origins": "https://app.example.com/path"},
        {"cors_origins": "https://10.0.0.2"},
        {"frontend_url": ""},
        {"frontend_url": "http://app.example.com"},
        {"frontend_url": "https://other.example.com"},
    ],
)
def test_unsafe_production_config_refuses_to_boot(override: dict) -> None:
    with pytest.raises(ValidationError):
        Settings(**{**_SAFE_PROD, **override})


def test_development_allows_dev_defaults() -> None:
    # The guard must not fire outside production — every dev-only value is fine.
    settings = Settings(
        _env_file=None,
        environment="development",
        debug=True,
        sql_echo=True,
        DEV_OTP_BYPASS=True,
        OTP_HASHING_SECRET="",
        AUTH_COOKIE_SECURE=False,
        cors_origins="http://localhost:3000",
        STORAGE_BACKEND="local",
        **_REQUIRED,
    )
    assert settings.debug is True
    assert settings.DEV_OTP_BYPASS is True


def test_cors_origins_list_splits_and_strips() -> None:
    settings = Settings(
        _env_file=None,
        cors_origins=" https://a.example.com , https://b.example.com ,",
        **_REQUIRED,
    )
    assert settings.cors_origins_list == [
        "https://a.example.com",
        "https://b.example.com",
    ]


def test_zero_cost_resource_defaults_are_bounded() -> None:
    settings = Settings(_env_file=None, **_REQUIRED)

    assert settings.DB_POOL_SIZE == 3
    assert settings.DB_MAX_OVERFLOW == 2
    assert settings.DB_POOL_TIMEOUT == 10
    assert settings.WEB_CONCURRENCY == 1
    assert settings.AI_RATE_LIMIT_BACKEND == "redis"
    assert settings.AI_MAX_CONCURRENT_JOBS == 3
    assert settings.MAX_AUDIO_UPLOAD_BYTES == 5 * 1024 * 1024
    assert settings.MAX_AUDIO_DURATION_SECONDS == 45


def test_redis_url_is_optional_for_memory_backend(monkeypatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)

    settings = Settings(
        _env_file=None,
        AI_RATE_LIMIT_BACKEND="memory",
        **_REQUIRED,
    )

    assert settings.AI_RATE_LIMIT_BACKEND == "memory"
    assert settings.redis_url is None


@pytest.mark.parametrize(
    ("pool_size", "max_overflow"),
    [(4, 2), (5, 1), (6, 0)],
)
def test_production_rejects_database_pool_above_five_connections(
    pool_size: int, max_overflow: int
) -> None:
    with pytest.raises(ValidationError, match="must not exceed 5"):
        Settings(
            **{
                **_SAFE_PROD,
                "DB_POOL_SIZE": pool_size,
                "DB_MAX_OVERFLOW": max_overflow,
            }
        )


def test_production_accepts_database_pool_at_five_connections() -> None:
    settings = Settings(**{**_SAFE_PROD, "DB_POOL_SIZE": 4, "DB_MAX_OVERFLOW": 1})
    assert settings.DB_POOL_SIZE + settings.DB_MAX_OVERFLOW == 5


@pytest.mark.parametrize(
    "database_url",
    [
        (
            "postgresql://vm-lingosai-prod:secret@pg-lingosai-prod.postgres."
            "database.azure.com:5432/lingosai?sslmode=require"
        ),
        (
            "postgresql://other-user@pg-lingosai-prod.postgres.database."
            "azure.com:5432/lingosai?sslmode=require"
        ),
        "postgresql://vm-lingosai-prod@db.example.com:5432/lingosai?sslmode=require",
        (
            "postgresql://vm-lingosai-prod@pg-lingosai-prod.postgres.database."
            "azure.com:6432/lingosai?sslmode=require"
        ),
        (
            "postgresql://vm-lingosai-prod@pg-lingosai-prod.postgres.database."
            "azure.com:5432/postgres?sslmode=require"
        ),
        (
            "postgresql://vm-lingosai-prod@pg-lingosai-prod.postgres.database."
            "azure.com:5432/lingosai?sslmode=prefer"
        ),
        (
            "postgresql://vm-lingosai-prod@pg-lingosai-prod.postgres.database."
            "azure.com:5432/lingosai?sslmode=require&application_name=lingosai"
        ),
    ],
)
def test_production_rejects_unsafe_managed_identity_database_url(
    database_url: str,
) -> None:
    with pytest.raises(ValidationError, match="managed-identity DATABASE_URL"):
        Settings(**{**_AZURE_MANAGED_IDENTITY_PROD, "database_url": database_url})


def test_production_rejects_password_mode_for_azure_postgres() -> None:
    with pytest.raises(ValidationError, match="Azure PostgreSQL requires"):
        Settings(
            **{
                **_AZURE_MANAGED_IDENTITY_PROD,
                "DATABASE_AUTH_MODE": "password",
            }
        )


def test_production_rejects_multiple_workers_with_memory_limiter() -> None:
    with pytest.raises(ValidationError, match="WEB_CONCURRENCY must be 1"):
        Settings(**{**_SAFE_PROD, "WEB_CONCURRENCY": 2})


@pytest.mark.parametrize("redis_url", [None, "", "   ", "https://redis.example.com"])
def test_production_redis_limiter_requires_redis_url(redis_url: str | None) -> None:
    with pytest.raises(ValidationError, match="REDIS_URL must be set"):
        Settings(
            **{
                **_SAFE_PROD,
                "AI_RATE_LIMIT_BACKEND": "redis",
                "redis_url": redis_url,
            }
        )


def test_production_redis_limiter_supports_multiple_workers() -> None:
    settings = Settings(
        **{
            **_SAFE_PROD,
            "AI_RATE_LIMIT_BACKEND": "redis",
            "redis_url": "redis://redis.example.com:6379/0",
            "WEB_CONCURRENCY": 3,
        }
    )
    assert settings.WEB_CONCURRENCY == 3


@pytest.mark.parametrize("storage_backend", ["local", "ftp", "unknown"])
def test_production_rejects_unsupported_storage_backend(storage_backend: str) -> None:
    with pytest.raises(ValidationError):
        Settings(**{**_SAFE_PROD, "STORAGE_BACKEND": storage_backend})


@pytest.mark.parametrize(
    "override",
    [
        {"AZURE_BLOB_PUBLIC_ACCOUNT_URL": ""},
        {"AZURE_BLOB_PRIVATE_ACCOUNT_URL": "http://private.blob.core.windows.net"},
        {
            "AZURE_BLOB_PRIVATE_ACCOUNT_URL": (
                "https://publicmedia.blob.core.windows.net"
            )
        },
        {"AZURE_BLOB_PUBLIC_CONTAINER": "Public-Media"},
        {"AZURE_BLOB_PRIVATE_CONTAINER": "ab"},
        {"AZURE_BLOB_INTERNAL_CONTAINER": "internal--media"},
        {"AZURE_BLOB_PRIVATE_CONTAINER": "public-media"},
        {"AZURE_BLOB_PUBLIC_CONTAINER_ACCESS": "private"},
        {"AZURE_BLOB_PUBLIC_CONTAINER_ACCESS": "container"},
        {"AZURE_BLOB_PRIVATE_CONTAINER_ACCESS": "blob"},
        {"AZURE_BLOB_PRIVATE_CONTAINER_ACCESS": "container"},
        {"AZURE_BLOB_INTERNAL_CONTAINER_ACCESS": "blob"},
        {"AZURE_BLOB_INTERNAL_CONTAINER_ACCESS": "container"},
    ],
)
def test_production_rejects_invalid_azure_container_configuration(
    override: dict,
) -> None:
    with pytest.raises(ValidationError):
        Settings(**{**_SAFE_PROD, **override})
