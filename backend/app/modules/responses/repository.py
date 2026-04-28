"""Data access for UserResponse — what the user submitted for a task."""

from sqlalchemy.orm import Session

from app.modules.responses.models import UserResponse


class ResponseRepository:
    """All DB access for UserResponse rows.

    Pure persistence — no validation, no ownership checks. The service
    layer enforces business rules; this layer just talks to Postgres.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # Reads
    def get_by_id(self, response_id: int) -> UserResponse | None:
        """Single response by primary key. Returns None if not found."""
        return self.db.get(UserResponse, response_id)

    def get_by_user_task_id(self, user_task_id: int) -> UserResponse | None:
        """Find the response for a given UserTask, if one exists.

        UserResponse.user_task_id is UNIQUE, so this is at most one row.
        Used by the service to detect duplicate submissions cleanly,
        instead of relying on catching IntegrityError.
        """
        return (
            self.db.query(UserResponse)
            .filter(UserResponse.user_task_id == user_task_id)
            .first()
        )

    # Writes
    def create(
        self,
        *,
        user_task_id: int,
        content: dict,
        raw_text: str | None = None,
    ) -> UserResponse:
        """Insert a new response row.

        Caller is responsible for ensuring this user_task_id has no
        existing response (otherwise the unique constraint will raise
        IntegrityError on commit).
        """
        response = UserResponse(
            user_task_id=user_task_id,
            content=content,
            raw_text=raw_text,
        )
        self.db.add(response)
        self.db.flush()
        return response
