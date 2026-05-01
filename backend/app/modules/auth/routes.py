"""Auth HTTP routes - translates between HTTP and AuthService"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.exceptions import EmailAlreadyExists, InvalidCredentials
from app.modules.auth.models import User
from app.modules.auth.repository import UserProfileRepository
from app.modules.auth.schemas import TokenOut, UserCreate, UserLogin, UserOut
from app.modules.auth.service import AuthService
from app.modules.curriculum.schemas import EnrollmentRead
from app.modules.curriculum.service import EnrollmentService

router = APIRouter()

@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(payload: UserCreate, db: Session = Depends(get_db)) -> UserOut:
    """Register a new user"""
    try: 
        user = AuthService(db).signup(
            email=payload.email,
            password=payload.password,
            name=payload.name
        )
    except EmailAlreadyExists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered"
        )
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        diagnosis_completed=False,
        enrollment=None,
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
def me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserOut:
    """Return the currently logged-in user's profile + diagnosis status."""
    profile = UserProfileRepository(db).get_by_user_id(current_user.id)
    enrollment = EnrollmentService(db).get_for_user(current_user.id)
    return UserOut(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        diagnosis_completed=bool(profile and profile.diagnosis_completed),
        enrollment=(
            EnrollmentRead.model_validate(enrollment)
            if enrollment is not None
            else None
        ),
    )
