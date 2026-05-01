"""Pydantic schemas for auth module - API boundary contracts"""

from pydantic import BaseModel, EmailStr, Field

from app.modules.curriculum.schemas import EnrollmentRead

class UserCreate(BaseModel):
    """Input schema for signup. What the client sends."""
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=100)

class UserLogin(BaseModel):
    """Input schema for login"""
    email: EmailStr
    password: str

class UserOut(BaseModel):
    """Output schema - What we send back to the client. Never includes password_hash"""
    id: int
    email: EmailStr
    name: str
    diagnosis_completed: bool = False  # tells frontend where to send the user
    enrollment: EnrollmentRead | None = None

    model_config = {"from_attributes": True}

class TokenOut(BaseModel):
    """Output Schema returned after successful login."""
    access_token: str
    token_type: str = "bearer"
