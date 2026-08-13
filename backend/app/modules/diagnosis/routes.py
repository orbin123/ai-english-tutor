"""Diagnosis HTTP routes."""

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.ai.pronunciation import (
    PronunciationError,
    PronunciationResult,
    PronunciationValidationError,
    get_default_pronunciation_service,
)
from app.core.ai_rate_limit import ai_rate_limit
from app.core.audio_uploads import enforce_wav_duration, read_audio_upload
from app.core.database import get_db
from app.modules.auth.dependencies import (
    get_current_user,
    require_learner,
    require_verified,
)
from app.modules.auth.models import User
from app.modules.diagnosis.diagnosis_agents.evaluators import PASSAGES
from app.modules.diagnosis.exceptions import (
    DiagnosisAlreadyCompleted,
    DiagnosisInvalidPayload,
)
from app.modules.diagnosis.schemas import (
    DiagnosisFeedbackOut,
    DiagnosisSubmitRequest,
    DiagnosisSubmitResponse,
    FocusCalloutOut,
    SkillCalloutOut,
)
from app.modules.diagnosis.service import DiagnosisService

# Diagnosis sits between email verification and the trial in the lifecycle:
# allowed for VERIFIED users, blocked for UNVERIFIED — hence require_verified
# here rather than the (post-trial) premium guard.
router = APIRouter(dependencies=[Depends(require_learner), Depends(require_verified)])

logger = logging.getLogger(__name__)


@router.post(
    "/pronunciation-score",
    response_model=PronunciationResult,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(ai_rate_limit("diagnosis"))],
)
async def score_read_aloud(
    audio: UploadFile = File(
        ..., description="WAV recording of the read-aloud passage"
    ),
    passage_id: str = Form(
        ..., description="Canonical passage id, e.g. diag_passage_v1"
    ),
    language: str = Form(default="en-US"),
    current_user: User = Depends(get_current_user),
) -> PronunciationResult:
    """Score a read-aloud recording with Azure Speech Pronunciation Assessment.

    The frontend records the passage, converts the audio to WAV client-side
    (Azure does not accept WebM), and posts it here. The canonical reference
    text is resolved from ``passage_id`` server-side so the client can't tamper
    with what's being graded. The returned result is included in the main
    ``/submit`` payload.

    Auth: Bearer token required.
    """
    reference_text = PASSAGES.get(passage_id)
    if reference_text is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown passage_id: {passage_id!r}",
        )

    audio_bytes = await read_audio_upload(audio)
    filename = audio.filename or "recording.wav"
    enforce_wav_duration(
        audio_bytes,
        filename=filename,
        content_type=audio.content_type,
    )

    service = get_default_pronunciation_service()
    try:
        result = await service.score(
            audio_bytes=audio_bytes,
            filename=filename,
            reference_text=reference_text,
            language=language,
        )
    except PronunciationValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except PronunciationError as exc:
        # Log the concrete Azure failure (type + message) so a 502 here is
        # diagnosable from CloudWatch — distinguishes a config/cred problem
        # (auth/region) from a runtime/connectivity one (missing native deps,
        # blocked egress). The route otherwise only emits the http_request 502.
        logger.warning(
            "pronunciation_score_failed passage_id=%s user_id=%s err_type=%s err=%s",
            passage_id,
            current_user.id,
            type(exc).__name__,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return result


@router.post(
    "/submit",
    response_model=DiagnosisSubmitResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(ai_rate_limit("diagnosis"))],
)
async def submit_diagnosis(
    payload: DiagnosisSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DiagnosisSubmitResponse:
    """Submit diagnosis answers, compute skill scores, and return AI feedback.

    Auth: Bearer token required.
    """
    try:
        skill_scores, ai_feedback, read_aloud_analysis = await DiagnosisService(
            db
        ).run_diagnosis(
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

    feedback_out = DiagnosisFeedbackOut(
        estimated_level_label=ai_feedback.estimated_level_label,
        level_description=ai_feedback.level_description,
        summary=ai_feedback.summary,
        biggest_weakness=SkillCalloutOut(
            skill_name=ai_feedback.biggest_weakness.skill_name,
            description=ai_feedback.biggest_weakness.description,
        ),
        strongest_skill=SkillCalloutOut(
            skill_name=ai_feedback.strongest_skill.skill_name,
            description=ai_feedback.strongest_skill.description,
        ),
        first_focus=FocusCalloutOut(
            title=ai_feedback.first_focus.title,
            description=ai_feedback.first_focus.description,
        ),
    )

    return DiagnosisSubmitResponse(
        skill_scores=skill_scores,
        goal=payload.self_assessment.goal,
        feedback=feedback_out,
        read_aloud_analysis=read_aloud_analysis,
    )
