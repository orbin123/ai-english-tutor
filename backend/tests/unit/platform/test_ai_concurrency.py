"""Process-local provider concurrency guard."""

import asyncio

import pytest

from app.core.ai_concurrency import (
    ai_provider_slot,
    reset_ai_concurrency_for_tests,
)
from app.core.config import settings


@pytest.mark.asyncio
async def test_provider_jobs_wait_when_the_configured_slot_is_busy(monkeypatch) -> None:
    monkeypatch.setattr(settings, "AI_MAX_CONCURRENT_JOBS", 1)
    reset_ai_concurrency_for_tests()
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    second_entered = asyncio.Event()

    async def first_job() -> None:
        async with ai_provider_slot():
            first_entered.set()
            await release_first.wait()

    async def second_job() -> None:
        async with ai_provider_slot():
            second_entered.set()

    first = asyncio.create_task(first_job())
    await first_entered.wait()
    second = asyncio.create_task(second_job())
    await asyncio.sleep(0)
    assert not second_entered.is_set()

    release_first.set()
    await asyncio.gather(first, second)
    assert second_entered.is_set()
    reset_ai_concurrency_for_tests()
