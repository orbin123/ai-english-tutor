"""HTTP endpoints for response submission."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.responses.exceptions import (
    NotResponseOwner,
    ResponseAlreadySubmitted,
    UserTaskNotFound,
    UserTaskNotSubmittable,
)
from app.modules.responses.schemas import ResponseRead, ResponseSubmit
from app.modules.responses.service import ResponseService

router = APIRouter(prefix="/responses", tags=["responses"])


@router.post(
    "/submit",
    response_model=ResponseRead,
    status_code=status.HTTP_201_CREATED,
)
def submit_response(
    payload: ResponseSubmit,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResponseRead:
    """Persist the user's answers for an assigned task.

    No evaluation happens here — that's a later stage. After this call:
      - A row exists in `user_responses`.
      - The matching UserTask.status is IN_PROGRESS.

    Errors:
      403 — UserTask belongs to a different user
      404 — UserTask does not exist
      409 — UserTask already completed/skipped, or response already submitted
    """
    service = ResponseService(db)
    try:
        response = service.submit(
            user_id=current_user.id,
            user_task_id=payload.user_task_id,
            content=payload.content,
            raw_text=payload.raw_text,
        )
    except UserTaskNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except NotResponseOwner as e:
        raise HTTPException(status_code=403, detail=str(e))
    except (UserTaskNotSubmittable, ResponseAlreadySubmitted) as e:
        raise HTTPException(status_code=409, detail=str(e))

    return ResponseRead.model_validate(response)
