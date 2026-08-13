"""Pronunciation cache layer — the public-facing pronunciation service.

Composes:
    IPronunciationClient + IBlobStorage = CachedPronunciationService

Same shape as STT:
  - Hash audio + reference text + language + provider config
  - Cache miss: call Azure Speech, store JSON result, return result
  - Cache hit:  read JSON from disk, return result (zero provider cost)

What's cached: the JSON-serialized PronunciationResult only.
What is NOT cached: the raw user audio bytes.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import cast

from app.ai.pronunciation.azure_client import get_default_pronunciation_client
from app.ai.pronunciation.exceptions import PronunciationValidationError
from app.ai.pronunciation.interface import IPronunciationClient, PronunciationResult
from app.ai.storage import (
    BlobVisibility,
    IBlobStorage,
    StorageError,
    StorageReadError,
    build_blob_storage,
)

logger = logging.getLogger(__name__)

_CACHE_NAMESPACE = "azure_pronunciation_assessment_v1"


def _compute_cache_key(
    *,
    audio_bytes: bytes,
    reference_text: str,
    language: str,
    namespace: str = _CACHE_NAMESPACE,
) -> str:
    """Stable cache key from all inputs that affect the score."""
    h = hashlib.sha256()
    h.update(namespace.encode("utf-8"))
    h.update(b"|")
    h.update(language.encode("utf-8"))
    h.update(b"|")
    h.update(reference_text.encode("utf-8"))
    h.update(b"|")
    h.update(audio_bytes)
    digest = h.hexdigest()[:16]
    return f"{digest}.json"


class CachedPronunciationService:
    """High-level pronunciation façade with on-disk dedup caching."""

    def __init__(
        self,
        *,
        provider: IPronunciationClient,
        storage: IBlobStorage,
    ) -> None:
        self._provider = provider
        self._storage = storage

    async def score(
        self,
        *,
        audio_bytes: bytes,
        filename: str,
        reference_text: str,
        language: str = "en-US",
    ) -> PronunciationResult:
        """Score user pronunciation with caching.

        Returns the same PronunciationResult whether served from cache
        or freshly computed by Azure Speech.
        """
        if not audio_bytes:
            raise PronunciationValidationError("audio_bytes must be non-empty")

        cache_key = _compute_cache_key(
            audio_bytes=audio_bytes,
            reference_text=reference_text,
            language=language,
        )

        if await self._storage.exists(key=cache_key):
            try:
                cached_bytes = await self._storage.get(key=cache_key)
            except StorageReadError as exc:
                logger.warning(
                    "pronunciation_cache_read_failed key=%s err=%s; rescoring",
                    cache_key,
                    exc,
                )
                cached_bytes = None

            if cached_bytes is not None:
                try:
                    parsed = json.loads(cached_bytes.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    logger.warning(
                        "pronunciation_cache_corrupt key=%s err=%s; rescoring",
                        cache_key,
                        exc,
                    )
                else:
                    logger.info(
                        "pronunciation_cache_hit key=%s bytes=%d",
                        cache_key,
                        len(audio_bytes),
                    )
                    return cast(PronunciationResult, parsed)

        logger.info(
            "pronunciation_cache_miss key=%s bytes=%d",
            cache_key,
            len(audio_bytes),
        )
        result = await self._provider.score(
            audio_bytes=audio_bytes,
            filename=filename,
            reference_text=reference_text,
            language=language,
        )

        try:
            payload = json.dumps(dict(result), ensure_ascii=False).encode("utf-8")
            await self._storage.put(
                key=cache_key,
                data=payload,
                content_type="application/json",
            )
        except StorageError as exc:
            logger.warning(
                "pronunciation_cache_write_failed key=%s err=%s; returning result anyway",
                cache_key,
                exc,
            )

        return result


_default_service: CachedPronunciationService | None = None


def get_default_pronunciation_service() -> CachedPronunciationService:
    """Return the shared default pronunciation service."""
    global _default_service
    if _default_service is None:
        from app.core.config import settings

        storage = build_blob_storage(
            cache_dir=settings.PRONUNCIATION_CACHE_DIR,
            public_url_prefix="/internal/pronunciation",
            visibility=BlobVisibility.INTERNAL,
        )
        _default_service = CachedPronunciationService(
            provider=get_default_pronunciation_client(),
            storage=storage,
        )
    return _default_service


def _reset_default_pronunciation_service() -> None:
    """Test-only: drop the cached service so the next get_*() rebuilds."""
    global _default_service
    _default_service = None
