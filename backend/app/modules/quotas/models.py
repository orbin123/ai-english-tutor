"""PostgreSQL-backed usage quota counters."""

from __future__ import annotations

from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import IDMixin, TimestampMixin


class UsageQuotaCounter(Base, IDMixin, TimestampMixin):
    """One row per (period, metric) aggregate counter.

    Counters survive deploys and restarts, unlike in-memory semaphores.
    """

    __tablename__ = "usage_quota_counters"
    __table_args__ = (
        UniqueConstraint(
            "period_type",
            "period_key",
            "metric",
            name="uq_usage_quota_counters_period_metric",
        ),
    )

    period_type: Mapped[str] = mapped_column(String(16), nullable=False)
    period_key: Mapped[str] = mapped_column(String(16), nullable=False)
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
