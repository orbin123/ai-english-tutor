"""Image-generation cache layer — the public-facing image service.

Composes:
    IImageGenClient + IBlobStorage = CachedImageGenService

Same shape as TTS:
  - Hash prompt + aspect ratio + style + provider config
  - Cache miss: call OpenAI, store image, return URL
  - Cache hit:  rebuild URL from storage key, return it (zero provider cost)
"""

from __future__ import annotations

import hashlib
import logging

from app.ai.imagegen.exceptions import ImageGenValidationError
from app.ai.imagegen.interface import (
    AspectRatio,
    IImageGenClient,
    ImageResult,
    dimensions_for_aspect_ratio,
)
from app.ai.imagegen.openai_client import get_default_imagegen_client
from app.ai.storage import IBlobStorage, build_blob_storage

logger = logging.getLogger(__name__)


def _compute_cache_key(
    *,
    prompt: str,
    aspect_ratio: AspectRatio,
    style: str | None,
    model: str,
    quality: str,
    output_format: str,
) -> str:
    """Build a stable cache key from all inputs that affect the image."""
    parts = "|".join(
        [
            model,
            quality,
            output_format,
            aspect_ratio,
            style or "",
            prompt,
        ]
    )
    digest = hashlib.sha256(parts.encode("utf-8")).hexdigest()[:16]
    return f"{digest}.{output_format}"


class CachedImageGenService:
    """High-level image-generation façade with on-disk dedup caching."""

    def __init__(
        self,
        *,
        provider: IImageGenClient,
        storage: IBlobStorage,
    ) -> None:
        self._provider = provider
        self._storage = storage
        self._content_type_map: dict[str, str] = {
            "png": "image/png",
            "jpeg": "image/jpeg",
            "webp": "image/webp",
        }

    async def generate(
        self,
        *,
        prompt: str,
        aspect_ratio: AspectRatio = "square",
        style: str | None = None,
    ) -> ImageResult:
        """Generate one image and return its public URL + dimensions."""
        from app.core.config import settings

        if not settings.ENABLE_IMAGE_GENERATION:
            raise ImageGenValidationError(
                "Image generation is disabled on this deployment."
            )

        cleaned_prompt = prompt.strip()
        if not cleaned_prompt:
            raise ImageGenValidationError("prompt must be non-empty")

        cleaned_style = style.strip() if style is not None else None
        if cleaned_style == "":
            cleaned_style = None

        try:
            width, height = dimensions_for_aspect_ratio(aspect_ratio)
        except ValueError as exc:
            raise ImageGenValidationError(str(exc)) from exc

        cache_key = _compute_cache_key(
            prompt=cleaned_prompt,
            aspect_ratio=aspect_ratio,
            style=cleaned_style,
            model=self._provider.model_name,
            quality=self._provider.default_quality,
            output_format=self._provider.output_format,
        )

        if await self._storage.exists(key=cache_key):
            logger.info(
                "imagegen_cache_hit key=%s chars=%d aspect_ratio=%s",
                cache_key,
                len(cleaned_prompt),
                aspect_ratio,
            )
            return ImageResult(
                image_url=self._storage.url_for(key=cache_key),
                width=width,
                height=height,
                cache_hit=True,
            )

        logger.info(
            "imagegen_cache_miss key=%s chars=%d aspect_ratio=%s",
            cache_key,
            len(cleaned_prompt),
            aspect_ratio,
        )
        from app.modules.quotas.constants import QuotaMetric
        from app.modules.quotas.service import consume_quota

        consume_quota(QuotaMetric.IMAGE_GENS)
        provider_result = await self._provider.generate(
            prompt=cleaned_prompt,
            aspect_ratio=aspect_ratio,
            style=cleaned_style,
        )
        content_type = self._content_type_map.get(
            self._provider.output_format,
            "application/octet-stream",
        )
        stored = await self._storage.put(
            key=cache_key,
            data=provider_result["image_bytes"],
            content_type=content_type,
        )
        return ImageResult(
            image_url=stored["public_url"],
            width=provider_result["width"],
            height=provider_result["height"],
            cache_hit=False,
        )


_default_service: CachedImageGenService | None = None


def get_default_imagegen_service() -> CachedImageGenService:
    """Return the shared default image-generation service."""
    global _default_service
    if _default_service is None:
        from app.core.config import settings

        storage = build_blob_storage(
            cache_dir=settings.IMAGEGEN_CACHE_DIR,
            public_url_prefix=settings.IMAGEGEN_PUBLIC_URL_PREFIX,
        )
        _default_service = CachedImageGenService(
            provider=get_default_imagegen_client(),
            storage=storage,
        )
    return _default_service


def _reset_default_imagegen_service() -> None:
    """Test-only: drop the cached service so the next get_*() rebuilds."""
    global _default_service
    _default_service = None
