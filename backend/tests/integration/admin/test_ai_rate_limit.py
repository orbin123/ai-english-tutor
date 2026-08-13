"""Tests for the per-user AI rate limiter (app/core/ai_rate_limit.py).

The suite runs with AI_RATE_LIMIT_ENABLED=false (conftest), so these tests
opt in explicitly via monkeypatch + reset_limiter_for_tests().
"""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import app.core.ai_rate_limit as ai_rate_limit_module
from app.core.ai_rate_limit import (
    InMemorySlidingWindowLimiter,
    RATE_LIMIT_MESSAGE,
    RedisSlidingWindowLimiter,
    ResilientLimiter,
    ai_rate_limit,
    get_limiter,
    reset_limiter_for_tests,
)
from app.core.config import settings
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User


@pytest.fixture(autouse=True)
def _fresh_limiter():
    # Pin a fresh in-memory limiter so these tests never touch a live Redis
    # (a developer's docker-compose Redis would persist buckets across runs).
    # The factory test overrides this by calling reset_limiter_for_tests().
    ai_rate_limit_module._limiter = InMemorySlidingWindowLimiter()
    yield
    reset_limiter_for_tests()


class TestInMemoryLimiter:
    def test_allows_up_to_limit_then_denies(self):
        limiter = InMemorySlidingWindowLimiter()
        results = [limiter.allow("k", limit=3, window_seconds=60) for _ in range(5)]
        assert results == [True, True, True, False, False]

    def test_keys_are_independent(self):
        limiter = InMemorySlidingWindowLimiter()
        assert limiter.allow("a", limit=1, window_seconds=60) is True
        assert limiter.allow("a", limit=1, window_seconds=60) is False
        assert limiter.allow("b", limit=1, window_seconds=60) is True

    def test_window_expiry_reallows(self, monkeypatch):
        limiter = InMemorySlidingWindowLimiter()
        now = [1000.0]
        monkeypatch.setattr(ai_rate_limit_module.time, "monotonic", lambda: now[0])
        assert limiter.allow("k", limit=1, window_seconds=60) is True
        assert limiter.allow("k", limit=1, window_seconds=60) is False
        now[0] += 61.0
        assert limiter.allow("k", limit=1, window_seconds=60) is True


class _ExplodingLimiter:
    def allow(self, key, *, limit, window_seconds):
        raise ConnectionError("redis down")


class TestResilience:
    def test_explicit_memory_backend_never_connects_to_redis(self, monkeypatch):
        import redis

        monkeypatch.setattr(settings, "AI_RATE_LIMIT_BACKEND", "memory")
        monkeypatch.setattr(settings, "redis_url", "redis://localhost:6379/0")
        monkeypatch.setattr(
            redis.Redis,
            "from_url",
            lambda *args, **kwargs: pytest.fail("memory backend contacted Redis"),
        )
        reset_limiter_for_tests()

        assert isinstance(get_limiter(), InMemorySlidingWindowLimiter)

    def test_redis_backend_uses_shared_limiter_when_configured(self, monkeypatch):
        import redis

        class _FakeRedis:
            def ping(self):
                return True

        fake = _FakeRedis()
        monkeypatch.setattr(settings, "AI_RATE_LIMIT_BACKEND", "redis")
        monkeypatch.setattr(settings, "redis_url", "redis://localhost:6379/0")
        monkeypatch.setattr(redis.Redis, "from_url", lambda *args, **kwargs: fake)
        reset_limiter_for_tests()

        limiter = get_limiter()
        assert isinstance(limiter, ResilientLimiter)
        assert isinstance(limiter._primary, RedisSlidingWindowLimiter)

    def test_redis_backend_without_url_degrades_to_memory(self, monkeypatch):
        monkeypatch.setattr(settings, "AI_RATE_LIMIT_BACKEND", "redis")
        monkeypatch.setattr(settings, "redis_url", None)
        reset_limiter_for_tests()

        assert isinstance(get_limiter(), InMemorySlidingWindowLimiter)

    def test_factory_falls_back_when_redis_unreachable(self, monkeypatch):
        # Point at a port nothing listens on; the 0.25 s connect timeout makes
        # this fast. The factory must swallow the failure and serve in-memory.
        monkeypatch.setattr(settings, "AI_RATE_LIMIT_BACKEND", "redis")
        monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1/0")
        reset_limiter_for_tests()
        limiter = get_limiter()
        assert isinstance(limiter, InMemorySlidingWindowLimiter)
        assert limiter.allow("k", limit=1, window_seconds=60) is True

    def test_runtime_redis_error_switches_to_memory_sticky(self):
        limiter = ResilientLimiter(_ExplodingLimiter())
        # First call hits the exploding primary, falls back, and still answers.
        assert limiter.allow("k", limit=2, window_seconds=60) is True
        # Sticky: primary is dropped, in-memory keeps counting.
        assert limiter.allow("k", limit=2, window_seconds=60) is True
        assert limiter.allow("k", limit=2, window_seconds=60) is False


