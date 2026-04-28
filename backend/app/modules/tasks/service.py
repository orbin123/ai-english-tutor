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
from app.modules.curriculum.models import EnrollmentStatus
from app.modules.curriculum.repository import (
    EnrollmentSkillHistoryRepository,
    UserEnrollmentRepository,
)
from app.modules.curriculum.rotation import RotationEngine
from app.modules.skills.repository import SkillRepository
from app.modules.tasks.models import UserTask
from app.modules.tasks.repository import TaskRepository, UserTaskRepository


class TaskService:
    """Orchestrates 'give me my next task' end-to-end."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.enrollment_repo = UserEnrollmentRepository(db)
        self.history_repo = EnrollmentSkillHistoryRepository(db)
        self.skill_repo = SkillRepository(db)
        self.task_repo = TaskRepository(db)
        self.user_task_repo = UserTaskRepository(db)
        self.engine = RotationEngine()

    def pick_next(self, *, user_id: int) -> UserTask:
        """Return the user's current task, creating one if needed.

        Idempotent: if a non-completed UserTask already exists for the
        current enrollment day, returns that. Otherwise creates a new one.

        Raises:
            NotEnrolled: user has no enrollment.
            EnrollmentNotActive: enrollment status != ACTIVE.
            NoTaskAvailable: rotation engine produced a plan but task pool
                is empty for that (skill, activity) combo.
        """
        # 1. Load enrollment
        enrollment = self.enrollment_repo.get_for_user(user_id)
        if enrollment is None:
            raise NotEnrolled(f"User {user_id} is not enrolled in any course")
        if enrollment.status != EnrollmentStatus.ACTIVE:
            raise EnrollmentNotActive(
                f"Enrollment {enrollment.id} status is {enrollment.status.value}"
            )

        # 2. Idempotency check — already have an open task for this day?
        existing = self.user_task_repo.find_active_for_enrollment_day(
            enrollment_id=enrollment.id
        )
        if existing is not None:
            return existing

        # 3. Run the rotation engine to decide today's plan
        skill_name_to_id = self.skill_repo.name_to_id_map()
        history_rows = self.history_repo.list_for_enrollment(enrollment.id)
        history_by_skill_id = {
            h.skill_id: h.last_activity_type for h in history_rows
        }

        plan = self.engine.decide(
            week_number=enrollment.current_week,
            day_in_week=enrollment.current_day_in_week,
            skill_name_to_id=skill_name_to_id,
            history_by_skill_id=history_by_skill_id,
        )

        # 4. Pick a matching task from the library
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

        # 5. Create UserTask
        assignment = self.user_task_repo.assign(
            user_id=user_id,
            task_id=task.id,
            enrollment_id=enrollment.id,
        )

        # 6. Update rotation memory so next time we pick a different activity
        self.history_repo.upsert_after_assignment(
            enrollment_id=enrollment.id,
            skill_id=plan.skill_id,
            activity_type=plan.activity_type,
        )

        # 7. Commit and return
        self.db.commit()
        self.db.refresh(assignment)
        # Eager-load task before returning so route can serialize it
        # without a fresh query
        self.db.refresh(assignment.task)
        return assignment