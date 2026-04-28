"""Pydantic schemas for the responses module."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ResponseSubmit(BaseModel):
    """Request body for POST /responses/submit.

    `content` is intentionally a free-form dict — its shape depends on
    the task_type:
      - fill-in-blanks: {"Q1": "answer", "Q2": "answer"}
      - writing:        {"text": "the user's essay..."}
      - speaking:       {"audio_url": "...", "transcript": "..."}

    Validation of the inner shape happens later, in the Evaluator agent.
    For S8 we trust the client and just persist what comes in.
    """

    user_task_id: int = Field(..., gt=0, description="UserTask being answered")
    content: dict = Field(..., description="Answers, shape depends on task_type")
    raw_text: str | None = Field(
        default=None,
        description="Optional flat text version of content, useful for writing/speaking",
    )


class ResponseRead(BaseModel):
    """Public view of a stored response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_task_id: int
    content: dict
    raw_text: str | None
    created_at: datetime
