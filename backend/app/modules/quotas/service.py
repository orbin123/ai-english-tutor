"""Transactional quota checks against PostgreSQL counters."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.quotas.constants import QuotaMetric, QuotaPeriod
from app.modules.quotas.exceptions import QuotaExceeded
from app.modules.quotas.repository import QuotaRepository


def _daily_key(now: datetime | None = None) -> str:
    current = now or datetime.now(UTC)
    return current.date().isoformat()


def _monthly_key(now: datetime | None = None) -> str:
    current = now or datetime.now(UTC)
    return f"{current.year:04d}-{current.month:02d}"


class QuotaService:
    """Increment and enforce Azure zero-cost usage caps."""

    _METRIC_PERIODS: dict[QuotaMetric, tuple[QuotaPeriod, ...]] = {
        QuotaMetric.COMPLETED_LESSONS: (QuotaPeriod.DAILY,),
        QuotaMetric.BLOB_WRITES: (QuotaPeriod.MONTHLY,),
        QuotaMetric.SPEECH_MINUTES: (QuotaPeriod.MONTHLY,),
        QuotaMetric.TTS_CHARS: (QuotaPeriod.MONTHLY,),
        QuotaMetric.LLM_TOKENS: (QuotaPeriod.MONTHLY,),
        QuotaMetric.IMAGE_GENS: (QuotaPeriod.MONTHLY,),
    }

    def __init__(self, db: Session) -> None:
        self._db = db
        self._repo = QuotaRepository(db)

    def consume(
        self,
        metric: QuotaMetric,
        amount: int = 1,
        *,
        now: datetime | None = None,
    ) -> None:
        """Increment counters and raise when a configured limit is exceeded."""
        if not settings.QUOTA_COUNTERS_ENABLED or amount <= 0:
            return

        for period_type in self._METRIC_PERIODS[metric]:
            period_key = (
                _daily_key(now)
                if period_type is QuotaPeriod.DAILY
                else _monthly_key(now)
            )
            limit = self._limit_for(metric=metric, period_type=period_type)
            if limit <= 0:
                raise QuotaExceeded(
                    metric=metric.value,
                    period_type=period_type.value,
                    period_key=period_key,
                    limit=limit,
                    attempted=amount,
                )

            new_total = self._repo.increment(
                period_type=period_type.value,
                period_key=period_key,
                metric=metric.value,
                amount=amount,
            )
            if new_total > limit:
                raise QuotaExceeded(
                    metric=metric.value,
                    period_type=period_type.value,
                    period_key=period_key,
                    limit=limit,
                    attempted=new_total,
                )

    def _limit_for(self, *, metric: QuotaMetric, period_type: QuotaPeriod) -> int:
        if metric is QuotaMetric.COMPLETED_LESSONS:
            return settings.QUOTA_DAILY_COMPLETED_LESSONS
        if metric is QuotaMetric.BLOB_WRITES:
            return settings.QUOTA_MONTHLY_BLOB_WRITES
        if metric is QuotaMetric.SPEECH_MINUTES:
            return int(settings.QUOTA_MONTHLY_SPEECH_MINUTES)
        if metric is QuotaMetric.TTS_CHARS:
            return settings.QUOTA_MONTHLY_TTS_CHARS
        if metric is QuotaMetric.LLM_TOKENS:
            return settings.QUOTA_MONTHLY_LLM_TOKENS
        if metric is QuotaMetric.IMAGE_GENS:
            return settings.QUOTA_MONTHLY_IMAGE_GENS
        raise ValueError(f"unknown quota metric: {metric!r}")


def consume_quota(metric: QuotaMetric, amount: int = 1) -> None:
    """Increment quota counters in a standalone DB session (for AI layer hooks)."""
    if not settings.QUOTA_COUNTERS_ENABLED or amount <= 0:
        return

    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        QuotaService(db).consume(metric, amount=amount)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
