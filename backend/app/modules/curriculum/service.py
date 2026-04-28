"""Business logic for course enrollment.

Routes call this. Repos do the data work. Service decides:
  - Does the course exist? (404)
  - Is the user already enrolled? (409 — MVP: one enrollment per user)
  - When to commit
"""

from sqlalchemy.orm import Session

from app.modules.curriculum.exceptions import AlreadyEnrolled, CourseNotFound
from app.modules.curriculum.models import UserEnrollment
from app.modules.curriculum.repository import (
    CourseRepository,
    UserEnrollmentRepository,
)


class EnrollmentService:
    """Manages a user's enrollment in a course."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.course_repo = CourseRepository(db)
        self.enrollment_repo = UserEnrollmentRepository(db)

    def enroll(self, *, user_id: int, course_slug: str) -> UserEnrollment:
        """Enroll a user in the course identified by slug.

        Raises:
            CourseNotFound: slug doesn't match any course.
            AlreadyEnrolled: user already has an enrollment (MVP rule).
        """
        course = self.course_repo.get_by_slug(course_slug)
        if course is None:
            raise CourseNotFound(f"No course with slug={course_slug!r}")

        existing = self.enrollment_repo.get_for_user(user_id)
        if existing is not None:
            raise AlreadyEnrolled(
                f"User {user_id} already enrolled in {existing.course.slug!r}"
            )

        enrollment = self.enrollment_repo.create(
            user_id=user_id,
            course_id=course.id,
        )
        self.db.commit()
        self.db.refresh(enrollment)
        return enrollment

    def get_for_user(self, user_id: int) -> UserEnrollment | None:
        """Return the user's current enrollment, or None if not enrolled.

        Pure read — no commit. Useful for /me/enrollment endpoints later.
        """
        return self.enrollment_repo.get_for_user(user_id)