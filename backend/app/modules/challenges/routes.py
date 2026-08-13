"""HTTP endpoints for challenge catalog and learner progress reads."""

from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.audio_uploads import read_audio_upload
from app.modules.auth.dependencies import require_learner
from app.modules.auth.models import User
from app.modules.challenges.ielts_sprint.schemas import (
    ChallengeAttemptRead,
    ChallengeAttemptResponsesPatchRequest,
    ChallengeAttemptSubmitRequest,
    ChallengeDetailRead,
    ChallengeHistoryRead,
    ChallengeListItem,
    ChallengeSpeakingUploadRead,
)
from app.modules.challenges.ielts_sprint.service import (
    ChallengeAttemptInProgress,
    ChallengeAttemptNotFound,
    ChallengeAudioNotFound,
    ChallengeDailyAttemptLimitExceeded,
    ChallengeLevelLocked,
    ChallengeLevelNotFound,
    ChallengeNotFound,
    ChallengeReadService,
    ChallengeSpeakingUploadRejected,
)
from app.modules.challenges.models import ChallengeAttempt


from app.modules.challenges.a2z_game.routes import router as a2z_router


router = APIRouter(prefix="/v1", tags=["challenges"])
router.include_router(a2z_router)


def _attempt_read(attempt: ChallengeAttempt) -> ChallengeAttemptRead:
    level = attempt.level
    return ChallengeAttemptRead.model_validate(
        {
            **ChallengeAttemptRead.model_validate(attempt).model_dump(),
            "level_number": level.level_number if level is not None else None,
            "pass_threshold": float(level.pass_threshold)
            if level is not None
            else None,
            "time_limit_seconds": level.time_limit_seconds
            if level is not None
            else None,
        }
    )


@router.get(
    "/challenges",
    response_model=list[ChallengeListItem],
    status_code=status.HTTP_200_OK,
)
def list_challenges(
    current_user: User = Depends(require_learner),
    db: Session = Depends(get_db),
) -> list[ChallengeListItem]:
    """Return active challenges for the authenticated learner."""
    _ = current_user
    return ChallengeReadService(db).list_challenges()


@router.get(
    "/challenges/{slug}",
    response_model=ChallengeDetailRead,
    status_code=status.HTTP_200_OK,
)
def get_challenge_detail(
    slug: str,
    current_user: User = Depends(require_learner),
    db: Session = Depends(get_db),
) -> ChallengeDetailRead:
    """Return challenge details plus this learner's level progress."""
    try:
        return ChallengeReadService(db).get_detail(slug=slug, user_id=current_user.id)
    except ChallengeNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/challenges/{slug}/history",
    response_model=ChallengeHistoryRead,
    status_code=status.HTTP_200_OK,
)
def get_challenge_history(
    slug: str,
    current_user: User = Depends(require_learner),
    db: Session = Depends(get_db),
) -> ChallengeHistoryRead:
    """Return the authenticated learner's personal history for a challenge."""
    try:
        return ChallengeReadService(db).get_history(slug=slug, user_id=current_user.id)
    except ChallengeNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/challenge-attempts/{attempt_id}",
    response_model=ChallengeAttemptRead,
    status_code=status.HTTP_200_OK,
)
def get_challenge_attempt(
    attempt_id: int,
    current_user: User = Depends(require_learner),
    db: Session = Depends(get_db),
) -> ChallengeAttemptRead:
    """Return one challenge attempt if it belongs to the authenticated learner."""
    try:
        attempt = ChallengeReadService(db).get_attempt(
            attempt_id=attempt_id,
            user_id=current_user.id,
        )
    except ChallengeAttemptNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _attempt_read(attempt)


@router.post(
    "/challenge-attempts/{attempt_id}/begin",
    response_model=ChallengeAttemptRead,
    status_code=status.HTTP_200_OK,
)
def begin_challenge_attempt(
    attempt_id: int,
    current_user: User = Depends(require_learner),
    db: Session = Depends(get_db),
) -> ChallengeAttemptRead:
    """Start the server-side sprint timer for a prepared attempt."""
    service = ChallengeReadService(db)
    try:
        attempt = service.begin_attempt(
            attempt_id=attempt_id,
            user_id=current_user.id,
        )
    except ChallengeAttemptNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _attempt_read(attempt)


