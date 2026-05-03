"""Business logic for assigning the next task to a user.

Orchestrates: enrollment → rotation engine → task pool → assignment +
history update.
"""

from sqlalchemy.orm import Session

from app.modules.curriculum.exceptions import (
    EnrollmentNotActive,
    NoTaskAvailable,
    NotEnrolled,
)
from app.modules.curriculum.models import EnrollmentStatus, UserEnrollment
from app.modules.curriculum.repository import (
    EnrollmentSkillHistoryRepository,
    UserEnrollmentRepository,
)
from app.modules.curriculum.rotation import RotationEngine
from app.modules.skills.repository import SkillRepository
from app.modules.tasks.models import UserTask
from app.modules.tasks.repository import TaskRepository, UserTaskRepository


class DayNotComplete(Exception):
    """Raised when mark_day_complete is called but not all tasks are done."""
    pass


class TaskService:
    """Orchestrates day-bundle creation and day-completion logic."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.enrollment_repo = UserEnrollmentRepository(db)
        self.history_repo = EnrollmentSkillHistoryRepository(db)
        self.skill_repo = SkillRepository(db)
        self.task_repo = TaskRepository(db)
        self.user_task_repo = UserTaskRepository(db)
        self.engine = RotationEngine()

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _load_enrollment(self, user_id: int) -> UserEnrollment:
        """Load and validate the user's active enrollment."""
        enrollment = self.enrollment_repo.get_for_user(user_id)
        if enrollment is None:
            raise NotEnrolled(f"User {user_id} is not enrolled in any course")
        if enrollment.status != EnrollmentStatus.ACTIVE:
            raise EnrollmentNotActive(
                f"Enrollment {enrollment.id} status is {enrollment.status.value}"
            )
        return enrollment

    def _create_one_task(
        self,
        *,
        user_id: int,
        enrollment: UserEnrollment,
        skill_name_to_id: dict[str, int],
        history_by_skill_id: dict[int, str | None],
    ) -> UserTask:
        """Run the rotation engine once, pick a task from the pool, assign it,
        and update rotation memory. Does NOT commit."""
        plan = self.engine.decide(
            week_number=enrollment.current_week,
            day_in_week=enrollment.current_day_in_week,
            skill_name_to_id=skill_name_to_id,
            history_by_skill_id=history_by_skill_id,
        )

        task = self.task_repo.find_for_plan(
            skill_id=plan.skill_id,
            activity_type=plan.activity_type,
            target_difficulty=plan.target_difficulty,
            # MVP shortcut: do NOT exclude completed tasks. With only one
            # seeded grammar reading task, excluding completions would
            # 404 the user on their second visit.
            # TODO: once we've seeded enough variety per (skill, activity)
            # cell, set this to user_id so users see fresh content.
            exclude_completed_by_user_id=None,
        )
        if task is None:
            raise NoTaskAvailable(
                f"No task in pool for skill={plan.skill_name}, "
                f"activity={plan.activity_type.value}, "
                f"difficulty~{plan.target_difficulty}"
            )

        assignment = self.user_task_repo.assign(
            user_id=user_id,
            task_id=task.id,
            enrollment_id=enrollment.id,
        )

        # Update rotation memory so the NEXT call picks a different activity
        self.history_repo.upsert_after_assignment(
            enrollment_id=enrollment.id,
            skill_id=plan.skill_id,
            activity_type=plan.activity_type,
        )

        return assignment

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def get_or_create_day_bundle(self, *, user_id: int) -> list[UserTask]:
        """Return the user's current day bundle, creating tasks if needed.

        Idempotent: if the bundle already has enrollment.tasks_per_day
        non-completed tasks, returns them as-is. Otherwise creates more
        until the bundle is full.

        Each new task in the bundle is created via the rotation engine,
        so tasks within the same day may have DIFFERENT activities for
        the same skill (round-robin advances after each assignment).

        Raises:
            NotEnrolled: user has no enrollment.
            EnrollmentNotActive: enrollment status != ACTIVE.
            NoTaskAvailable: rotation engine produced a plan but task pool
                is empty for that (skill, activity) combo.
        """
        enrollment = self._load_enrollment(user_id)

        # Check how many open tasks already exist for the current day
        existing = self.user_task_repo.find_active_for_enrollment_day(
            enrollment_id=enrollment.id,
        )

        needed = enrollment.tasks_per_day - len(existing)
        if needed <= 0:
            return existing

        # Build lookup maps once
        skill_name_to_id = self.skill_repo.name_to_id_map()
        history_rows = self.history_repo.list_for_enrollment(enrollment.id)
        history_by_skill_id = {
            h.skill_id: h.last_activity_type for h in history_rows
        }

        new_tasks: list[UserTask] = []
        for _ in range(needed):
            assignment = self._create_one_task(
                user_id=user_id,
                enrollment=enrollment,
                skill_name_to_id=skill_name_to_id,
                history_by_skill_id=history_by_skill_id,
            )
            new_tasks.append(assignment)

            # Update the in-memory history map so the next iteration picks
            # a different activity (the DB row was already updated via
            # upsert_after_assignment, but the local dict needs refreshing).
            # We re-read the plan's skill_id from the task to stay generic.
            plan = self.engine.decide(
                week_number=enrollment.current_week,
                day_in_week=enrollment.current_day_in_week,
                skill_name_to_id=skill_name_to_id,
                history_by_skill_id=history_by_skill_id,
            )
            # Refresh from the DB-flushed history
            refreshed_rows = self.history_repo.list_for_enrollment(enrollment.id)
            history_by_skill_id = {
                h.skill_id: h.last_activity_type for h in refreshed_rows
            }

        # Commit everything
        self.db.commit()

        # Refresh all objects so they're serializable
        bundle = existing + new_tasks
        for ut in bundle:
            self.db.refresh(ut)
            self.db.refresh(ut.task)

        return bundle

    def mark_day_complete(self, *, user_id: int) -> UserEnrollment:
        """Advance the enrollment day if ALL tasks in the bundle are done.

        Checks that every UserTask for the current enrollment day has
        status == COMPLETED. If any are still open, raises DayNotComplete.

        Day/week rollover logic:
          - current_day_in_week increments 1 → 7
          - when day goes past 7, resets to 1 and current_week increments

        Returns the updated enrollment (for the response).

        Raises:
            NotEnrolled / EnrollmentNotActive: standard guards.
            DayNotComplete: at least one task is still pending/in_progress.
        """
        enrollment = self._load_enrollment(user_id)

        # Any open tasks left?
        open_tasks = self.user_task_repo.find_active_for_enrollment_day(
            enrollment_id=enrollment.id,
        )
        if open_tasks:
            raise DayNotComplete(
                f"{len(open_tasks)} task(s) still pending for the current day"
            )

        # Advance day
        enrollment = self.enrollment_repo.advance_day(enrollment)

        self.db.commit()
        self.db.refresh(enrollment)
        return enrollment