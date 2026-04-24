"""Authentication module models - User and related tables"""

from sqlalchemy import String 
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import IDMixin, TimestampMixin


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

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email!r})"