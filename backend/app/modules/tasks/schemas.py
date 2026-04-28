"""Pydantic schemas for the tasks module."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.modules.tasks.models import TaskStatus, TaskType, UserTaskStatus


class TaskRead(BaseModel):
    """Public view of a task template (the actual content the user works on)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    task_type: TaskType
    difficulty: int
    status: TaskStatus
    content: dict   # JSONB blob — shape varies by task_type


class UserTaskRead(BaseModel):
    """A task assigned to a user, with the task content embedded."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    task_id: int
    enrollment_id: int | None
    status: UserTaskStatus
    completed_at: datetime | None
    created_at: datetime

    task: TaskRead   # embedded — frontend gets everything in one shot