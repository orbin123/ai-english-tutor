"""Authentication module models - User and related tables"""

from enum import Enum

from sqlalchemy import Boolean
from sqlalchemy import Enum as SQLAlchemyEnum, ForeignKey, String 
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.mixins import IDMixin, TimestampMixin


# Enums for UserProfile
class SelfAssessedLevel(str, Enum):
    """User's own opinion of their English Level"""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"

class ContentExposure(str, Enum):
    """How often user consumes English content (reading, video, etc...)"""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class UserGoal(str, Enum):
    """Why the user is learning English"""
    CASUAL = "casual"
    PROFESSIONAL = "professional"
    ACADEMIC = "academic"

# User Base Class
class User(Base, IDMixin, TimestampMixin):
    """
    Represents a user account.

    Holds only authentication-critical data (email, password hash, name).
    Learning-related data (level, goal, skill scores) lives in UserProfile
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    # Relationships
    profile: Mapped["UserProfile"] = relationship(
        back_populates="user",
        cascade = "all, delete-orphan",
        uselist=False,
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email!r})"

# User Profile Base Class
class UserProfile(Base, IDMixin, TimestampMixin):
    """
    Learning profile for a user.

    Created automatically on signup with default values.
    Updated when the user completes the diagnosis flow (or stay default if skipped)
    """

    __tablename__ = "user_profiles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    self_assessed_level: Mapped[SelfAssessedLevel] = mapped_column(
        SQLAlchemyEnum(SelfAssessedLevel, name="self_assessed_level_enum"),
        default=SelfAssessedLevel.BEGINNER,
        nullable=False,
    )

    daily_time_minutes: Mapped[int] = mapped_column(
        default=15,
        nullable=False,
    )

    content_exposure: Mapped[ContentExposure] = mapped_column(
        SQLAlchemyEnum(ContentExposure, name="content_exposure_enum"),
        default=ContentExposure.LOW,
        nullable=False,
    )

    goal: Mapped[UserGoal] = mapped_column(
        SQLAlchemyEnum(UserGoal, name="user_goal_enum"),
        default=UserGoal.CASUAL,
        nullable=False,
    )

    interests: Mapped[str] = mapped_column(
        String(500),
        default="",
        nullable=False,
    )

    diagnosis_completed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="profile")

    def __repr__(self) -> str:
        return f"<UserProfile(id={self.id}, user_id={self.user_id})>"
