"""Business logic for assigning the next task to a user.

Orchestrates: enrollment → rotation engine → task pool → assignment +
history update.  When an LLM-generated template is available the service
tries TaskGeneratorAgent first, falling back to the seeded pool on failure.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.orm import Session

from app.ai.task_generator import TaskGeneratorAgent
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
from app.modules.skills.repository import SkillRepository, UserSkillScoreRepository
from app.modules.tasks.models import Task, TaskStatus, UserTask
from app.modules.tasks.repository import TaskRepository, UserTaskRepository
from app.tasks.schemas import get_templates_for
from app.tasks.schemas.base import Activity

logger = logging.getLogger(__name__)

# Map DB TaskType → schema Activity so we can look up templates
_TASK_TYPE_TO_ACTIVITY = {
    "reading": Activity.READ,
    "writing": Activity.WRITE,
    "listening": Activity.LISTEN,
    "speaking": Activity.SPEAK,
}


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
        self.score_repo = UserSkillScoreRepository(db)
        self.task_repo = TaskRepository(db)
        self.user_task_repo = UserTaskRepository(db)
        self.engine = RotationEngine()
        self.generator = TaskGeneratorAgent()

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

    def _build_user_profile(self, user_id: int) -> dict:
        """Assemble the user_profile dict the TaskGeneratorAgent needs.

        Includes sub_level (derived from weakest skill score) and a
        comma-separated list of weak_areas.
        """
        scores = self.score_repo.get_for_user(user_id)
        if not scores:
            # No diagnosis yet — return safe defaults
            return {
                "sub_level": 3,
                "weak_areas": "general grammar, basic vocabulary",
                "topic": "workplace",
            }

        # Sort ascending so weakest come first
        sorted_scores = sorted(scores, key=lambda s: float(s.score))
        weakest = sorted_scores[:3]  # bottom 3 skills
        avg_score = sum(float(s.score) for s in scores) / len(scores)

        # Map 0–10 score → 1–10 sub-level
        sub_level = max(1, min(10, round(avg_score)))

        weak_area_names = []
        for s in weakest:
            if s.skill and s.skill.name:
                weak_area_names.append(s.skill.name)
        weak_areas = ", ".join(weak_area_names) if weak_area_names else "general grammar"

        return {
            "sub_level": sub_level,
            "weak_areas": weak_areas,
            "topic": "workplace",  # hardcoded for MVP
        }

    def _try_generate_task(
        self,
        *,
        user_id: int,
        plan: "RotationEngine.Plan",  # noqa: F821
        enrollment: UserEnrollment,
        user_profile: dict,
        skill_name_to_id: dict[str, int],
    ) -> UserTask | None:
        """Attempt to generate a task via the LLM.

        Returns a UserTask if generation succeeds, None on any failure
        (so the caller can fall back to the seeded pool).
        """
        from app.tasks.schemas.base import SubSkill

        # Map the plan's skill name to a SubSkill enum
        # The schema SubSkill uses the DB skill name directly for grammar/vocabulary/tone;
        # for others we need a mapping.
        _SKILL_NAME_TO_SUBSKILL = {
            "grammar": SubSkill.GRAMMAR,
            "vocabulary": SubSkill.VOCABULARY,
            "pronunciation": SubSkill.PRONUNCIATION,
            "fluency": SubSkill.FLUENCY,
            "expression": SubSkill.THOUGHT_ORGANIZATION,
            "comprehension": SubSkill.LISTENING,
            "tone": SubSkill.TONE,
        }

        sub_skill = _SKILL_NAME_TO_SUBSKILL.get(plan.skill_name)
        if sub_skill is None:
            logger.warning("No SubSkill mapping for %r, skipping LLM gen", plan.skill_name)
            return None

        # Map plan.activity_type (TaskType) → schema Activity
        schema_activity = _TASK_TYPE_TO_ACTIVITY.get(plan.activity_type.value)
        if schema_activity is None:
            logger.warning("No Activity mapping for %r, skipping LLM gen", plan.activity_type)
            return None

        # Find matching templates
        templates = get_templates_for(sub_skill, schema_activity)
        if not templates:
            logger.info(
                "No templates for sub_skill=%s activity=%s, skipping LLM gen",
                sub_skill.value, schema_activity.value,
            )
            return None

        # Pick the first template that supports the user's sub_level
        sub_level = user_profile.get("sub_level", 5)
        template = None
        for tpl in templates:
            lo, hi = tpl.difficulty_range
            if lo <= sub_level <= hi:
                template = tpl
                break
        if template is None:
            template = templates[0]  # fallback to first template

        try:
            # Run the async generator in a sync context
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're inside an async framework (FastAPI) — use a new thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    content = pool.submit(
                        asyncio.run,
                        self.generator.generate(template, user_profile),
                    ).result(timeout=30)
            else:
                content = asyncio.run(
                    self.generator.generate(template, user_profile)
                )
        except Exception as exc:
            logger.warning(
                "LLM generation failed for template=%s: %s",
                template.template_id, exc,
            )
            return None

        # Create a new Task row with the generated content
        task = Task(
            title=f"{plan.skill_name.title()} – {template.task_type} (generated)",
            task_type=plan.activity_type,
            difficulty=sub_level,
            status=TaskStatus.ACTIVE,
            content=content,
        )
        self.db.add(task)
        self.db.flush()  # get task.id

        # Wire up the TaskSkill junction
        from app.modules.tasks.models import TaskSkill
        ts = TaskSkill(
            task_id=task.id,
            skill_id=plan.skill_id,
            weight=1.0,
        )
        self.db.add(ts)
        self.db.flush()

        # Assign to user
        assignment = self.user_task_repo.assign(
            user_id=user_id,
            task_id=task.id,
            enrollment_id=enrollment.id,
        )

        logger.info(
            "LLM-generated task created: task_id=%s template=%s for user=%s",
            task.id, template.template_id, user_id,
        )
        return assignment

    def _create_one_task(
        self,
        *,
        user_id: int,
        enrollment: UserEnrollment,
        skill_name_to_id: dict[str, int],
        history_by_skill_id: dict[int, str | None],
    ) -> UserTask:
        """Run the rotation engine once, try LLM generation first, then
        fall back to the seeded task pool. Does NOT commit."""
        plan = self.engine.decide(
            week_number=enrollment.current_week,
            day_in_week=enrollment.current_day_in_week,
            skill_name_to_id=skill_name_to_id,
            history_by_skill_id=history_by_skill_id,
        )

        # --- Try LLM generation first ---
        user_profile = self._build_user_profile(user_id)
        assignment = self._try_generate_task(
            user_id=user_id,
            plan=plan,
            enrollment=enrollment,
            user_profile=user_profile,
            skill_name_to_id=skill_name_to_id,
        )
        if assignment is not None:
            # Update rotation memory
            self.history_repo.upsert_after_assignment(
                enrollment_id=enrollment.id,
                skill_id=plan.skill_id,
                activity_type=plan.activity_type,
            )
            return assignment

        # --- Fallback: seeded task pool ---
        logger.info(
            "Falling back to seeded pool for skill=%s activity=%s",
            plan.skill_name, plan.activity_type.value,
        )
        task = self.task_repo.find_for_plan(
            skill_id=plan.skill_id,
            activity_type=plan.activity_type,
            target_difficulty=plan.target_difficulty,
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

    def superuser_jump(
        self,
        *,
        user_id: int,
        week: int,
        day_in_week: int,
    ) -> list[UserTask]:
        """Create a fresh task bundle for an arbitrary (week, day).

        Used only by the superuser dev panel for UI testing.
        Bypasses the enrollment's current_week/current_day_in_week.
        Always creates new tasks — does NOT reuse existing ones.
        Does NOT advance or modify the user's enrollment state.
        Does NOT update rotation history.
        Commits and returns the created UserTask objects.
        """
        enrollment = self._load_enrollment(user_id)

        skill_name_to_id = self.skill_repo.name_to_id_map()

        # Start from the first allowed activity every time so the jump
        # is deterministic for UI testing regardless of prior usage.
        history_by_skill_id: dict[int, None] = {}

        user_profile = self._build_user_profile(user_id)

        plan = self.engine.decide(
            week_number=week,
            day_in_week=day_in_week,
            skill_name_to_id=skill_name_to_id,
            history_by_skill_id=history_by_skill_id,
        )

        assignment = self._try_generate_task(
            user_id=user_id,
            plan=plan,
            enrollment=enrollment,
            user_profile=user_profile,
            skill_name_to_id=skill_name_to_id,
        )

        if assignment is None:
            task = self.task_repo.find_for_plan(
                skill_id=plan.skill_id,
                activity_type=plan.activity_type,
                target_difficulty=plan.target_difficulty,
                exclude_completed_by_user_id=None,
            )
            if task is None:
                raise NoTaskAvailable(
                    f"No task in pool for skill={plan.skill_name}, "
                    f"activity={plan.activity_type.value}"
                )
            assignment = self.user_task_repo.assign(
                user_id=user_id,
                task_id=task.id,
                enrollment_id=enrollment.id,
            )

        self.db.commit()
        self.db.refresh(assignment)
        self.db.refresh(assignment.task)
        return [assignment]

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
