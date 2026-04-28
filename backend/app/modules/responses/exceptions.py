"""Responses module exceptions."""


class UserTaskNotFound(Exception):
    """Raised when the referenced UserTask does not exist."""
    pass


class NotResponseOwner(Exception):
    """Raised when a user tries to submit a response for someone else's UserTask."""
    pass


class UserTaskNotSubmittable(Exception):
    """Raised when the UserTask is in a state that cannot accept submissions
    (already COMPLETED or SKIPPED)."""
    pass


class ResponseAlreadySubmitted(Exception):
    """Raised when a response already exists for this UserTask
    (DB unique constraint on user_task_id)."""
    pass
