"""Database access for usage quota counters."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.quotas.models import UsageQuotaCounter


class QuotaRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_count(
        self,
        *,
        period_type: str,
        period_key: str,
        metric: str,
    ) -> int:
        row = self._db.scalar(
            select(UsageQuotaCounter.count).where(
                UsageQuotaCounter.period_type == period_type,
                UsageQuotaCounter.period_key == period_key,
                UsageQuotaCounter.metric == metric,
            )
        )
        return int(row or 0)

    def increment(
        self,
        *,
        period_type: str,
        period_key: str,
        metric: str,
        amount: int,
    ) -> int:
        if amount <= 0:
            return self.get_count(
                period_type=period_type,
                period_key=period_key,
                metric=metric,
            )

        row = self._db.scalar(
            select(UsageQuotaCounter).where(
                UsageQuotaCounter.period_type == period_type,
                UsageQuotaCounter.period_key == period_key,
                UsageQuotaCounter.metric == metric,
            )
        )
        if row is None:
            row = UsageQuotaCounter(
                period_type=period_type,
                period_key=period_key,
                metric=metric,
                count=amount,
            )
            self._db.add(row)
            self._db.flush()
            return amount

        row.count += amount
        self._db.flush()
        return row.count
