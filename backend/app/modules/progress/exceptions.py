# app/modules/progress/exceptions.py
"""Progress module exceptions."""


class EvaluationNotFound(Exception):
    """Raised when the referenced Evaluation does not exist."""
    pass


class TaskHasNoTargetSkills(Exception):
    """Raised when a Task has no TaskSkill rows — cannot update scores.

    This is a data integrity bug (every task should target at least one skill).
    We surface it loudly instead of silently doing nothing.
    """
    pass