"""Unit tests for PostgreSQL-backed usage quota counters."""

from datetime import UTC, datetime

import pytest

from app.core.config import settings
from app.modules.quotas.constants import QuotaMetric
from app.modules.quotas.exceptions import QuotaExceeded
from app.modules.quotas.service import QuotaService


@pytest.fixture(autouse=True)
def enable_quotas(monkeypatch):
    monkeypatch.setattr(settings, "QUOTA_COUNTERS_ENABLED", True)


def test_consume_increments_daily_completed_lessons(db_session) -> None:
    fixed_now = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
    service = QuotaService(db_session)

    service.consume(QuotaMetric.COMPLETED_LESSONS, now=fixed_now)
    service.consume(QuotaMetric.COMPLETED_LESSONS, now=fixed_now)

    repo = service._repo
    assert (
        repo.get_count(
            period_type="daily",
            period_key="2026-08-19",
            metric=QuotaMetric.COMPLETED_LESSONS.value,
        )
        == 2
    )


def test_consume_raises_when_daily_lesson_cap_exceeded(db_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "QUOTA_DAILY_COMPLETED_LESSONS", 1)
    fixed_now = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
    service = QuotaService(db_session)

    service.consume(QuotaMetric.COMPLETED_LESSONS, now=fixed_now)
    with pytest.raises(QuotaExceeded):
        service.consume(QuotaMetric.COMPLETED_LESSONS, now=fixed_now)


def test_zero_monthly_image_cap_fails_closed(db_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "QUOTA_MONTHLY_IMAGE_GENS", 0)
    service = QuotaService(db_session)

    with pytest.raises(QuotaExceeded):
        service.consume(QuotaMetric.IMAGE_GENS)
