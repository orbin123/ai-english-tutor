"""Pydantic schemas for learning session HTTP + WebSocket payloads."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# --- REST -------------------------------------------------------------


class LearningSessionSnapshotRead(BaseModel):
    """Read-only snapshot of a completed chat session for the history page."""

    session_id: str
    daily_session_id: int
    topic: str
    skill_name: str
    task_type: str
    phase: str
    messages: list[dict[str, Any]]
    pre_generated_tasks: dict[str, Any] | None
    user_submission: dict[str, Any] | None
    evaluation: dict[str, Any] | None
    feedback: dict[str, Any] | None
    task_queue: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime


class LearningSessionStateRead(BaseModel):
    """REST hydrate snapshot the chat UI renders before/without the WebSocket.

    Unlike ``LearningSessionSnapshotRead`` (raw row dump for history views) this
    carries the derived resume checkpoint so the client can land on the correct
    actionable step and show compact summaries for completed activities.
    """

    session_id: str
    daily_session_id: int
    topic: str
    skill_name: str
    task_type: str
    phase: str
    messages: list[dict[str, Any]] = Field(default_factory=list)
    task_queue: list[dict[str, Any]] = Field(default_factory=list)
    current_task: dict[str, Any] | None = None
    current_sequence: int | None = None
    last_evaluation: dict[str, Any] | None = None
    last_feedback: dict[str, Any] | None = None
    completed_sequences: list[int] = Field(default_factory=list)
    # Compact, read-only summary per completed activity (sequence, label,
    # widget, raw_score) so a returning learner sees what they finished without
    # the full evaluation/feedback widgets being replayed.
    completed_activities: list[dict[str, Any]] = Field(default_factory=list)
    teaching_completed: bool = False
    last_resumable_phase: str = "teaching"
    daily_completed: bool = False
    blueprint: dict[str, Any] | None = None


class StartSessionRequest(BaseModel):
    """Start a chat session.

    When ``daily_session_id`` is supplied the chat is layered on top of an
    existing V2 DailySession. Without it, the service resolves today's
    DailySession from `UserCoursePreference` (creating one if needed).
    """

    daily_session_id: Optional[int] = None


class StartSessionResponse(BaseModel):
    session_id: str
    daily_session_id: int
    topic: str
    skill_name: str
    task_type: str
    message: str = "Session ready"


class RegenerateFeedbackResponse(BaseModel):
    """Response for POST .../activities/{sequence}/regenerate-feedback.

    Carries a freshly generated feedback card (same shape the WS ``feedback_card``
    event delivers) so the chat UI can swap it in place — the graded score and
    task are untouched.
    """

    sequence: int
    feedback: dict[str, Any]


# --- WebSocket --------------------------------------------------------


class WSIncomingMessage(BaseModel):
    """Message shape sent FROM the frontend chat composer."""

    type: str  # "user_message" | "task_submission" | "follow_up_action" | "ping"
    content: Optional[str] = None
    answers: Optional[dict] = None
    action: Optional[str] = None


class WSOutgoingMessage(BaseModel):
    """Message shape sent FROM the backend back to the frontend."""

    type: str  # "chat_message" | "chat_stream_*" | "ui_event" | "error" | "pong"
    role: Optional[str] = None
    content: Optional[str] = None
    stream_id: Optional[str] = None
    widget: Optional[str] = None
    payload: Optional[dict] = None
    actions: Optional[list[str]] = None
    event_id: Optional[str] = None
    event_type: Optional[str] = None
    phase: Optional[str] = None
    activity_id: Optional[str] = None
    sequence: Optional[int] = None
    archetype_id: Optional[str] = None
    task_widget: Optional[str] = None
    evaluation_widget: Optional[str] = None
    feedback_widget: Optional[str] = None
    activity_contract: Optional[dict] = None
    payload_kind: Optional[str] = None
    # Machine-readable error classifier (e.g. "task_generation_failed"). Lets the
    # chat client distinguish a recoverable task-generation failure (offer a retry
    # affordance) from an unrecoverable one. Only set on `type == "error"`.
    code: Optional[str] = None
