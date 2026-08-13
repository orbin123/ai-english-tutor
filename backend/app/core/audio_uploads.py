"""Shared size and duration guardrails for learner audio uploads."""

from __future__ import annotations

import wave
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings


async def read_audio_upload(upload: UploadFile) -> bytes:
    """Read at most the configured limit plus one sentinel byte."""
    limit = settings.MAX_AUDIO_UPLOAD_BYTES
    audio_bytes = await upload.read(limit + 1)
    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio upload is empty.",
        )
    if len(audio_bytes) > limit:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Audio upload exceeds the configured {limit:,}-byte limit.",
        )
    return audio_bytes


def enforce_audio_duration(duration_seconds: float | int | None) -> None:
    """Reject a provider- or decoder-reported duration above the cap."""
    if duration_seconds is None:
        return
    if float(duration_seconds) > settings.MAX_AUDIO_DURATION_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                "Audio recording exceeds the configured "
                f"{settings.MAX_AUDIO_DURATION_SECONDS:g}-second limit."
            ),
        )


def enforce_wav_duration(
    audio_bytes: bytes,
    *,
    filename: str,
    content_type: str | None,
) -> None:
    """Enforce duration before a provider call when the upload is WAV.

    Browser pronunciation flows already convert to WAV. Other supported audio
    containers are checked using the transcription provider's returned duration.
    Malformed WAV data is left to the existing provider validation so this helper
    does not replace format validation.
    """
    primary_type = (content_type or "").split(";", 1)[0].strip().lower()
    is_wav = (
        primary_type in {"audio/wav", "audio/x-wav"}
        or Path(filename).suffix.lower() == ".wav"
    )
    if not is_wav:
        return

    try:
        with wave.open(BytesIO(audio_bytes), "rb") as wav_file:
            frame_rate = wav_file.getframerate()
            if frame_rate <= 0:
                return
            duration_seconds = wav_file.getnframes() / frame_rate
    except (EOFError, wave.Error):
        return

    enforce_audio_duration(duration_seconds)
