"""Pydantic schemas for the diagnosis API."""

from pydantic import BaseModel, Field

from app.modules.auth.models import (
    ContentExposure,
    SelfAssessedLevel,
    UserGoal,
)

# Nested input pieces
class SelfAssessmentIn(BaseModel):
    """User's own answers to the 5 self-assessment questions."""
    self_assessed_level: SelfAssessedLevel
    goal: UserGoal
    daily_time_minutes: int = Field(ge=5, le=240)
    content_exposure: ContentExposure
    interests: list[str] = Field(default_factory=list, max_length=3)


class FillBlankIn(BaseModel):
    """User's answers to the 5 fill-in-the-blank questions."""
    question_set_id: str  # e.g. "diag_fillblank_v1"
    answers: list[str] = Field(min_length=5, max_length=5)


class WritingIn(BaseModel):
    """User's writing response."""
    prompt_id: str  # e.g. "diag_writing_v1"
    response_text: str = Field(min_length=10, max_length=2000)


class ReadAloudIn(BaseModel):
    """User's audio submission for the read-aloud task.
    
    For MVP: audio_url points to a pre-uploaded file. For our stub today,
    we just accept it and return hardcoded scores.
    """
    passage_id: str  # e.g. "diag_passage_v1"
    audio_url: str
    duration_seconds: float = Field(gt=0)

# The top-level request
class DiagnosisSubmitRequest(BaseModel):
    """Full payload for POST /diagnosis/submit."""
    self_assessment: SelfAssessmentIn
    fill_blank: FillBlankIn
    writing: WritingIn
    read_aloud: ReadAloudIn

# The response
class DiagnosisSubmitResponse(BaseModel):
    """Response after diagnosis is computed."""
    skill_scores: dict[str, float]      # {"grammar": 3.0, "vocabulary": 2.7, ...}
    weakest_skills: list[str]            # 2 lowest, by score
    next_step: str = "Your first personalized task is ready."