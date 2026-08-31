"""Business Logic for authentication and user signup."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.modules.auth.exceptions import (
    EmailAlreadyExists,
    EmailNotVerified,
    InvalidCredentials,
    PasswordLoginUnavailable,
)
from app.modules.auth.models import ROLE_LEARNER, User
from app.modules.auth.repository import (
    OAuthAccountRepository,
    RoleRepository,
    UserProfileRepository,
    UserRepository,
)


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.profiles = UserProfileRepository(db)
        self.oauth_accounts = OAuthAccountRepository(db)
        self.roles = RoleRepository(db)

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

        # 3. Create User (flushes to get the id). email_verified defaults to
        # False — the account stays UNVERIFIED until the registration OTP is
        # confirmed (the route triggers the send).
        user = self.users.create(
            email=email,
            password_hash=password_hash,
            name=name,
        )

        # 4. Create default profile linked to that user
        self.profiles.create_default(user_id=user.id)
        self.roles.assign_role(user_id=user.id, role_name=ROLE_LEARNER)

        # 5. Commit transaction (user + profile + role saved together)
        self.db.commit()
        self.db.refresh(user)

        return user

    def authenticate(self, *, email: str, password: str) -> User:
        """
        Verify Login Credentials and return the user

        Raises:
            InvalidCredentials: if email not found OR password is wrong.
            PasswordLoginUnavailable: the account has no password because it
                was created via Google OAuth — the user must continue with
                Google instead of email/password.
            EmailNotVerified: credentials are correct but the email is not
                verified yet. Checked AFTER the password so verification
                state never leaks on a bad-credentials probe.
        """
        user = self.users.get_by_email(email)

        if user is None:
            raise InvalidCredentials("Invalid email or password")

        if not user.is_active:
            raise InvalidCredentials("Invalid email or password")

        # Google OAuth accounts have no password hash. Verifying against an
        # empty string makes passlib raise UnknownHashError, so branch first.
        if user.password_hash is None:
            raise PasswordLoginUnavailable()

        if not verify_password(password, user.password_hash):
            raise InvalidCredentials("Invalid email or password")

        if not user.email_verified:
            raise EmailNotVerified()

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
        # Google asserts ownership of the email, so every branch below may
        # mark the account verified — this also rescues a stuck unverified
        # password signup that logs in with Google instead.

        # 1. Existing OAuth link
        existing_link = self.oauth_accounts.get_by_provider(
            provider="google",
            provider_user_id=google_user_id,
        )
        if existing_link:
            user = existing_link.user
            needs_commit = False
            if not user.email_verified:
                self._mark_email_verified(user)
                needs_commit = True
            if self.profiles.get_by_user_id(user.id) is None:
                self.profiles.create_default(user_id=user.id)
                needs_commit = True
            if needs_commit:
                self.db.commit()
                self.db.refresh(user)
            return user, False

        # 2. User with same email exists (signed up with email/password before)
        existing_user = self.users.get_by_email(email)
        if existing_user:
            # Link their Google account to the existing user
            self.oauth_accounts.create(
                user_id=existing_user.id,
                provider="google",
                provider_user_id=google_user_id,
            )
            if not existing_user.email_verified:
                self._mark_email_verified(existing_user)
            if self.profiles.get_by_user_id(existing_user.id) is None:
                self.profiles.create_default(user_id=existing_user.id)
            self.db.commit()
            self.db.refresh(existing_user)
            return existing_user, False

        # 3. Brand new user — create everything
        new_user = self.users.create_oauth_user(email=email, name=name)
        self.profiles.create_default(user_id=new_user.id)
        self.roles.assign_role(user_id=new_user.id, role_name=ROLE_LEARNER)
        self.oauth_accounts.create(
            user_id=new_user.id,
            provider="google",
            provider_user_id=google_user_id,
        )
        self._mark_email_verified(new_user)
        self.db.commit()
        self.db.refresh(new_user)
        return new_user, True

    @staticmethod
    def _mark_email_verified(user: User) -> None:
        user.email_verified = True
        user.email_verified_at = datetime.now(timezone.utc)
