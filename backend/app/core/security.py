"""Security Utilities: password hashing and JWT Tokens"""

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# Configure bcrypt as the password hashing scheme.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(plain_password: str) -> str:
    """
    Hash a plain password using bcrypt.

    Used during user registration before storing in DB.
    """
    return pwd_context.hash(plain_password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Check if a plain password matches a stored hash.

    Used during login. Returns True if match, Fasle otherwise.
    Never raises an exception for wrong passwords - just returns False
    """
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """
    Create a signed JWT access token.

    Args:
        data: Claims to embed in the token (e.g. {"sub": user_id}).
        expires_delta: Optional custom expiry. Defaults to settings value.

    Returns:
        Encoded JWT string (signed with JWT_SECRET).
    """
    to_encode = data.copy()

    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.jwt_access_token_expire_minutes)

    expire_at = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire_at})

    return jwt.encode(
        to_encode,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

def decode_token(token: str) -> dict[str, Any] | None:
    """
    Decode and verify a JWT token.

    Returns:
        The token's payload (claims dict) if valid.
        None if the token is invalid, expired, or tampered with.
    """
    try: 
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError:
        return None