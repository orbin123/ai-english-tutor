"""usage quota counters table

Revision ID: t0u1v2w3x456
Revises: s9t0u1v2w345
Create Date: 2026-08-19 20:00:00.000000

Persistent daily/monthly counters for Azure zero-cost capacity enforcement.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "t0u1v2w3x456"
down_revision: Union[str, Sequence[str], None] = "s9t0u1v2w345"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usage_quota_counters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("period_type", sa.String(length=16), nullable=False),
        sa.Column("period_key", sa.String(length=16), nullable=False),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("count", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "period_type",
            "period_key",
            "metric",
            name="uq_usage_quota_counters_period_metric",
        ),
    )


def downgrade() -> None:
    op.drop_table("usage_quota_counters")
