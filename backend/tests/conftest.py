import sys
import os
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("LANGCHAIN_API_KEY", "test-langchain-key")
os.environ.setdefault("PINECONE_API_KEY", "test-pinecone-key")
# Schema-boundary contracts raise (not fall back) under tests so contract
# violations surface loudly. Prod default stays False during rollout.
os.environ.setdefault("STRICT_CONTRACTS", "true")
# AI rate limiting is off for the suite so tight request loops sharing one
# user id never trip a limit and the limiter never dials Redis. Dedicated
# tests opt back in via monkeypatch + reset_limiter_for_tests().
os.environ.setdefault("AI_RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("QUOTA_COUNTERS_ENABLED", "false")


# Shared fixtures live in dedicated modules and are registered as plugins so
# every test (regardless of folder) can request `db_session`, `client`,
# `seed_archetypes`, factories, etc. without re-declaring them. See
# docs/testing-strategy.md (Phase 3). Env vars above MUST be set before these
# import, because they pull in `app.*` (which reads settings at import time).
# (Factories under tests/factories/ are plain functions — imported directly,
# e.g. `from tests.factories.users import make_user` — not registered here.)
pytest_plugins = [
    "tests.fixtures.db",
    "tests.fixtures.client",
    "tests.fixtures.curriculum",
]
