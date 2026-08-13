"""Per-user rate limiting for AI-cost-incurring endpoints.

Unlike the IP-keyed ``AdminRateLimitMiddleware``, these limits are keyed by
the authenticated user (mobile users share IPs behind NAT) and applied as a
FastAPI dependency so the resolved ``User`` is available. The configured
backend is either deliberately process-local memory (one worker only) or Redis
(shared across workers, with a sticky in-memory fallback on runtime failure).
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from threading import Lock
from typing import Protocol

import structlog
from fastapi import Depends, HTTPException, status

from app.core.config import settings
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User

logger = structlog.get_logger(__name__)

RATE_LIMIT_MESSAGE = "You're going a little fast — please wait a moment and try again."


class SlidingWindowLimiter(Protocol):
    def allow(self, key: str, *, limit: int, window_seconds: int) -> bool:
        """Record a hit and return whether it is within the limit."""
        ...


class InMemorySlidingWindowLimiter:
    """Same deque-based sliding window as AdminRateLimitMiddleware._allow."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str, *, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            cutoff = now - window_seconds
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True


class RedisSlidingWindowLimiter:
    """Sorted-set sliding window: one pipeline round-trip per check."""

    def __init__(self, client) -> None:  # redis.Redis — untyped to keep redis optional
        self._client = client

    def allow(self, key: str, *, limit: int, window_seconds: int) -> bool:
        now = time.time()
        redis_key = f"rl:{key}"
        pipe = self._client.pipeline()
        pipe.zremrangebyscore(redis_key, 0, now - window_seconds)
        pipe.zcard(redis_key)
        results = pipe.execute()
        if int(results[1]) >= limit:
            return False
        pipe = self._client.pipeline()
        pipe.zadd(redis_key, {uuid.uuid4().hex: now})
        pipe.expire(redis_key, window_seconds)
        pipe.execute()
        return True


class ResilientLimiter:
    """Redis limiter that degrades permanently to in-memory on any error.

    Sticky on purpose: once Redis misbehaves mid-flight we stop paying a
    timeout per request and serve from process-local buckets until restart.
    """

    def __init__(self, primary: SlidingWindowLimiter) -> None:
        self._primary: SlidingWindowLimiter | None = primary
        self._fallback = InMemorySlidingWindowLimiter()

    def allow(self, key: str, *, limit: int, window_seconds: int) -> bool:
        if self._primary is not None:
            try:
                return self._primary.allow(
                    key, limit=limit, window_seconds=window_seconds
                )
            except Exception:
                logger.warning("ai_rate_limit_redis_error_falling_back", exc_info=True)
                self._primary = None
        return self._fallback.allow(key, limit=limit, window_seconds=window_seconds)


_limiter: SlidingWindowLimiter | None = None


def _build_limiter() -> SlidingWindowLimiter:
    if settings.AI_RATE_LIMIT_BACKEND == "memory":
        logger.info("ai_rate_limit_using_memory_backend")
        return InMemorySlidingWindowLimiter()

    if not settings.redis_url:
        logger.warning("ai_rate_limit_redis_url_missing_using_memory")
        return InMemorySlidingWindowLimiter()

    try:
        import redis  # imported lazily so a missing package can't break startup

        client = redis.Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=0.25,
            socket_timeout=0.25,
        )
        client.ping()
        return ResilientLimiter(RedisSlidingWindowLimiter(client))
    except Exception:
        logger.warning("ai_rate_limit_redis_unavailable_using_memory", exc_info=True)
        return InMemorySlidingWindowLimiter()


def get_limiter() -> SlidingWindowLimiter:
    global _limiter
    if _limiter is None:
        _limiter = _build_limiter()
    return _limiter


def reset_limiter_for_tests() -> None:
    global _limiter
    _limiter = None


def ai_rate_limit(
    scope: str,
    *,
    limit_setting: str = "AI_RATE_LIMIT_PER_MINUTE",
    window_seconds: int = 60,
):
    """Dependency factory: per-user sliding-window limit for one AI surface.

    Usage: ``@router.post(..., dependencies=[Depends(ai_rate_limit("scope"))])``.
    Reads the limit from settings at call time so it stays monkeypatchable.
    """

    def _dependency(current_user: User = Depends(get_current_user)) -> None:
        if not settings.AI_RATE_LIMIT_ENABLED:
            return
        limit = int(getattr(settings, limit_setting))
        key = f"ai:{scope}:{current_user.id}"
        if not get_limiter().allow(key, limit=limit, window_seconds=window_seconds):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=RATE_LIMIT_MESSAGE,
            )

    return _dependency
