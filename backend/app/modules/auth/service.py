"""Business Logic for authentication and user signup."""

from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.modules.auth.exceptions import EmailAlreadyExists, InvalidCredentials
from app.modules.auth.models import User
from app.modules.auth.repository import (
    OAuthAccountRepository,
    UserProfileRepository,
    UserRepository,
)


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.profiles = UserProfileRepository(db)
        self.oauth_accounts = OAuthAccountRepository(db)

    def signup(self, *, email: str, password: str, name: str) -> User:
        """Register a new user and create their default profile.
        
        Raises:
            EmailAlreadyExists: if email is already registered.
        """
        # 1. Check Uniqueness
        if self.users.email_exists(email):
            raise EmailAlreadyExists(f"Email already registered: {email}")
        
        # 2. Hash Password
        password_hash = hash_password(password)

        # 3. Create User (flushes to get the id)
        user = self.users.create(
            email=email,
            password_hash=password_hash,
            name=name,
        )

        # 4. Create default profile linked to that user
        self.profiles.create_default(user_id=user.id)

        # 5. Commit transaction (user + profile saved together)
        self.db.commit()
        self.db.refresh(user)

        return user

    def authenticate(self, *, email: str, password: str) -> User:
        """
        Verify Login Credentials and return the user

        Raises:
            InvalidCredentials: if email not found OR password is wrong.
        """
        user = self.users.get_by_email(email)

        if user is None:
            raise InvalidCredentials("Invalid email or password")

        if not verify_password(password, user.password_hash or ""):
            raise InvalidCredentials("Invalid email or password")

        return user

    def get_or_create_google_user(
        self,
        *,
        google_user_id: str,
        email: str,
        name: str,
    ) -> tuple[User, bool]:
        """
        Find or create a user based on their Google account.

        Flow:
          1. Check if we have an OAuthAccount for this google_user_id.
             → Yes: return the linked user. Done.
          2. Check if a user already exists with this email.
             → Yes: link their account to Google, return the user.
          3. Neither exists: create a new user (no password) + profile + OAuth link.

        Returns:
            (user, is_new_user)
            is_new_user = True if we just created the account (→ send to diagnosis).
        """
        # 1. Existing OAuth link
        existing_link = self.oauth_accounts.get_by_provider(
            provider="google",
            provider_user_id=google_user_id,
        )
        if existing_link:
            return existing_link.user, False

        # 2. User with same email exists (signed up with email/password before)
        existing_user = self.users.get_by_email(email)
        if existing_user:
            # Link their Google account to the existing user
            self.oauth_accounts.create(
                user_id=existing_user.id,
                provider="google",
                provider_user_id=google_user_id,
            )
            self.db.commit()
            self.db.refresh(existing_user)
            return existing_user, False

        # 3. Brand new user — create everything
        new_user = self.users.create_oauth_user(email=email, name=name)
        self.profiles.create_default(user_id=new_user.id)
        self.oauth_accounts.create(
            user_id=new_user.id,
            provider="google",
            provider_user_id=google_user_id,
        )
        self.db.commit()
        self.db.refresh(new_user)
        return new_user, True
