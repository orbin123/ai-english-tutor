"""Data access for User, UserProfile, and OAuthAccount."""

from sqlalchemy.orm import Session

from app.modules.auth.models import OAuthAccount, User, UserProfile


class UserRepository:
    """All DB access for the User table goes through this class."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # Reads
    def get_by_id(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        return (
            self.db.query(User)
            .filter(User.email == email.lower())
            .first()
        )

    def email_exists(self, email: str) -> bool:
        return self.get_by_email(email) is not None

    # Writes
    def create(self, *, email: str, password_hash: str, name: str) -> User:
        user = User(
            email=email.lower(),
            password_hash=password_hash,
            name=name,
        )
        self.db.add(user)
        self.db.flush()  # populate user.id without committing
        return user

    def create_oauth_user(self, *, email: str, name: str) -> User:
        """Create a user that has no password (Google OAuth user)."""
        user = User(
            email=email.lower(),
            password_hash=None,
            name=name,
        )
        self.db.add(user)
        self.db.flush()
        return user

    def delete(self, user: User) -> None:
        self.db.delete(user)


class UserProfileRepository:
    """All DB access for UserProfile."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_user_id(self, user_id: int) -> UserProfile | None:
        return (
            self.db.query(UserProfile)
            .filter(UserProfile.user_id == user_id)
            .first()
        )

    def create_default(self, user_id: int) -> UserProfile:
        """Create a profile with default values (used right after signup)."""
        profile = UserProfile(user_id=user_id)
        self.db.add(profile)
        self.db.flush()
        return profile


class OAuthAccountRepository:
    """All DB access for OAuthAccount."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_provider(
        self, provider: str, provider_user_id: str
    ) -> OAuthAccount | None:
        """Find an existing OAuth link by provider + their user id."""
        return (
            self.db.query(OAuthAccount)
            .filter(
                OAuthAccount.provider == provider,
                OAuthAccount.provider_user_id == provider_user_id,
            )
            .first()
        )

    def create(
        self, *, user_id: int, provider: str, provider_user_id: str
    ) -> OAuthAccount:
        account = OAuthAccount(
            user_id=user_id,
            provider=provider,
            provider_user_id=provider_user_id,
        )
        self.db.add(account)
        self.db.flush()
        return account
