"""Auth HTTP routes - translates between HTTP and AuthService"""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
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

# ---------------------------------------------------------------------------
# Standard email / password routes
# ---------------------------------------------------------------------------

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

    token = create_access_token(data={
        "sub": str(user.id),
        "is_superuser": user.is_superuser,
    })
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
        is_superuser=current_user.is_superuser,
        diagnosis_completed=bool(profile and profile.diagnosis_completed),
        enrollment=(
            EnrollmentRead.model_validate(enrollment)
            if enrollment is not None
            else None
        ),
    )


# ---------------------------------------------------------------------------
# Google OAuth routes
# ---------------------------------------------------------------------------

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

GOOGLE_SCOPES = "openid email profile"


@router.get("/google/login")
def google_login() -> RedirectResponse:
    """
    Step 1 — Redirect the user to Google's consent screen.

    The frontend calls this URL. The browser is redirected to Google.
    After consent, Google redirects back to /auth/google/callback.
    """
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "access_type": "offline",
        "prompt": "select_account",  # always show account picker
    }
    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url=f"{GOOGLE_AUTH_URL}?{query_string}")


@router.get("/google/callback")
def google_callback(
    code: str = Query(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """
    Step 2 — Google redirects here with a one-time `code`.

    We exchange the code for an access token, fetch the user's profile,
    then find-or-create a user in our DB, issue a JWT, and redirect
    the frontend to the right page (dashboard or diagnosis).
    """
    # --- Exchange code for access token ---
    token_response = httpx.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        },
    )

    if token_response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to exchange Google code for token",
        )

    google_access_token = token_response.json().get("access_token")

    # --- Fetch user info from Google ---
    userinfo_response = httpx.get(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {google_access_token}"},
    )

    if userinfo_response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to fetch Google user info",
        )

    google_user = userinfo_response.json()
    google_user_id: str = google_user["sub"]        # Google's unique user ID
    email: str = google_user["email"]
    name: str = google_user.get("name", email.split("@")[0])

    # --- Find or create the user in our DB ---
    user, is_new = AuthService(db).get_or_create_google_user(
        google_user_id=google_user_id,
        email=email,
        name=name,
    )

    # --- Issue our own JWT ---
    jwt_token = create_access_token(data={
        "sub": str(user.id),
        "is_superuser": user.is_superuser,
    })

    # --- Redirect frontend with token ---
    # We pass the token as a query param. The frontend reads it and stores it.
    frontend_base = settings.frontend_url
    destination = "diagnosis" if is_new else "dashboard"
    redirect_url = f"{frontend_base}/callback?token={jwt_token}&next={destination}"

    return RedirectResponse(url=redirect_url)
