"""HTTP endpoints for the progress module."""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.progress.repository import ProgressLogRepository
from app.modules.progress.schemas import ProgressLogPoint, SkillScoreSnapshot
from app.modules.skills.repository import UserSkillScoreRepository

router = APIRouter(prefix="/progress", tags=["progress"])


@router.get(
    "/scores",
    response_model=list[SkillScoreSnapshot],
    status_code=status.HTTP_200_OK,
)
def get_current_scores(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SkillScoreSnapshot]:
    """Return the user's current score on every tracked skill.

    Used by the dashboard spider chart. Returns an empty list if the
    user has not completed diagnosis yet (no rows seeded).
    """
    rows = UserSkillScoreRepository(db).get_for_user(current_user.id)
    return [
        SkillScoreSnapshot(
            skill_id=row.skill_id,
            skill_name=row.skill.name,
            score=float(row.score),
        )
        for row in rows
    ]


@router.get(
    "/history",
    response_model=list[ProgressLogPoint],
    status_code=status.HTTP_200_OK,
)
def get_skill_history(
    skill_id: int = Query(..., gt=0, description="Skill to fetch history for"),
    days: int = Query(
        30, ge=1, le=365, description="Window size in days (max 365)"
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ProgressLogPoint]:
    """Return score history for ONE skill over the last `days` days.

    Used by the dashboard line chart. Points are ordered oldest → newest.
    Empty list if there are no logs in the window.
    """
    rows = ProgressLogRepository(db).list_for_user_skill(
        user_id=current_user.id,
        skill_id=skill_id,
        days=days,
    )
    return [ProgressLogPoint.model_validate(row) for row in rows]