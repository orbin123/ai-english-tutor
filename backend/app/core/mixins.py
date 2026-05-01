"""Reusable model mixins - shared columns for all models"""

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

# ID Mixin
class IDMixin:
    """
    Adds an auto-incrementing integer primary key.

    Every table that inherits this gets an `id` column.
    """

    id: Mapped[int] = mapped_column(primary_key=True)

# CreatedAt Mixin
class CreatedAtMixin:
    """
    Adds a `created_at` timestamp (UTC)

    Set by the database at INSERT time.
    Used by every table (state and event tables alike)
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

# UpdatedAt Mixin
class UpdatedAtMixin:
    """
    Adds an `updated_at` timestamp (UTC).

    Set by the database at INSERT time, updated automatically on UPDATE.
    Only used by MUTABLE tables (users, profiles, scores) — not events.
    """

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),   # set on INSERT
        onupdate=func.now(),         # refreshed on every UPDATE
        nullable=False,
    )

# Timestamp Mixin (convenience)
class TimestampMixin(CreatedAtMixin, UpdatedAtMixin):
    """
    Combines both timestamps.

    Use this for mutable tables. For append-only event tables,
    use CreatedAtMixin alone.
    """

    pass
