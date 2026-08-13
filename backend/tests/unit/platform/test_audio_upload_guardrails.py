"""Shared audio-upload size and duration limits."""

import wave
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile

from app.core.audio_uploads import enforce_wav_duration, read_audio_upload
from app.core.config import settings


@pytest.mark.asyncio
async def test_audio_reader_stops_after_limit_plus_sentinel(monkeypatch) -> None:
    monkeypatch.setattr(settings, "MAX_AUDIO_UPLOAD_BYTES", 10)
    upload = UploadFile(filename="large.webm", file=BytesIO(b"x" * 50))

    with pytest.raises(HTTPException) as exc_info:
        await read_audio_upload(upload)

    assert exc_info.value.status_code == 413
    assert upload.file.tell() == 11


def test_wav_duration_is_rejected_before_provider_call(monkeypatch) -> None:
    monkeypatch.setattr(settings, "MAX_AUDIO_DURATION_SECONDS", 1.0)
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(8_000)
        wav_file.writeframes(b"\x00\x00" * 16_000)

    with pytest.raises(HTTPException) as exc_info:
        enforce_wav_duration(
            buffer.getvalue(),
            filename="recording.wav",
            content_type="audio/wav",
        )

    assert exc_info.value.status_code == 413
