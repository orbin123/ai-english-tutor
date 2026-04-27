"""Diagnosis HTTP routes — translates between HTTP and DiagnosisService."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.diagnosis.exceptions import (
    DiagnosisAlreadyCompleted,
    DiagnosisInvalidPayload,
)
from app.modules.diagnosis.schemas import (
    DiagnosisSubmitRequest,
    DiagnosisSubmitResponse,
)
from app.modules.diagnosis.service import DiagnosisService

router = APIRouter()


@router.post(
    "/submit",
    response_model=DiagnosisSubmitResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_diagnosis(
    payload: DiagnosisSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DiagnosisSubmitResponse:
    """Submit diagnosis answers and create the user's 7 skill scores.

    Auth: Bearer token required.
    """
    try:
        skill_scores = DiagnosisService(db).run_diagnosis(
            user_id=current_user.id,
            payload=payload,
        )
    except DiagnosisAlreadyCompleted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Diagnosis already completed for this user.",
        )
    except DiagnosisInvalidPayload as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    # Pick the 2 weakest skills for the response
    weakest = sorted(skill_scores.items(), key=lambda kv: kv[1])[:2]

    return DiagnosisSubmitResponse(
        skill_scores=skill_scores,
        weakest_skills=[name for name, _ in weakest],
    )