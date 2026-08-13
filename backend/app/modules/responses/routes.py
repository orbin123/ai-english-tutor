"""Learner response routes.

`POST /responses/transcribe-audio` — used by the SpeakRecordWidget on the
session/chat page. The widget records a blob, posts it here, and uses the
returned transcript + audio_url in its local `recordings[]` answer state.
The transcript is what the evaluator + feedback generator then grade on
submit.
"""

from __future__ import annotations

import hashlib
import logging
import time
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.ai.storage import (
    BlobVisibility,
    IBlobStorage,
    StorageError,
    build_blob_storage,
)
from app.ai.stt import get_default_stt_service
from app.ai.stt.exceptions import (
    STTError,
    STTPayloadTooLarge,
    STTValidationError,
)
from app.core.ai_rate_limit import ai_rate_limit
from app.core.audio_uploads import enforce_audio_duration, read_audio_upload
from app.modules.subscriptions.dependencies import require_active_access
from app.core.config import settings
from app.modules.auth.dependencies import get_current_user, require_learner
from app.modules.auth.models import User
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/responses",
    tags=["responses"],
    dependencies=[Depends(require_learner)],
)


class TranscribeResponse(BaseModel):
    transcript: str
    audio_url: str


_AUDIO_EXTENSIONS = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".mp4",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/flac": ".flac",
}
_LEARNER_AUDIO_URL_PREFIX = "/responses/audio"
_learner_audio_storage: IBlobStorage | None = None


def get_learner_audio_storage() -> IBlobStorage:
    """Return the private learner-audio storage client.

    Private visibility keeps the clip off every anonymous object URL —
    `url_for` returns the owner-checked `/responses/audio/...` route below,
    which streams the bytes back through `storage.get`.
    """
    global _learner_audio_storage
    if _learner_audio_storage is None:
        _learner_audio_storage = build_blob_storage(
            cache_dir=settings.LEARNER_AUDIO_DIR,
            public_url_prefix=_LEARNER_AUDIO_URL_PREFIX,
            visibility=BlobVisibility.PRIVATE,
        )
    return _learner_audio_storage


def _reset_learner_audio_storage() -> None:
    """Test helper: rebuild storage after monkeypatching settings."""
    global _learner_audio_storage
    _learner_audio_storage = None


def _normalized_audio_content_type(content_type: str | None) -> str:
    primary = (content_type or "").split(";", 1)[0].strip().lower()
    if primary not in _AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail="Unsupported audio content type.",
        )
    return primary


def _extension_for(filename: str, content_type: str | None) -> str:
    if content_type:
        primary = content_type.split(";", 1)[0].strip().lower()
        if primary in _AUDIO_EXTENSIONS:
            return _AUDIO_EXTENSIONS[primary]
    name = (filename or "").lower()
    for ext in (".webm", ".ogg", ".mp4", ".m4a", ".mp3", ".wav", ".flac"):
        if name.endswith(ext):
            return ext
    return ".webm"


def _content_type_for_key(audio_key: str) -> str:
    suffix = Path(audio_key).suffix.lower()
    for content_type, ext in _AUDIO_EXTENSIONS.items():
        if suffix == ext:
            return content_type
    return "application/octet-stream"


@router.post(
    "/transcribe-audio",
    response_model=TranscribeResponse,
    dependencies=[
        Depends(require_active_access),
        Depends(
            ai_rate_limit(
                "transcribe",
                limit_setting="AI_RATE_LIMIT_TRANSCRIBE_PER_MINUTE",
            )
        ),
    ],
)
async def transcribe_audio(
    audio: UploadFile = File(..., description="Learner audio recording."),
    language: str = Form(default="en"),
    current_user: User = Depends(get_current_user),
) -> TranscribeResponse:
    """Persist the uploaded clip and return its Whisper transcript + URL.

    The widget uses `audio_url` to play back the learner's clip alongside
    feedback after the activity is submitted.
    """
    content_type = _normalized_audio_content_type(audio.content_type)
    audio_bytes = await read_audio_upload(audio)

    ext = _extension_for(audio.filename or "", content_type)

    digest = hashlib.sha256(audio_bytes).hexdigest()[:24]
    storage_key = f"{digest}-learner-{current_user.id}-{int(time.time() * 1000)}{ext}"

    stt = get_default_stt_service()
    try:
        result = await stt.transcribe(
            audio_bytes=audio_bytes,
            filename=audio.filename or f"recording{ext}",
            language=language,
            with_timestamps=False,
        )
        enforce_audio_duration(result.get("duration_seconds"))
    except STTPayloadTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except STTValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except STTError as exc:
        logger.warning("STT failed for key=%s: %s", storage_key, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    storage = get_learner_audio_storage()
    try:
        stored = await storage.put(
            key=storage_key,
            data=audio_bytes,
            content_type=content_type,
        )
    except Exception as exc:
        logger.exception("Failed to persist learner audio key=%s", storage_key)
        raise HTTPException(status_code=500, detail="Could not save audio.") from exc

    transcript = (result.get("text") or "").strip()
    return TranscribeResponse(transcript=transcript, audio_url=stored["public_url"])


@router.get("/audio/{shard}/{audio_key}", include_in_schema=False)
async def get_learner_audio(
    shard: str,
    audio_key: str,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Serve one learner-owned recording through auth instead of StaticFiles."""
    if shard != audio_key[:2] or f"-learner-{current_user.id}-" not in audio_key:
        raise HTTPException(status_code=404, detail="Audio not found.")

    try:
        audio_bytes = await get_learner_audio_storage().get(key=audio_key)
    except StorageError as exc:
        logger.warning("Invalid learner audio key=%s: %s", audio_key, exc)
        raise HTTPException(status_code=404, detail="Audio not found.") from exc

    if audio_bytes is None:
        raise HTTPException(status_code=404, detail="Audio not found.")

    return StreamingResponse(
        BytesIO(audio_bytes),
        media_type=_content_type_for_key(audio_key),
    )
