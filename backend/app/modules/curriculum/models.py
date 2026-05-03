"""Curriculum module models — Course, UserEnrollment, EnrollmentSkillHistory.

The curriculum is structure-only. It does NOT store daily tasks (those live
in the tasks module). What a user does on Day N is decided at runtime by
the rotation engine, based on:
  - day_of_week → fixed skill (from WEEK_SCHEDULE constant)
  - last activity for that skill → next activity (round-robin)
  - week number → difficulty target
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    DateTime,
    Enum as SQLAlchemyEnum,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.mixins import IDMixin, TimestampMixin
from app.modules.tasks.models import TaskType


# Enums

class CourseLevel(str, Enum):
    """Target proficiency for a course (helps users pick)."""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class CourseStatus(str, Enum):
    """Lifecycle of a course definition."""
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class EnrollmentStatus(str, Enum):
    """Lifecycle of a user's enrollment."""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


# Course — static catalog row

class Course(Base, IDMixin, TimestampMixin):
    """A curriculum the user can enroll in.

    Holds only metadata. No daily plan stored here — the rotation engine
    generates the daily plan from constants at runtime.
    """

    __tablename__ = "courses"

    slug: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    duration_weeks: Mapped[int] = mapped_column(nullable=False)  # 24 or 48
    target_level: Mapped[CourseLevel] = mapped_column(
        SQLAlchemyEnum(CourseLevel, name="course_level_enum"), nullable=False
    )
    status: Mapped[CourseStatus] = mapped_column(
        SQLAlchemyEnum(CourseStatus, name="course_status_enum"),
        nullable=False,
        default=CourseStatus.ACTIVE,
        index=True,
    )

    def __repr__(self) -> str:
        return f"<Course(id={self.id}, slug={self.slug!r}, weeks={self.duration_weeks})>"


# UserEnrollment — user's position in a course

class UserEnrollment(Base, IDMixin, TimestampMixin):
    """A user's active path through a course.

    MVP rule: one ACTIVE enrollment per user (enforced by unique partial
    index — but we use a simple unique on user_id for MVP since we don't
    yet support multiple historical enrollments).

    `current_week` and `current_day_in_week` are advanced when the user
    completes a task (handled in a later sprint, not S7).
    """

    __tablename__ = "user_enrollments"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,        # MVP: one enrollment per user
        index=True,
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    current_week: Mapped[int] = mapped_column(nullable=False, default=1)
    current_day_in_week: Mapped[int] = mapped_column(nullable=False, default=1)
    tasks_per_day: Mapped[int] = mapped_column(nullable=False, default=2)
    status: Mapped[EnrollmentStatus] = mapped_column(
        SQLAlchemyEnum(EnrollmentStatus, name="enrollment_status_enum"),
        nullable=False,
        default=EnrollmentStatus.ACTIVE,
        index=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    course: Mapped["Course"] = relationship()
    skill_history: Mapped[list["EnrollmentSkillHistory"]] = relationship(
        back_populates="enrollment", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<UserEnrollment(id={self.id}, user_id={self.user_id}, "
            f"week={self.current_week}, day={self.current_day_in_week})>"
        )


# EnrollmentSkillHistory — rotation memory

class EnrollmentSkillHistory(Base, IDMixin, TimestampMixin):
    """Per-(enrollment, skill) record of the most recent activity used.

    The rotation engine reads this to decide the NEXT activity (round-robin).
    Example: if last_activity_type for grammar = READING, next will be WRITING.
    """

    __tablename__ = "enrollment_skill_history"

    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("user_enrollments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    last_activity_type: Mapped[TaskType | None] = mapped_column(
        SQLAlchemyEnum(TaskType, name="task_type_enum", create_type=False),
        nullable=True,    # null until first practice for this skill
    )
    times_practiced: Mapped[int] = mapped_column(nullable=False, default=0)
    last_practiced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    enrollment: Mapped["UserEnrollment"] = relationship(back_populates="skill_history")

    __table_args__ = (
        UniqueConstraint("enrollment_id", "skill_id", name="uq_enrollment_skill"),
    )

    def __repr__(self) -> str:
        return (
            f"<EnrollmentSkillHistory(enrollment_id={self.enrollment_id}, "
            f"skill_id={self.skill_id}, last={self.last_activity_type})>"
        )