"""TTS cache layer — the public-facing TTS service.

This is the layer agents and routes actually import. It composes:

    ITTSClient  +  IBlobStorage  =  CachedTTSService

The contract:
  - Same (text, voice, speed, instructions, model) -> always same audio
  - First call:  OpenAI -> storage write -> metadata write -> URL
  - Later calls: storage read + metadata read -> URL/duration ($0)

Why a separate layer (not a method on OpenAITTSClient)?
  - Single Responsibility: providers do TTS, storage stores blobs, this
    glues them together. Either side can be swapped without rewriting
    the cache.
  - Testability: feed in a fake provider + fake storage to unit-test
    cache hits / misses without touching the network or disk.
"""

from __future__ import annotations

import hashlib
import json
import logging

from typing_extensions import TypedDict

from app.ai.storage import IBlobStorage, StorageError, get_default_blob_storage
from app.ai.tts.exceptions import TTSValidationError
from app.ai.tts.interface import ITTSClient, SynthesisResult
from app.ai.tts.openai_client import get_default_tts_client

logger = logging.getLogger(__name__)


class TTSDurationMetadata(TypedDict):
    """Sidecar metadata persisted alongside cached audio."""

    duration_seconds: float


def _compute_cache_key(
    *,
    text: str,
    voice: str,
    speed: float,
    style_instructions: str | None,
    model: str,
    audio_format: str,
) -> str:
    """Build a stable cache key from all inputs that affect the audio.

    SHA-256 is overkill for collision safety here, but it's the
    cheapest way to guarantee no clash for many years of usage.
    Truncated to 16 hex chars (64 bits) — Birthday collisions become
    likely only past ~2^32 entries (4 billion). We won't hit that.

    Format: <16-char-hash>.<extension>
    Example: "a3f9c2e8b1d04f6e.mp3"

    Why include `model` in the hash? gpt-4o-mini-tts and tts-1 produce
    audibly different output. Switching models without busting the
    cache would serve stale audio.

    Why include `style_instructions`? It changes delivery noticeably
    on gpt-4o-mini-tts. None and "" must hash differently from
    "speak slowly" so we normalize None → "".
    """
    parts = "|".join(
        [
            model,
            voice,
            f"{speed:.2f}",
            style_instructions or "",
            text,
        ]
    )
    digest = hashlib.sha256(parts.encode("utf-8")).hexdigest()[:16]
    return f"{digest}.{audio_format}"


def _metadata_key_for(cache_key: str) -> str:
    """Return the JSON sidecar key for one audio cache key."""
    return f"{cache_key}.meta.json"


