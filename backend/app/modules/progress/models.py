"""Progress tracking — append-only log of skill score changes."""

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import CreatedAtMixin, IDMixin


class ProgressLog(Base, IDMixin, CreatedAtMixin):
    """
    One row per skill-score change. Append-only — never updated, never deleted.

    Used to:
      - Power the "score over time" line chart
      - Audit how a user's scores evolved
      - Rebuild UserSkillScore if it ever gets corrupted
    """

    __tablename__ = "progress_logs"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    score: Mapped[float] = mapped_column(Numeric(3, 1), nullable=False)
    # Optional context — link back to the task that caused this change
    user_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_tasks.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<ProgressLog(user_id={self.user_id}, skill_id={self.skill_id}, "
            f"score={self.score}, at={self.created_at})>"
        )