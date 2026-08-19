"""STT cache layer — the public-facing transcription service.

Composes:
    OpenAISTTClient + IBlobStorage = CachedSTTService

Same shape as CachedTTSService:
  - Hash inputs (audio bytes + language + with_timestamps + model)
  - Cache miss: call OpenAI, store JSON, return result
  - Cache hit:  read JSON from disk, return result (zero cost)

What's cached: the JSON-serialised TranscriptionResult.
What is NOT cached: the raw audio bytes. We never persist user audio —
only the resulting transcript. This is a privacy + cost decision.

Why a separate storage instance from TTS?
- Different content type (application/json vs audio/mpeg)
- Different retention story (transcripts may be more sensitive than
  tutor-spoken audio prompts)
- Different access pattern (transcripts are read by the agent layer,
  TTS audio is served to the browser)
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import cast

from app.ai.storage import (
    BlobVisibility,
    IBlobStorage,
    StorageError,
    StorageReadError,
    build_blob_storage,
)
from app.ai.stt.exceptions import STTValidationError
from app.ai.stt.interface import TranscriptionResult
from app.ai.stt.openai_client import OpenAISTTClient, get_default_stt_client

logger = logging.getLogger(__name__)


def _compute_cache_key(
    *,
    audio_bytes: bytes,
    language: str,
    with_timestamps: bool,
    model: str,
) -> str:
    """Stable cache key from all inputs that affect the transcript.

    SHA-256 of the audio bytes + the call parameters. Truncated to 16
    hex chars — same approach as the TTS cache. Audio identity is what
    drives the bulk of the entropy here; the same recording will always
    hash to the same key regardless of who uploads it.

    Why include `model`? whisper-1 vs gpt-4o-transcribe produce
    different transcripts. Switching model without busting the cache
    would serve stale results.

    Why include `with_timestamps`? The result shape differs (words
    field is None vs populated). Caching them under the same key would
    leak stale-shape data across calls.

    Format: <16-char-hash>.json
    """
    h = hashlib.sha256()
    h.update(audio_bytes)
    h.update(b"|")
    h.update(model.encode("utf-8"))
    h.update(b"|")
    h.update(language.encode("utf-8"))
    h.update(b"|")
    h.update(b"ts" if with_timestamps else b"plain")
    digest = h.hexdigest()[:16]
    return f"{digest}.json"


class CachedSTTService:
    """High-level STT façade with on-disk dedup caching.

    Usage:
        service = get_default_stt_service()
        result = await service.transcribe(
            audio_bytes=data,
            filename="recording.webm",
            with_timestamps=False,
        )
        text = result["text"]
    """

    def __init__(
        self,
        *,
        provider: OpenAISTTClient,
        storage: IBlobStorage,
    ) -> None:
        self._provider = provider
        self._storage = storage

    # ------------------------------------------------------------------
    # Public — transcribe with caching
    # ------------------------------------------------------------------
    async def transcribe(
        self,
        *,
        audio_bytes: bytes,
        filename: str,
        language: str = "en",
        with_timestamps: bool = False,
    ) -> TranscriptionResult:
        """Transcribe audio. Hits cache on repeat calls with same inputs.

        Returns the same TranscriptionResult shape whether served from
        cache or freshly synthesized.

        Cache hits also fill in `cache_hit=True` semantically — but our
        TranscriptionResult TypedDict doesn't currently carry that flag
        (TTS does because the audio_url is what changes; here the text
        is identical either way). If you need to know whether a call
        was cached, the structured log line `stt_cache_hit` vs
        `stt_cache_miss` tells you.

        Raises:
            STTValidationError + subclasses, STTError + subclasses,
            StorageError. Caller catches STTError for "the transcriber
            failed" and StorageError for "we couldn't read/save the
            cache file".
        """
        if not audio_bytes:
            raise STTValidationError("audio_bytes must be non-empty")

        cache_key = _compute_cache_key(
            audio_bytes=audio_bytes,
            language=language,
            with_timestamps=with_timestamps,
            model=self._provider._model,  # noqa: SLF001
        )

        # ---- 1. Cache check
        if await self._storage.exists(key=cache_key):
            try:
                cached_bytes = await self._storage.get(key=cache_key)
            except StorageReadError as exc:
                # Treat read failures as a cache miss rather than failing
                # the whole request — we can always re-transcribe.
                logger.warning(
                    "stt_cache_read_failed key=%s err=%s; falling back to provider",
                    cache_key,
                    exc,
                )
                cached_bytes = None

            if cached_bytes is not None:
                try:
                    parsed = json.loads(cached_bytes.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    # Cache file is corrupt — log + re-transcribe, don't crash.
                    logger.warning(
                        "stt_cache_corrupt key=%s err=%s; re-transcribing",
                        cache_key,
                        exc,
                    )
                else:
                    logger.info(
                        "stt_cache_hit key=%s bytes=%d",
                        cache_key,
                        len(audio_bytes),
                    )
                    return cast(TranscriptionResult, parsed)

        # ---- 2. Cache miss — call provider
        logger.info(
            "stt_cache_miss key=%s bytes=%d with_timestamps=%s",
            cache_key,
            len(audio_bytes),
            with_timestamps,
        )
        result = await self._provider.transcribe(
            audio_bytes=audio_bytes,
            filename=filename,
            language=language,
            with_timestamps=with_timestamps,
        )

        duration_seconds = result.get("duration_seconds")
        if duration_seconds is not None:
            from math import ceil

            from app.modules.quotas.constants import QuotaMetric
            from app.modules.quotas.service import consume_quota

            consume_quota(
                QuotaMetric.SPEECH_MINUTES,
                amount=max(1, int(ceil(float(duration_seconds) / 60.0))),
            )

        # ---- 3. Persist for next time. Failures here are NOT fatal —
        # we already have a valid result; failing the request because
        # the cache write hiccupped would be silly.
        try:
            payload = json.dumps(dict(result), ensure_ascii=False).encode("utf-8")
            await self._storage.put(
                key=cache_key,
                data=payload,
                content_type="application/json",
            )
        except StorageError as exc:
            logger.warning(
                "stt_cache_write_failed key=%s err=%s; returning result anyway",
                cache_key,
                exc,
            )

        return result


# ---------------------------------------------------------------------------
# Process-wide singleton (lazy)
# ---------------------------------------------------------------------------
_default_service: CachedSTTService | None = None


def get_default_stt_service() -> CachedSTTService:
    """Return the shared default STT service (provider + cache + storage).

    Lazy — first call wires up the provider singleton and creates a
    dedicated `LocalBlobStorage` instance for STT cache files.
    Tests can call `_reset_default_stt_service()` to force a rebuild.
    """
    global _default_service
    if _default_service is None:
        from app.core.config import settings

        # STT gets its OWN storage instance with its own root + URL prefix.
        # Transcripts are JSON sidecars; we never serve them via StaticFiles
        # (they're read by the service layer, not the browser), so the
        # url_prefix is purely cosmetic for the StoredBlob's `public_url`.
        storage = build_blob_storage(
            cache_dir=settings.STT_CACHE_DIR,
            public_url_prefix="/internal/stt",  # not actually mounted
            visibility=BlobVisibility.INTERNAL,
        )
        _default_service = CachedSTTService(
            provider=get_default_stt_client(),
            storage=storage,
        )
    return _default_service


def _reset_default_stt_service() -> None:
    """Test-only: drop the cached service so the next get_*() rebuilds."""
    global _default_service
    _default_service = None