class CachedTTSService:
    """High-level TTS façade with on-disk dedup caching.

    Usage:
        service = get_default_tts_service()
        result = await service.synthesize(text="Hello!", voice="alloy")
        audio_url = result["audio_url"]
        was_cached = result["cache_hit"]
    """

    def __init__(
        self,
        *,
        provider: ITTSClient,
        storage: IBlobStorage,
    ) -> None:
        self._provider = provider
        self._storage = storage
        # mp3 is the only content_type we currently produce; if you ever
        # change the format, update the lookup below.
        self._content_type_map: dict[str, str] = {
            "mp3": "audio/mpeg",
            "opus": "audio/opus",
            "aac": "audio/aac",
            "flac": "audio/flac",
            "wav": "audio/wav",
            "pcm": "audio/L16",
        }

    # ------------------------------------------------------------------
    # Public — synthesize with caching
    # ------------------------------------------------------------------
    async def synthesize(
        self,
        *,
        text: str,
        voice: str | None = None,
        speed: float = 1.0,
        style_instructions: str | None = None,
    ) -> SynthesisResult:
        """Get an audio URL for `text`. Hits cache on repeat calls.

        Returns a SynthesisResult with the public URL ready for the
        frontend to drop into <audio src=...>.

        Raises:
            TTSValidationError, TTSAuthError, TTSRateLimited,
            TTSTimeout, TTSProviderError, StorageError — bubbled up
            from the underlying provider / storage. Caller catches
            TTSError for "the synthesizer failed" and StorageError
            for "we couldn't save the file".
        """
        if not text or not text.strip():
            raise TTSValidationError("text must be non-empty")

        # Resolve effective voice / model so they're correctly hashed.
        # We mirror the same defaults the provider uses, so the cache
        # key matches the provider's actual call shape.
        effective_voice = voice or self._provider.default_voice_id
        effective_model = self._provider.model_name
        audio_format = self._provider.response_format

        cache_key = _compute_cache_key(
            text=text,
            voice=effective_voice,
            speed=speed,
            style_instructions=style_instructions,
            model=effective_model,
            audio_format=audio_format,
        )

        # ---- 1. Cache check
        if await self._storage.exists(key=cache_key):
            logger.info("tts_cache_hit key=%s chars=%d", cache_key, len(text))
            return await self._build_cached_result(cache_key)

        # ---- 2. Cache miss — synthesize then store
        logger.info("tts_cache_miss key=%s chars=%d", cache_key, len(text))
        from app.modules.quotas.constants import QuotaMetric
        from app.modules.quotas.service import consume_quota

        consume_quota(QuotaMetric.TTS_CHARS, amount=len(text))
        provider_result = await self._provider.synthesize(
            text=text,
            voice_id=effective_voice,
            speed=speed,
            style_instructions=style_instructions,
        )
        content_type = self._content_type_map.get(
            audio_format, "application/octet-stream"
        )
        stored = await self._storage.put(
            key=cache_key,
            data=provider_result["audio_bytes"],
            content_type=content_type,
        )
        await self._persist_duration_metadata(
            cache_key=cache_key,
            duration_seconds=provider_result["duration_seconds"],
        )

        return SynthesisResult(
            audio_url=stored["public_url"],
            duration_seconds=provider_result["duration_seconds"],
            cache_hit=False,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    async def _build_cached_result(self, cache_key: str) -> SynthesisResult:
        """Build a SynthesisResult for a cache hit WITHOUT re-reading
        the bytes off disk.

        Newer cache entries carry a JSON sidecar with the exact
        duration. Older entries created before that change are
        backfilled on first read by estimating from the cached audio.
        """
        url = self._storage.url_for(key=cache_key)
        duration = await self._read_or_backfill_duration(cache_key=cache_key)

        return SynthesisResult(
            audio_url=url,
            duration_seconds=duration,
            cache_hit=True,
        )

    async def _read_or_backfill_duration(self, *, cache_key: str) -> float:
        """Read cached duration metadata, or backfill it for old entries."""
        metadata_key = _metadata_key_for(cache_key)

        try:
            raw_metadata = await self._storage.get(key=metadata_key)
        except StorageError as exc:
            logger.warning(
                "tts_cache_metadata_read_failed key=%s err=%s; backfilling",
                metadata_key,
                exc,
            )
            raw_metadata = None

        if raw_metadata is not None:
            try:
                parsed = json.loads(raw_metadata.decode("utf-8"))
                duration = round(float(parsed["duration_seconds"]), 2)
            except (
                UnicodeDecodeError,
                json.JSONDecodeError,
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                logger.warning(
                    "tts_cache_metadata_corrupt key=%s err=%s; backfilling",
                    metadata_key,
                    exc,
                )
            else:
                return duration

        try:
            audio_bytes = await self._storage.get(key=cache_key)
        except StorageError as exc:
            logger.warning(
                "tts_cache_audio_read_failed key=%s err=%s; returning 0.0",
                cache_key,
                exc,
            )
            return 0.0

        if audio_bytes is None:
            logger.warning(
                "tts_cache_audio_missing_after_exists key=%s; returning 0.0",
                cache_key,
            )
            return 0.0

        duration = self._provider.estimate_duration_seconds(audio_bytes=audio_bytes)
        await self._persist_duration_metadata(
            cache_key=cache_key,
            duration_seconds=duration,
        )
        logger.info(
            "tts_cache_metadata_backfilled key=%s duration=%.2f",
            cache_key,
            duration,
        )
        return duration

    async def _persist_duration_metadata(
        self,
        *,
        cache_key: str,
        duration_seconds: float,
    ) -> None:
        """Persist sidecar metadata for cache-hit parity.

        Metadata write failures are non-fatal: the audio is already
        usable, and we can always backfill the sidecar later.
        """
        metadata_key = _metadata_key_for(cache_key)
        payload = TTSDurationMetadata(
            duration_seconds=round(duration_seconds, 2),
        )
        try:
            await self._storage.put(
                key=metadata_key,
                data=json.dumps(payload).encode("utf-8"),
                content_type="application/json",
            )
        except StorageError as exc:
            logger.warning(
                "tts_cache_metadata_write_failed key=%s err=%s; continuing",
                metadata_key,
                exc,
            )


# ---------------------------------------------------------------------------
# Process-wide singleton (lazy)
# ---------------------------------------------------------------------------
_default_service: CachedTTSService | None = None


def get_default_tts_service() -> CachedTTSService:
    """Return the shared default TTS service (provider + cache + storage).

    Lazy — first call wires up the provider singleton and the storage
    singleton. Tests can call `_reset_default_tts_service()` to force a
    fresh build with mocked dependencies.
    """
    global _default_service
    if _default_service is None:
        _default_service = CachedTTSService(
            provider=get_default_tts_client(),
            storage=get_default_blob_storage(),
        )
    return _default_service


def _reset_default_tts_service() -> None:
    """Test-only: drop the cached service so the next get_*() rebuilds."""
    global _default_service
    _default_service = None
