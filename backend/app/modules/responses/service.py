"""Business logic for accepting + grading a user's response to a task."""

from sqlalchemy.orm import Session

from app.ai.agents import EvaluationService
from app.modules.progress.service import ScoreUpdaterService
from app.modules.responses.exceptions import (
    NotResponseOwner,
    ResponseAlreadySubmitted,
    UserTaskNotFound,
    UserTaskNotSubmittable,
)
from app.modules.responses.feedback_service import FeedbackService
from app.modules.responses.models import Evaluation, Feedback, UserResponse
from app.modules.responses.repository import (
    EvaluationRepository,
    ResponseRepository,
)
from app.modules.skills.models import UserSkillScore
from app.modules.tasks.models import UserTaskStatus
from app.modules.tasks.repository import UserTaskRepository


# Statuses that allow a response to be submitted
_SUBMITTABLE_STATUSES = {UserTaskStatus.PENDING, UserTaskStatus.IN_PROGRESS}


class ResponseService:
    """Orchestrates the full submit → evaluate → feedback → score loop."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.user_task_repo = UserTaskRepository(db)
        self.response_repo = ResponseRepository(db)
        self.evaluation_repo = EvaluationRepository(db)
        # Sub-services — each owns its own commit boundary
        self.evaluator = EvaluationService()
        self.feedback_service = FeedbackService(db)
        self.score_updater = ScoreUpdaterService(db)

    # ---- Step 1: persist response only (private, reused by submit_and_grade) ----
    def _persist_response(
        self,
        *,
        user_id: int,
        user_task_id: int,
        content: dict,
        raw_text: str | None,
    ) -> UserResponse:
        """Validate ownership/state and save the UserResponse row.

        Same guards as before: 404 / 403 / 409. One commit.
        """
        # 1. Load the assignment
        user_task = self.user_task_repo.get_by_id(user_task_id)
        if user_task is None:
            raise UserTaskNotFound(f"UserTask {user_task_id} does not exist")

        # 2. Ownership check
        if user_task.user_id != user_id:
            raise NotResponseOwner(
                f"User {user_id} cannot submit a response for UserTask "
                f"{user_task_id} (owner: {user_task.user_id})"
            )

        # 3. State check
        if user_task.status not in _SUBMITTABLE_STATUSES:
            raise UserTaskNotSubmittable(
                f"UserTask {user_task_id} is {user_task.status.value} — "
                f"cannot submit"
            )

        # 4. Duplicate-submission check
        existing = self.response_repo.get_by_user_task_id(user_task_id)
        if existing is not None:
            raise ResponseAlreadySubmitted(
                f"UserTask {user_task_id} already has response {existing.id}"
            )

        # 5. Create the response row
        response = self.response_repo.create(
            user_task_id=user_task_id,
            content=content,
            raw_text=raw_text,
        )

        # 6. Move the assignment forward
        if user_task.status == UserTaskStatus.PENDING:
            user_task.status = UserTaskStatus.IN_PROGRESS

        # 7. Commit response + status flip atomically
        self.db.commit()
        self.db.refresh(response)
        return response

    # ---- Step 2: run the rule-based evaluator and save it ----
    def _evaluate_and_persist(
        self, *, response: UserResponse
    ) -> Evaluation:
        """Run the rule-based evaluator and save the Evaluation row.

        Idempotent: if an evaluation already exists for this response,
        return it instead of re-evaluating.

        Picks the right evaluator based on the FIRST activity inside
        Task.content.activities. MVP shortcut: a task today has exactly
        one scorable activity. When tasks bundle multiple activities,
        we'll loop here and aggregate.
        """
        # Idempotency guard — protects against retries/duplicate calls
        existing = self.evaluation_repo.get_by_response_id(response.id)
        if existing is not None:
            return existing

        # Walk back to the Task to get the answer key + activity type
        user_task = self.user_task_repo.get_by_id(response.user_task_id)
        task = user_task.task

        activity_type = self._first_activity_type(task.content)

        report = self.evaluator.evaluate(
            activity_type=activity_type,
            task_content=task.content,
            user_answers=response.content,
        )

        # overall_score = percentage / 10 → 0–10 scale (matches Numeric(4,2))
        percentage = float(report["percentage"])
        overall_score = round(percentage / 10.0, 2)

        evaluation = self.evaluation_repo.create(
            response_id=response.id,
            overall_score=overall_score,
            percentage=percentage,
            report=report,
        )
        self.db.commit()
        self.db.refresh(evaluation)
        return evaluation

    @staticmethod
    def _first_activity_type(task_content: dict) -> str:
        """Return the activity_type of the first activity in the task.

        Raises ValueError if the task has no activities at all — that's
        a malformed seed and should fail loud, not silently default.
        """
        activities = task_content.get("activities") or []
        if not activities:
            raise ValueError(
                "Task content has no activities — cannot evaluate"
            )
        return activities[0]["activity_type"]

    # ---- The whole loop ----
    async def submit_and_grade(
        self,
        *,
        user_id: int,
        user_task_id: int,
        content: dict,
        raw_text: str | None = None,
    ) -> tuple[UserResponse, Evaluation, Feedback, list[UserSkillScore]]:
        """Submit a response and run the entire grading loop.

        Returns a 4-tuple: (response, evaluation, feedback, updated_scores).
        Routes layer turns this into the public schema.

        Failure modes:
          - 404/403/409 from _persist_response (handled in route)
          - LLM failure from FeedbackService → bubbles up as
            FeedbackGenerationFailed (route maps to 502)
        """
        # 1. Save response (commit 1)
        response = self._persist_response(
            user_id=user_id,
            user_task_id=user_task_id,
            content=content,
            raw_text=raw_text,
        )

        # 2. Evaluate + save (commit 2)
        evaluation = self._evaluate_and_persist(response=response)

        # 3. Generate feedback via LLM + save (commit 3, may fail loudly)
        feedback = await self.feedback_service.generate_for_evaluation(
            evaluation.id
        )

        # 4. Update skill scores + log progress (commit 4)
        updated_scores = self.score_updater.apply(evaluation.id)

        return response, evaluation, feedback, updated_scores
