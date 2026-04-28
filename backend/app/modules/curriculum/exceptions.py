"""Curriculum module exceptions."""


class AlreadyEnrolled(Exception):
    """Raised when a user tries to enroll while having an active enrollment."""
    pass


class CourseNotFound(Exception):
    """Raised when an enrollment references a non-existent course slug."""
    pass


class NotEnrolled(Exception):
    """Raised when a user action requires enrollment but none exists."""
    pass


class EnrollmentNotActive(Exception):
    """Raised when enrollment exists but its status is not 'active'."""
    pass


class NoTaskAvailable(Exception):
    """Raised when the rotation engine produced a plan but no task in the
    library matches it (empty pool for this skill+activity combo)."""
    pass