@router.patch(
    "/challenge-attempts/{attempt_id}/responses",
    response_model=ChallengeAttemptRead,
    status_code=status.HTTP_200_OK,
)
def patch_challenge_attempt_responses(
    attempt_id: int,
    payload: ChallengeAttemptResponsesPatchRequest,
    current_user: User = Depends(require_learner),
    db: Session = Depends(get_db),
) -> ChallengeAttemptRead:
    """Autosave draft section responses for an in-progress attempt."""
    service = ChallengeReadService(db)
    try:
        attempt = service.save_draft_responses(
            attempt_id=attempt_id,
            user_id=current_user.id,
            response_payload=payload.response_payload,
        )
    except ChallengeAttemptNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _attempt_read(attempt)


@router.get(
    "/challenge-attempts/{attempt_id}/audio/{audio_key}",
    status_code=status.HTTP_200_OK,
)
async def get_challenge_attempt_audio(
    attempt_id: int,
    audio_key: str,
    current_user: User = Depends(require_learner),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream one owner-checked listening audio clip for an attempt."""
    service = ChallengeReadService(db)
    try:
        audio_bytes, content_type = await service.get_attempt_audio(
            attempt_id=attempt_id,
            user_id=current_user.id,
            audio_key=audio_key,
        )
    except ChallengeAttemptNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ChallengeAudioNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return StreamingResponse(BytesIO(audio_bytes), media_type=content_type)


@router.get(
    "/challenge-attempts/{attempt_id}/speaking/{prompt_id}/audio/{audio_key}",
    status_code=status.HTTP_200_OK,
)
async def get_challenge_attempt_speaking_audio(
    attempt_id: int,
    prompt_id: str,
    audio_key: str,
    current_user: User = Depends(require_learner),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream one owner-checked speaking upload for an attempt."""
    service = ChallengeReadService(db)
    try:
        audio_bytes, content_type = await service.get_speaking_audio(
            attempt_id=attempt_id,
            user_id=current_user.id,
            prompt_id=prompt_id,
            audio_key=audio_key,
        )
    except ChallengeAttemptNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ChallengeAudioNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return StreamingResponse(BytesIO(audio_bytes), media_type=content_type)


@router.post(
    "/challenge-attempts/{attempt_id}/speaking/{prompt_id}/upload",
    response_model=ChallengeSpeakingUploadRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_challenge_attempt_speaking(
    attempt_id: int,
    prompt_id: str,
    audio: UploadFile = File(...),
    current_user: User = Depends(require_learner),
    db: Session = Depends(get_db),
) -> ChallengeSpeakingUploadRead:
    """Accept one browser-recorded speaking take for a live attempt."""
    service = ChallengeReadService(db)
    audio_bytes = await read_audio_upload(audio)
    try:
        result = await service.upload_speaking_response(
            attempt_id=attempt_id,
            user_id=current_user.id,
            prompt_id=prompt_id,
            audio_bytes=audio_bytes,
            content_type=audio.content_type,
        )
    except ChallengeAttemptNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ChallengeSpeakingUploadRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return ChallengeSpeakingUploadRead.model_validate(result)


@router.post(
    "/challenges/{slug}/levels/{level_number}/attempts",
    response_model=ChallengeAttemptRead,
    status_code=status.HTTP_201_CREATED,
)
async def start_challenge_attempt(
    slug: str,
    level_number: int,
    current_user: User = Depends(require_learner),
    db: Session = Depends(get_db),
) -> ChallengeAttemptRead:
    """Create a timed attempt for one unlocked challenge level."""
    service = ChallengeReadService(db)
    try:
        attempt = await service.start_attempt(
            slug=slug,
            level_number=level_number,
            user_id=current_user.id,
        )
    except ChallengeNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ChallengeLevelNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ChallengeLevelLocked as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ChallengeDailyAttemptLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ChallengeAttemptInProgress as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "attempt_id": exc.attempt_id},
        ) from exc
    return _attempt_read(attempt)


@router.post(
    "/challenge-attempts/{attempt_id}/submit",
    response_model=ChallengeAttemptRead,
    status_code=status.HTTP_200_OK,
)
async def submit_challenge_attempt(
    attempt_id: int,
    payload: ChallengeAttemptSubmitRequest,
    current_user: User = Depends(require_learner),
    db: Session = Depends(get_db),
) -> ChallengeAttemptRead:
    """Persist raw section responses and return current phase evaluation/feedback."""
    service = ChallengeReadService(db)
    try:
        attempt = await service.submit_attempt(
            attempt_id=attempt_id,
            user_id=current_user.id,
            response_payload=payload.response_payload,
        )
    except ChallengeAttemptNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _attempt_read(attempt)
