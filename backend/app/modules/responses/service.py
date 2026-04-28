"""Business logic for accepting a user's response to an assigned task."""

from sqlalchemy.orm import Session

from app.modules.responses.exceptions import (
    NotResponseOwner,
    ResponseAlreadySubmitted,
    UserTaskNotFound,
    UserTaskNotSubmittable,
)
from app.modules.responses.models import UserResponse
from app.modules.responses.repository import ResponseRepository
from app.modules.tasks.models import UserTaskStatus
from app.modules.tasks.repository import UserTaskRepository


# Statuses that allow a response to be submitted
_SUBMITTABLE_STATUSES = {UserTaskStatus.PENDING, UserTaskStatus.IN_PROGRESS}


class ResponseService:
    """Orchestrates 'user submits answers for a task' end-to-end.

    Steps:
      1. Load the UserTask (404 if missing).
      2. Verify ownership — the submitter must be the assigned user (403).
      3. Verify state — task must be PENDING or IN_PROGRESS (409).
      4. Verify no prior submission (409).
      5. Create UserResponse row.
      6. Flip UserTask.status → IN_PROGRESS (idempotent).
      7. Commit, return the response.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.user_task_repo = UserTaskRepository(db)
        self.response_repo = ResponseRepository(db)

    def submit(
        self,
        *,
        user_id: int,
        user_task_id: int,
        content: dict,
        raw_text: str | None = None,
    ) -> UserResponse:
        # 1. Load the assignment
        user_task = self.user_task_repo.get_by_id(user_task_id)
        if user_task is None:
            raise UserTaskNotFound(f"UserTask {user_task_id} does not exist")

        # 2. Ownership check
        if user_task.user_id != user_id:
            raise NotResponseOwner(
                f"User {user_id} cannot submit a response for UserTask "
                f"{user_task_id} (owner: {user_task.user_id})"
            )

        # 3. State check
        if user_task.status not in _SUBMITTABLE_STATUSES:
            raise UserTaskNotSubmittable(
                f"UserTask {user_task_id} is {user_task.status.value} — "
                f"cannot submit"
            )

        # 4. Duplicate-submission check
        existing = self.response_repo.get_by_user_task_id(user_task_id)
        if existing is not None:
            raise ResponseAlreadySubmitted(
                f"UserTask {user_task_id} already has response {existing.id}"
            )

        # 5. Create the response row
        response = self.response_repo.create(
            user_task_id=user_task_id,
            content=content,
            raw_text=raw_text,
        )

        # 6. Move the assignment forward.
        # Only PENDING → IN_PROGRESS; if it was already IN_PROGRESS keep
        # it (don't overwrite — could happen if a future feature flips it
        # to IN_PROGRESS earlier, e.g. when the user opens the task).
        if user_task.status == UserTaskStatus.PENDING:
            user_task.status = UserTaskStatus.IN_PROGRESS

        # 7. One commit for both writes — atomic.
        self.db.commit()
        self.db.refresh(response)
        return response
