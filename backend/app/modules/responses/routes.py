"""HTTP endpoints for response submission."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.progress.exceptions import TaskHasNoTargetSkills
from app.modules.responses.exceptions import (
    FeedbackAlreadyExists,
    FeedbackGenerationFailed,
    NotResponseOwner,
    ResponseAlreadySubmitted,
    UserTaskNotFound,
    UserTaskNotSubmittable,
)
from app.modules.responses.schemas import (
    EvaluationRead,
    FeedbackRead,
    ResponseGradedRead,
    ResponseRead,
    ResponseSubmit,
    SkillScoreRead,
)
from app.modules.responses.service import ResponseService

router = APIRouter(prefix="/responses", tags=["responses"])


@router.post(
    "/submit",
    response_model=ResponseGradedRead,
    status_code=status.HTTP_201_CREATED,
)
async def submit_response(
    payload: ResponseSubmit,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResponseGradedRead:
    """Submit a response and run the full grading loop.

    Pipeline (per request):
      1. Persist UserResponse, flip UserTask → IN_PROGRESS
      2. Run rule-based evaluator → save Evaluation
      3. Call Feedback Agent (LLM) → save Feedback
      4. Update UserSkillScore (WMA) + insert ProgressLog rows

    Returns the full bundle in one round trip:
      response, evaluation, feedback, skill_scores

    Errors:
      403 — UserTask belongs to a different user
      404 — UserTask does not exist
      409 — UserTask already completed/skipped, response already submitted,
            or feedback already generated (retry)
      422 — Task has no target skills (data integrity bug)
      502 — LLM call failed; response & evaluation are saved, retry later
    """
    service = ResponseService(db)
    try:
        response, evaluation, feedback, updated_scores = (
            await service.submit_and_grade(
                user_id=current_user.id,
                user_task_id=payload.user_task_id,
                content=payload.content,
                raw_text=payload.raw_text,
            )
        )
    except UserTaskNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except NotResponseOwner as e:
        raise HTTPException(status_code=403, detail=str(e))
    except (
        UserTaskNotSubmittable,
        ResponseAlreadySubmitted,
        FeedbackAlreadyExists,
    ) as e:
        raise HTTPException(status_code=409, detail=str(e))
    except TaskHasNoTargetSkills as e:
        raise HTTPException(status_code=422, detail=str(e))
    except FeedbackGenerationFailed as e:
        raise HTTPException(status_code=502, detail=str(e))

    # Build skill_scores with the skill name (frontend-friendly).
    # The score_updater already loaded skill rows via the upsert; the
    # `.skill` relationship is on UserSkillScore, so this is one extra
    # SELECT per row at worst — fine for 1–3 skills per task.
    skill_scores = [
        SkillScoreRead(
            skill_id=row.skill_id,
            skill_name=row.skill.name,
            score=float(row.score),
        )
        for row in updated_scores
    ]

    return ResponseGradedRead(
        response=ResponseRead.model_validate(response),
        evaluation=EvaluationRead.model_validate(evaluation),
        feedback=FeedbackRead.model_validate(feedback),
        skill_scores=skill_scores,
    )