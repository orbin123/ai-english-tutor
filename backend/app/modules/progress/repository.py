"""Data access for ProgressLog — append-only history of skill score changes."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.modules.progress.models import ProgressLog


class ProgressLogRepository:
    """All DB access for ProgressLog rows.

    Append-only by design: no update(), no delete(). The full history
    of every score change is kept forever — used for charts and audits.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # Reads
    def list_for_user_skill(
        self,
        *,
        user_id: int,
        skill_id: int,
        days: int,
    ) -> list[ProgressLog]:
        """Return history rows for one (user, skill) within the last N days.

        Ordered oldest → newest, so the line chart can render left to right
        without the frontend having to sort.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return (
            self.db.query(ProgressLog)
            .filter(
                ProgressLog.user_id == user_id,
                ProgressLog.skill_id == skill_id,
                ProgressLog.created_at >= cutoff,
            )
            .order_by(ProgressLog.created_at.asc())
            .all()
        )

    # Writes
    def create(
        self,
        *,
        user_id: int,
        skill_id: int,
        score: float,
        user_task_id: int | None = None,
    ) -> ProgressLog:
        """Insert one history row. Service layer handles the commit."""
        row = ProgressLog(
            user_id=user_id,
            skill_id=skill_id,
            score=score,
            user_task_id=user_task_id,
        )
        self.db.add(row)
        self.db.flush()
        return row