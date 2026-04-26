"""Auth Dependencies - reusable across all protected routes."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token
from app.modules.auth.models import User
from app.modules.auth.repository import UserRepository

bearer_scheme = HTTPBearer()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the currently logged-in user from the JWT in the request.

    Raises:
        HTTPException 401: token missing, invalid, expired, or user not found.
    """

    token = credentials.credentials

    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_token(token)
    
    if payload is None:
        raise credentials_error

    user_id_raw = payload.get("sub")
    
    if user_id_raw is None:
        raise credentials_error

    # JWT 'sub' is always a string by spec, so we cast back to int
    try:
        user_id = int(user_id_raw)
    except (TypeError, ValueError):
        raise credentials_error

    user = UserRepository(db).get_by_id(user_id)
    if user is None:
        raise credentials_error

    return user