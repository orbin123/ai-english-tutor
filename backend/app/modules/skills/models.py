"""Skill module models — Skill master table and per-user scores."""

from sqlalchemy import ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.mixins import CreatedAtMixin, IDMixin, TimestampMixin


class Skill(Base, IDMixin, CreatedAtMixin):
    """
    Master table for the 7 sub-skills tracked by the system.

    Pre-seeded once. Rarely changes. Only created_at, no updated_at.
    """

    __tablename__ = "skills"

    name: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    def __repr__(self) -> str:
        return f"<Skill(id={self.id}, name={self.name!r})>"


class UserSkillScore(Base, IDMixin, TimestampMixin):
    """
    Current score for a user on a specific skill (cached state).

    One row per (user, skill) pair. Updated on every relevant task.
    History lives in ProgressLog.
    """

    __tablename__ = "user_skill_scores"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Numeric(3, 1) → up to 999.9, plenty for 0.0–10.0 scores
    score: Mapped[float] = mapped_column(
        Numeric(3, 1), nullable=False, default=3.0
    )

    # Relationships
    skill: Mapped["Skill"] = relationship()

    __table_args__ = (
        UniqueConstraint("user_id", "skill_id", name="uq_user_skill"),
    )

    def __repr__(self) -> str:
        return f"<UserSkillScore(user_id={self.user_id}, skill_id={self.skill_id}, score={self.score})>"