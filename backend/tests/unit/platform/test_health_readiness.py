"""Readiness checks only dependencies selected by configuration."""

from __future__ import annotations

import json

import app.main as main_module


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, statement) -> None:
        return None


class _Engine:
    def connect(self) -> _Connection:
        return _Connection()


def _payload(response) -> dict:
    return json.loads(response.body)


def test_memory_backend_is_ready_without_redis(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "engine", _Engine())
    monkeypatch.setattr(main_module.settings, "AI_RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(main_module.settings, "AI_RATE_LIMIT_BACKEND", "memory")
    monkeypatch.setattr(main_module.settings, "redis_url", None)

    response = main_module.readiness_check()

    assert response.status_code == 200
    assert _payload(response) == {
        "status": "ready",
        "checks": {"database": "ok"},
    }


def test_redis_backend_is_checked_when_configured(monkeypatch) -> None:
    import redis

    class _RedisClient:
        def ping(self) -> bool:
            return True

    observed: dict[str, object] = {}

    def _from_url(url, **kwargs):
        observed["url"] = url
        observed.update(kwargs)
        return _RedisClient()

    monkeypatch.setattr(main_module, "engine", _Engine())
    monkeypatch.setattr(main_module.settings, "AI_RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(main_module.settings, "AI_RATE_LIMIT_BACKEND", "redis")
    monkeypatch.setattr(
        main_module.settings,
        "redis_url",
        "redis://redis.internal:6379/0",
    )
    monkeypatch.setattr(redis.Redis, "from_url", _from_url)

    response = main_module.readiness_check()

    assert response.status_code == 200
    assert _payload(response) == {
        "status": "ready",
        "checks": {"database": "ok", "redis": "ok"},
    }
    assert observed == {
        "url": "redis://redis.internal:6379/0",
        "socket_connect_timeout": 0.5,
        "socket_timeout": 0.5,
    }


def test_selected_redis_backend_without_url_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "engine", _Engine())
    monkeypatch.setattr(main_module.settings, "AI_RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(main_module.settings, "AI_RATE_LIMIT_BACKEND", "redis")
    monkeypatch.setattr(main_module.settings, "redis_url", None)

    response = main_module.readiness_check()

    assert response.status_code == 503
    assert _payload(response) == {
        "status": "not_ready",
        "checks": {"database": "ok", "redis": "not_configured"},
    }


def test_selected_redis_backend_failure_is_not_ready(monkeypatch) -> None:
    import redis

    monkeypatch.setattr(main_module, "engine", _Engine())
    monkeypatch.setattr(main_module.settings, "AI_RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(main_module.settings, "AI_RATE_LIMIT_BACKEND", "redis")
    monkeypatch.setattr(main_module.settings, "redis_url", "redis://broken:6379/0")
    monkeypatch.setattr(
        redis.Redis,
        "from_url",
        lambda *args, **kwargs: (_ for _ in ()).throw(ConnectionError("down")),
    )

    response = main_module.readiness_check()

    assert response.status_code == 503
    assert _payload(response) == {
        "status": "not_ready",
        "checks": {"database": "ok", "redis": "error"},
    }


def test_database_failure_remains_not_ready_in_memory_mode(monkeypatch) -> None:
    class _BrokenEngine:
        def connect(self):
            raise RuntimeError("database down")

    monkeypatch.setattr(main_module, "engine", _BrokenEngine())
    monkeypatch.setattr(main_module.settings, "AI_RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(main_module.settings, "AI_RATE_LIMIT_BACKEND", "memory")
    monkeypatch.setattr(main_module.settings, "redis_url", None)

    response = main_module.readiness_check()

    assert response.status_code == 503
    assert _payload(response) == {
        "status": "not_ready",
        "checks": {"database": "error"},
    }


def test_disabled_rate_limiter_does_not_require_redis(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "engine", _Engine())
    monkeypatch.setattr(main_module.settings, "AI_RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(main_module.settings, "AI_RATE_LIMIT_BACKEND", "redis")
    monkeypatch.setattr(main_module.settings, "redis_url", None)

    response = main_module.readiness_check()

    assert response.status_code == 200
    assert _payload(response) == {
        "status": "ready",
        "checks": {"database": "ok"},
    }
