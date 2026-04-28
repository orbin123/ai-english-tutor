"""Data access for curriculum module — Course, UserEnrollment, EnrollmentSkillHistory."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.modules.curriculum.models import (
    Course,
    CourseStatus,
    EnrollmentSkillHistory,
    EnrollmentStatus,
    UserEnrollment,
)
from app.modules.tasks.models import TaskType


class CourseRepository:
    """Read-only access to the courses catalog.

    Courses are seeded and rarely changed — no create/update/delete here yet.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, course_id: int) -> Course | None:
        """Single course by primary key."""
        return self.db.get(Course, course_id)

    def get_by_slug(self, slug: str) -> Course | None:
        """Look up by stable slug (e.g. 'beginner-24w'). Returns None if missing."""
        return self.db.query(Course).filter(Course.slug == slug).first()

    def list_active(self) -> list[Course]:
        """All courses available for enrollment, ordered by duration."""
        return (
            self.db.query(Course)
            .filter(Course.status == CourseStatus.ACTIVE)
            .order_by(Course.duration_weeks, Course.id)
            .all()
        )
    
class UserEnrollmentRepository:
    """All DB access for a user's enrollment in a course.

    MVP rule: one enrollment per user (DB enforces via UNIQUE on user_id).
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # Reads
    def get_by_id(self, enrollment_id: int) -> UserEnrollment | None:
        return self.db.get(UserEnrollment, enrollment_id)

    def get_for_user(self, user_id: int) -> UserEnrollment | None:
        """Return the user's enrollment row, or None if not enrolled.

        Eager-loads the course so callers can read `enrollment.course.slug`
        without an extra query.
        """
        return (
            self.db.query(UserEnrollment)
            .filter(UserEnrollment.user_id == user_id)
            .options(joinedload(UserEnrollment.course))
            .first()
        )

    # Writes
    def create(self, *, user_id: int, course_id: int) -> UserEnrollment:
        """Create a new enrollment at week=1, day=1, status=ACTIVE.

        Caller (service) must check 'already enrolled' before calling this —
        the DB UNIQUE on user_id will raise if violated.
        """
        enrollment = UserEnrollment(
            user_id=user_id,
            course_id=course_id,
            current_week=1,
            current_day_in_week=1,
            status=EnrollmentStatus.ACTIVE,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(enrollment)
        self.db.flush()
        return enrollment

    def advance_day(self, enrollment: UserEnrollment) -> UserEnrollment:
        """Move forward by one day. Wraps to the next week after day 7.

        NOT called from S7 — kept here for the future 'task completion' sprint.
        Documented now so the contract is obvious.
        """
        if enrollment.current_day_in_week < 7:
            enrollment.current_day_in_week += 1
        else:
            enrollment.current_day_in_week = 1
            enrollment.current_week += 1
        self.db.flush()
        return enrollment
    
class EnrollmentSkillHistoryRepository:
    """Per-(enrollment, skill) rotation memory.

    Used by the rotation engine to decide 'last activity for grammar was
    READING, so next should be WRITING'. Not user-facing.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # Reads
    def get_one(
        self, *, enrollment_id: int, skill_id: int
    ) -> EnrollmentSkillHistory | None:
        """Single row by (enrollment, skill). None if never practiced this skill."""
        return (
            self.db.query(EnrollmentSkillHistory)
            .filter(
                EnrollmentSkillHistory.enrollment_id == enrollment_id,
                EnrollmentSkillHistory.skill_id == skill_id,
            )
            .first()
        )

    def list_for_enrollment(
        self, enrollment_id: int
    ) -> list[EnrollmentSkillHistory]:
        """All skill-history rows for one enrollment. Used by rotation engine
        to see the full picture across all skills."""
        return (
            self.db.query(EnrollmentSkillHistory)
            .filter(EnrollmentSkillHistory.enrollment_id == enrollment_id)
            .all()
        )

    # Writes
    def upsert_after_assignment(
        self,
        *,
        enrollment_id: int,
        skill_id: int,
        activity_type: TaskType,
    ) -> EnrollmentSkillHistory:
        """Record that 'this skill was just practiced with this activity'.

        Insert if missing, update if exists. Increments times_practiced and
        stamps last_practiced_at = now.
        """
        existing = self.get_one(enrollment_id=enrollment_id, skill_id=skill_id)
        now = datetime.now(timezone.utc)

        if existing is not None:
            existing.last_activity_type = activity_type
            existing.times_practiced += 1
            existing.last_practiced_at = now
            self.db.flush()
            return existing

        new_row = EnrollmentSkillHistory(
            enrollment_id=enrollment_id,
            skill_id=skill_id,
            last_activity_type=activity_type,
            times_practiced=1,
            last_practiced_at=now,
        )
        self.db.add(new_row)
        self.db.flush()
        return new_row