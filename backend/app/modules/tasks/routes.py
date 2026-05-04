"""HTTP endpoints for tasks."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user, require_superuser
from app.modules.auth.models import User
from app.modules.curriculum.exceptions import (
    EnrollmentNotActive,
    NoTaskAvailable,
    NotEnrolled,
)
from app.modules.curriculum.schemas import EnrollmentRead
from app.modules.tasks.schemas import UserTaskRead
from app.modules.tasks.service import DayNotComplete, TaskService


class SuperuserJumpRequest(BaseModel):
    week: int = Field(..., ge=1, le=48)
    day_in_week: int = Field(..., ge=1, le=7)


router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post(
    "/next",
    response_model=list[UserTaskRead],
    status_code=status.HTTP_200_OK,
)
def get_next_tasks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[UserTaskRead]:
    """Return the authenticated user's current day bundle (2–3 tasks).

    Idempotent — calling repeatedly on the same day returns the same bundle.
    New tasks are created only if the bundle is not yet full.

    Errors:
      404 — user not enrolled
      409 — enrollment paused/abandoned
      503 — rotation engine ran but task pool is empty for this slot
    """
    service = TaskService(db)
    try:
        bundle = service.get_or_create_day_bundle(user_id=current_user.id)
    except NotEnrolled as e:
        raise HTTPException(status_code=404, detail=str(e))
    except EnrollmentNotActive as e:
        raise HTTPException(status_code=409, detail=str(e))
    except NoTaskAvailable as e:
        raise HTTPException(status_code=503, detail=str(e))

    return [UserTaskRead.model_validate(ut) for ut in bundle]


@router.post(
    "/superuser-jump",
    response_model=list[UserTaskRead],
    status_code=status.HTTP_200_OK,
)
def superuser_jump(
    payload: SuperuserJumpRequest,
    current_user: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> list[UserTaskRead]:
    """Dev-only: jump to a specific (week, day) and get a fresh task.
    Only accessible to superusers. Does not modify enrollment state."""
    service = TaskService(db)
    try:
        bundle = service.superuser_jump(
            user_id=current_user.id,
            week=payload.week,
            day_in_week=payload.day_in_week,
        )
    except NotEnrolled as e:
        raise HTTPException(status_code=404, detail=str(e))
    except EnrollmentNotActive as e:
        raise HTTPException(status_code=409, detail=str(e))
    except NoTaskAvailable as e:
        raise HTTPException(status_code=503, detail=str(e))

    return [UserTaskRead.model_validate(ut) for ut in bundle]


@router.post(
    "/complete-day",
    response_model=EnrollmentRead,
    status_code=status.HTTP_200_OK,
)
def complete_day(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EnrollmentRead:
    """Mark the current day as complete and advance to the next day.

    Checks that ALL tasks in the day bundle are COMPLETED.
    Returns the updated enrollment state (current_week, current_day_in_week).

    Errors:
      404 — user not enrolled
      409 — enrollment paused/abandoned, or tasks still incomplete
    """
    service = TaskService(db)
    try:
        enrollment = service.mark_day_complete(user_id=current_user.id)
    except NotEnrolled as e:
        raise HTTPException(status_code=404, detail=str(e))
    except EnrollmentNotActive as e:
        raise HTTPException(status_code=409, detail=str(e))
    except DayNotComplete as e:
        raise HTTPException(status_code=409, detail=str(e))

    return EnrollmentRead.model_validate(enrollment)
