"""HTTP endpoints for tasks."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.curriculum.exceptions import (
    EnrollmentNotActive,
    NoTaskAvailable,
    NotEnrolled,
)
from app.modules.tasks.schemas import UserTaskRead
from app.modules.tasks.service import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post(
    "/next",
    response_model=UserTaskRead,
    status_code=status.HTTP_200_OK,  
)
def get_next_task(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserTaskRead:
    """Return the authenticated user's current task.

    Idempotent — calling repeatedly on the same day returns the same task.
    Errors:
      404 — user not enrolled
      409 — enrollment paused/abandoned
      503 — rotation engine ran but task pool is empty for this slot
    """
    service = TaskService(db)
    try:
        user_task = service.pick_next(user_id=current_user.id)
    except NotEnrolled as e:
        raise HTTPException(status_code=404, detail=str(e))
    except EnrollmentNotActive as e:
        raise HTTPException(status_code=409, detail=str(e))
    except NoTaskAvailable as e:
        raise HTTPException(status_code=503, detail=str(e))

    return UserTaskRead.model_validate(user_task)