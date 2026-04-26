"""Business Logic for authentication and user signup."""

from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.modules.auth.exceptions import EmailAlreadyExists, InvalidCredentials
from app.modules.auth.models import User
from app.modules.auth.repository import UserRepository, UserProfileRepository

class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.profiles = UserProfileRepository(db)

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
        Vertify Login Credentials and return the user

        Raises:
            InvalidCredentials: if email not found OR password is wrong.
        """
        user = self.users.get_by_email(email)

        if user is None:
            raise InvalidCredentials("Invalid email or password")

        if not verify_password(password, user.password_hash):
            raise InvalidCredentials("Invalid email or password")

        return user

    
