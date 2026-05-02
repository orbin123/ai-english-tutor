"""Diagnosis HTTP routes."""

import io
import time

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.diagnosis.exceptions import (
    DiagnosisAlreadyCompleted,
    DiagnosisInvalidPayload,
)
from app.modules.diagnosis.schemas import (
    DiagnosisFeedbackOut,
    DiagnosisSubmitRequest,
    DiagnosisSubmitResponse,
    TranscribeResponse,
    WeakSkillExplanationOut,
)
from app.modules.diagnosis.service import DiagnosisService

router = APIRouter()

# One shared async OpenAI client for Whisper calls
_openai = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

# Allowed audio MIME types Whisper accepts
ALLOWED_AUDIO_TYPES = {
    "audio/webm",
    "audio/webm;codecs=opus",
    "audio/mp4",
    "audio/mpeg",
    "audio/wav",
    "audio/ogg",
}

# Max file size: 25 MB (Whisper API limit)
MAX_AUDIO_BYTES = 25 * 1024 * 1024


@router.post(
    "/transcribe",
    response_model=TranscribeResponse,
    status_code=status.HTTP_200_OK,
)
async def transcribe_audio(
    audio: UploadFile = File(..., description="Audio recording from the read-aloud step"),
    current_user: User = Depends(get_current_user),
) -> TranscribeResponse:
    """Transcribe a read-aloud audio recording using OpenAI Whisper.

    Accepts: webm, mp4, mpeg, wav, ogg (browser MediaRecorder output).
    Returns: transcript text + duration in seconds.

    Auth: Bearer token required.
    """
    # Validate MIME type
    content_type = (audio.content_type or "").lower()
    if content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported audio type: {content_type!r}. "
                "Please record in webm, mp4, wav, or ogg format."
            ),
        )

    # Read file into memory and check size
    audio_bytes = await audio.read()
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Audio file is too large. Maximum size is 25 MB.",
        )
    if len(audio_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio file is empty.",
        )

    # Wrap bytes in a file-like object with a filename so Whisper can detect format
    extension = _mime_to_extension(content_type)
    audio_file = (f"recording.{extension}", io.BytesIO(audio_bytes), content_type)

    # Time the call so we can derive duration from wall-clock if needed
    t_start = time.monotonic()

    try:
        transcription = await _openai.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="en",          # force English — avoids mis-detection
            response_format="json",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Whisper transcription failed: {exc}",
        )

    t_elapsed = time.monotonic() - t_start

    # Whisper JSON response doesn't include duration — estimate from byte size.
    # A typical webm/opus recording runs ~12–16 kbps, so:
    #   duration ≈ bytes / (14_000 / 8)  = bytes / 1750
    # This is a rough estimate; good enough for scoring fluency.
    estimated_duration = max(len(audio_bytes) / 1750, t_elapsed)

    return TranscribeResponse(
        transcript=transcription.text.strip(),
        duration_seconds=round(estimated_duration, 2),
    )


@router.post(
    "/submit",
    response_model=DiagnosisSubmitResponse,
    status_code=status.HTTP_201_CREATED,
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
        skill_scores, ai_feedback = await DiagnosisService(db).run_diagnosis(
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

    weakest = sorted(skill_scores.items(), key=lambda kv: kv[1])[:2]
    weakest_skill_names = [name for name, _ in weakest]

    feedback_out = DiagnosisFeedbackOut(
        estimated_level_label=ai_feedback.estimated_level_label,
        summary=ai_feedback.summary,
        weak_skill_explanations=[
            WeakSkillExplanationOut(
                skill_name=e.skill_name,
                what_it_means=e.what_it_means,
                why_it_matters=e.why_it_matters,
                what_to_expect=e.what_to_expect,
            )
            for e in ai_feedback.weak_skill_explanations
        ],
        motivation=ai_feedback.motivation,
        first_week_focus=ai_feedback.first_week_focus,
    )

    return DiagnosisSubmitResponse(
        skill_scores=skill_scores,
        weakest_skills=weakest_skill_names,
        feedback=feedback_out,
    )


# ── Helpers ────────────────────────────────────────────────────────────────

def _mime_to_extension(mime: str) -> str:
    """Map a MIME type to a file extension Whisper recognises."""
    mapping = {
        "audio/webm": "webm",
        "audio/webm;codecs=opus": "webm",
        "audio/mp4": "mp4",
        "audio/mpeg": "mp3",
        "audio/wav": "wav",
        "audio/ogg": "ogg",
    }
    return mapping.get(mime, "webm")
