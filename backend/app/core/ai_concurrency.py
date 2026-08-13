"""Process-local concurrency guard for external AI and audio providers."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from weakref import WeakKeyDictionary

from app.core.config import settings


_semaphores: WeakKeyDictionary[
    asyncio.AbstractEventLoop, tuple[int, asyncio.Semaphore]
] = WeakKeyDictionary()


def _semaphore_for_running_loop() -> asyncio.Semaphore:
    """Return a limiter bound to the current event loop and configured size."""
    loop = asyncio.get_running_loop()
    limit = settings.AI_MAX_CONCURRENT_JOBS
    configured = _semaphores.get(loop)
    if configured is None or configured[0] != limit:
        semaphore = asyncio.Semaphore(limit)
        _semaphores[loop] = (limit, semaphore)
        return semaphore
    return configured[1]


@asynccontextmanager
async def ai_provider_slot():
    """Hold one of the process-wide provider slots for one external job."""
    semaphore = _semaphore_for_running_loop()
    await semaphore.acquire()
    try:
        yield
    finally:
        semaphore.release()


def reset_ai_concurrency_for_tests() -> None:
    """Drop loop-local semaphores after a test changes the configured limit."""
    _semaphores.clear()