def _make_client(user: User) -> TestClient:
    app = FastAPI()

    @app.post("/boom", dependencies=[Depends(ai_rate_limit("test_scope"))])
    def boom() -> dict[str, bool]:
        return {"ok": True}

    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


class TestDependency:
    def test_429_over_limit_with_detail_shape(self, monkeypatch):
        monkeypatch.setattr(settings, "AI_RATE_LIMIT_ENABLED", True)
        monkeypatch.setattr(settings, "AI_RATE_LIMIT_PER_MINUTE", 2)
        user = User(id=7, email="u@example.com", password_hash="x", name="U")
        with _make_client(user) as client:
            assert client.post("/boom").status_code == 200
            assert client.post("/boom").status_code == 200
            resp = client.post("/boom")
        assert resp.status_code == 429
        assert resp.json() == {"detail": RATE_LIMIT_MESSAGE}

    def test_disabled_flag_never_429s(self, monkeypatch):
        monkeypatch.setattr(settings, "AI_RATE_LIMIT_ENABLED", False)
        monkeypatch.setattr(settings, "AI_RATE_LIMIT_PER_MINUTE", 1)
        user = User(id=8, email="u@example.com", password_hash="x", name="U")
        with _make_client(user) as client:
            for _ in range(5):
                assert client.post("/boom").status_code == 200

    def test_budgets_are_per_user(self, monkeypatch):
        monkeypatch.setattr(settings, "AI_RATE_LIMIT_ENABLED", True)
        monkeypatch.setattr(settings, "AI_RATE_LIMIT_PER_MINUTE", 1)
        user_a = User(id=1, email="a@example.com", password_hash="x", name="A")
        user_b = User(id=2, email="b@example.com", password_hash="x", name="B")
        with _make_client(user_a) as client_a:
            assert client_a.post("/boom").status_code == 200
            assert client_a.post("/boom").status_code == 429
        with _make_client(user_b) as client_b:
            assert client_b.post("/boom").status_code == 200

    def test_custom_limit_setting_is_read(self, monkeypatch):
        monkeypatch.setattr(settings, "AI_RATE_LIMIT_ENABLED", True)
        monkeypatch.setattr(settings, "AI_RATE_LIMIT_TRANSCRIBE_PER_MINUTE", 1)
        app = FastAPI()

        @app.post(
            "/t",
            dependencies=[
                Depends(
                    ai_rate_limit(
                        "transcribe_test",
                        limit_setting="AI_RATE_LIMIT_TRANSCRIBE_PER_MINUTE",
                    )
                )
            ],
        )
        def t() -> dict[str, bool]:
            return {"ok": True}

        user = User(id=9, email="t@example.com", password_hash="x", name="T")
        app.dependency_overrides[get_current_user] = lambda: user
        with TestClient(app) as client:
            assert client.post("/t").status_code == 200
            assert client.post("/t").status_code == 429
