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
    redis_url="redis://localhost:6379/0",
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
    **_REQUIRED,
)


def test_safe_production_config_boots() -> None:
    settings = Settings(**_SAFE_PROD)
    assert settings.environment == "production"
    assert settings.cors_origins_list == ["https://app.example.com"]


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
    assert settings.AI_MAX_CONCURRENT_JOBS == 3
    assert settings.MAX_AUDIO_UPLOAD_BYTES == 5 * 1024 * 1024
    assert settings.MAX_AUDIO_DURATION_SECONDS == 45
