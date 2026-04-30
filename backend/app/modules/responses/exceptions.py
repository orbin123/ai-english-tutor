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

class EvaluationNotFound(Exception):
    """Raised when the referenced Evaluation does not exist."""
    pass


class FeedbackAlreadyExists(Exception):
    """Raised when feedback has already been generated for this evaluation."""
    pass


class FeedbackGenerationFailed(Exception):
    """Raised when the LLM call or its output validation fails."""
    pass
