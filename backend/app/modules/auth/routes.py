"""Auth HTTP routes - translates between HTTP and AuthService"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.exceptions import EmailAlreadyExists, InvalidCredentials
from app.modules.auth.models import User
from app.modules.auth.schemas import TokenOut, UserCreate, UserLogin, UserOut
from app.modules.auth.service import AuthService

router = APIRouter()

@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    """Register a new user"""
    try: 
        return AuthService(db).signup(
            email=payload.email,
            password=payload.password,
            name=payload.name
        )
    except EmailAlreadyExists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered"
        )

@router.post("/login", response_model=TokenOut)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> TokenOut:
    """Authenticate user and return a JWT access token"""
    try: 
        user = AuthService(db).authenticate(
            email=payload.email,
            password=payload.password,
        )
    except InvalidCredentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    token = create_access_token(data={"sub": str(user.id)})
    return TokenOut(access_token=token)

@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> User:
    """Return the currently logged-in user's profile."""
    return current_user