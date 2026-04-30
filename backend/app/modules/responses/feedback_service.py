"""FeedbackService — orchestrates Agent 3 to produce + persist feedback.

Flow (given an evaluation_id):
  1. Load Evaluation (404 if missing).
  2. Walk back: Evaluation → UserResponse → UserTask → Task.
  3. Reshape that data into the inputs Agent 3 expects.
  4. Call generate_feedback() (the LLM agent from app/ai/feedback.py).
  5. Persist the validated FeedbackOutput into a new Feedback row.
  6. Commit, return the Feedback ORM object.

This service does NOT regenerate evaluations — it strictly transforms
an existing Evaluation into a Feedback. That keeps responsibilities
single (SRP) and makes feedback regeneration cheap later (just call
this again with the same evaluation_id).
"""

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.ai.feedback import generate_feedback
from app.modules.responses.exceptions import (
    EvaluationNotFound,
    FeedbackAlreadyExists,
    FeedbackGenerationFailed,
)
from app.modules.responses.models import Feedback
from app.modules.responses.repository import (
    EvaluationRepository,
    FeedbackRepository,
)


class FeedbackService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.evaluation_repo = EvaluationRepository(db)
        self.feedback_repo = FeedbackRepository(db)

    async def generate_for_evaluation(self, evaluation_id: int) -> Feedback:
        # 1. Load the evaluation
        evaluation = self.evaluation_repo.get_by_id(evaluation_id)
        if evaluation is None:
            raise EvaluationNotFound(
                f"Evaluation {evaluation_id} does not exist"
            )

        # 2. Idempotency — don't double-generate
        existing = self.feedback_repo.get_by_evaluation_id(evaluation_id)
        if existing is not None:
            raise FeedbackAlreadyExists(
                f"Evaluation {evaluation_id} already has feedback {existing.id}"
            )

        # 3. Walk back through the chain to gather LLM inputs.
        # Relationships are eager enough on access; SQLAlchemy will
        # lazy-load each step. Fine for one row.
        from app.modules.tasks.models import UserTask  # local: avoid import cycle

        response = evaluation.response
        user_task = self.db.get(UserTask, response.user_task_id)
        task = user_task.task

        # 4. Reshape — Agent 3 expects specific keys.
        score_int = int(round(float(evaluation.percentage)))

        # 5. Call the LLM. Wrap in try/except so we surface a clean
        # business error instead of leaking pydantic/openai internals.
        try:
            feedback_output = await generate_feedback(
                task_content=task.content,
                user_answers=response.content,
                evaluation_report=evaluation.report,
                score=score_int,
            )
        except ValidationError as e:
            raise FeedbackGenerationFailed(
                f"LLM returned invalid feedback JSON: {e}"
            ) from e
        except Exception as e:
            # Network errors, OpenAI 5xx, timeouts, etc.
            raise FeedbackGenerationFailed(
                f"Feedback generation failed: {e}"
            ) from e

        # 6. Persist. body is the full structured payload — JSONB column
        # already accepts dict, so we just dump the pydantic model.
        feedback = self.feedback_repo.create(
            evaluation_id=evaluation_id,
            body=feedback_output.model_dump(),
        )

        # 7. One commit — the only DB write in this flow.
        self.db.commit()
        self.db.refresh(feedback)
        return feedback
    
