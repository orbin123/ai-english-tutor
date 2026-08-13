"""OpenAI implementation of IImageGenClient.

We use the Image API here because Phase 5 only needs one-shot image
generation from a single prompt. If the product later needs iterative
edits or conversational image refinement, that can move to the
Responses API without changing callers above this layer.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import random
from typing import Any

import openai
from openai import AsyncOpenAI

from app.ai.imagegen.exceptions import (
    ImageGenAuthError,
    ImageGenError,
    ImageGenProviderError,
    ImageGenRateLimited,
    ImageGenTimeout,
    ImageGenValidationError,
)
from app.ai.imagegen.interface import (
    AspectRatio,
    GeneratedImage,
    dimensions_for_aspect_ratio,
    size_string_for_aspect_ratio,
)
from app.core.ai_concurrency import ai_provider_slot
from app.core.config import settings

logger = logging.getLogger(__name__)

_SUPPORTED_OUTPUT_FORMATS: frozenset[str] = frozenset({"png", "jpeg", "webp"})
_SUPPORTED_QUALITIES: frozenset[str] = frozenset(
    {
        "low",
        "medium",
        "high",
        "auto",
    }
)


class OpenAIImageGenClient:
    """Concrete `IImageGenClient` backed by OpenAI's Image API."""

    def __init__(
        self,
        *,
        model: str | None = None,
        quality: str | None = None,
        output_format: str | None = None,
        timeout: float = 120.0,
        max_retries: int = 3,
    ) -> None:
        self._model = model or settings.OPENAI_IMAGE_MODEL
        self._quality = quality or settings.OPENAI_IMAGE_QUALITY
        self._format = output_format or settings.OPENAI_IMAGE_OUTPUT_FORMAT
        self._timeout = timeout
        self._max_retries = max_retries
        self._validate_configuration()
        self._client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=timeout,
        )

    @property
    def model_name(self) -> str:
        """Public read-only access for cache-key construction."""
        return self._model

    @property
    def output_format(self) -> str:
        """Public read-only access for storage/content-type decisions."""
        return self._format

    @property
    def default_quality(self) -> str:
        """Public read-only access for cache-key construction."""
        return self._quality

    async def generate(
        self,
        *,
        prompt: str,
        aspect_ratio: AspectRatio = "square",
        style: str | None = None,
    ) -> GeneratedImage:
        """Generate raw image bytes from one text prompt."""
        cleaned_prompt = prompt.strip()
        if not cleaned_prompt:
            raise ImageGenValidationError("prompt must be non-empty")

        cleaned_style = style.strip() if style is not None else ""
        if style is not None and not cleaned_style:
            cleaned_style = ""

        try:
            width, height = dimensions_for_aspect_ratio(aspect_ratio)
            size = size_string_for_aspect_ratio(aspect_ratio)
        except ValueError as exc:
            raise ImageGenValidationError(str(exc)) from exc

        provider_prompt = self._build_provider_prompt(
            prompt=cleaned_prompt,
            style=cleaned_style or None,
        )

        kwargs: dict[str, Any] = {
            "model": self._model,
            "prompt": provider_prompt,
            "n": 1,
            "size": size,
            "quality": self._quality,
            "output_format": self._format,
        }

        async with ai_provider_slot():
            raw = await self._call_with_retries(kwargs)
        image_bytes = self._extract_image_bytes(raw)

        self._log_usage(
            raw=raw,
            aspect_ratio=aspect_ratio,
            width=width,
            height=height,
            prompt_chars=len(cleaned_prompt),
            has_style=bool(cleaned_style),
        )
        return GeneratedImage(
            image_bytes=image_bytes,
            width=width,
            height=height,
        )

    def _validate_configuration(self) -> None:
        """Fail fast if local config asks for unsupported options."""
        if not self._model.strip():
            raise ImageGenValidationError("OPENAI_IMAGE_MODEL must be non-empty")
        if self._format not in _SUPPORTED_OUTPUT_FORMATS:
            raise ImageGenValidationError(
                f"OPENAI_IMAGE_OUTPUT_FORMAT must be one of "
                f"{sorted(_SUPPORTED_OUTPUT_FORMATS)}, got {self._format!r}"
            )
        if self._quality not in _SUPPORTED_QUALITIES:
            raise ImageGenValidationError(
                f"OPENAI_IMAGE_QUALITY must be one of "
                f"{sorted(_SUPPORTED_QUALITIES)}, got {self._quality!r}"
            )

    @staticmethod
    def _build_provider_prompt(*, prompt: str, style: str | None) -> str:
        """Fold optional style guidance into the provider prompt.

        GPT Image models do not expose the old DALL·E-style `style`
        parameter, so a free-form style hint is appended as natural
        language guidance instead.
        """
        if not style:
            return prompt
        return f"{prompt}\n\nStyle guidance: {style}"

    async def _call_with_retries(self, kwargs: dict[str, Any]) -> Any:
        """Call the OpenAI images.generate endpoint with manual retries."""
        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                return await self._client.images.generate(**kwargs)
            except (
                openai.AuthenticationError,
                openai.BadRequestError,
                openai.PermissionDeniedError,
            ) as exc:
                raise self._translate_exception(exc) from exc
            except (
                openai.RateLimitError,
                openai.APITimeoutError,
                openai.APIConnectionError,
                openai.InternalServerError,
            ) as exc:
                last_exc = exc
                if attempt == self._max_retries:
                    break
                delay = (2 ** (attempt - 1)) * (1 + random.uniform(-0.25, 0.25))
                logger.warning(
                    "imagegen_retry attempt=%d/%d delay=%.2fs err=%s",
                    attempt,
                    self._max_retries,
                    delay,
                    type(exc).__name__,
                )
                await asyncio.sleep(delay)
            except Exception as exc:
                raise self._translate_exception(exc) from exc

        assert last_exc is not None
        raise self._translate_exception(last_exc) from last_exc

    @staticmethod
    def _translate_exception(exc: Exception) -> ImageGenError:
        """Map provider exceptions into our ImageGenError family."""
        if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
            return ImageGenAuthError(f"OpenAI image generation auth failed: {exc}")
        if isinstance(exc, openai.RateLimitError):
            return ImageGenRateLimited(f"OpenAI image generation rate limit: {exc}")
        if isinstance(exc, openai.APITimeoutError):
            return ImageGenTimeout(f"OpenAI image generation timed out: {exc}")
        if isinstance(exc, openai.BadRequestError):
            return ImageGenValidationError(
                f"OpenAI rejected image-generation request: {exc}"
            )
        if isinstance(exc, openai.APIError):
            return ImageGenProviderError(f"OpenAI image generation API error: {exc}")
        return ImageGenProviderError(f"Unexpected image-generation failure: {exc}")

    @staticmethod
    def _extract_image_bytes(raw: Any) -> bytes:
        """Decode the first base64 image payload from the SDK response."""
        data = getattr(raw, "data", None) or []
        if not data:
            raise ImageGenProviderError("OpenAI returned no image data.")

        b64_payload = getattr(data[0], "b64_json", None)
        if not b64_payload:
            raise ImageGenProviderError(
                "OpenAI image response did not include base64 image data."
            )

        try:
            return base64.b64decode(b64_payload, validate=True)
        except (ValueError, TypeError) as exc:
            raise ImageGenProviderError(
                f"OpenAI returned malformed image data: {exc}"
            ) from exc

    def _log_usage(
        self,
        *,
        raw: Any,
        aspect_ratio: AspectRatio,
        width: int,
        height: int,
        prompt_chars: int,
        has_style: bool,
    ) -> None:
        """Log one structured line per successful generation."""
        usage = getattr(raw, "usage", None)
        logger.info(
            "imagegen_success model=%s size=%dx%d aspect_ratio=%s quality=%s "
            "format=%s prompt_chars=%d style=%s input_tokens=%s "
            "output_tokens=%s total_tokens=%s",
            self._model,
            width,
            height,
            aspect_ratio,
            self._quality,
            self._format,
            prompt_chars,
            has_style,
            getattr(usage, "input_tokens", None),
            getattr(usage, "output_tokens", None),
            getattr(usage, "total_tokens", None),
        )


_default_client: OpenAIImageGenClient | None = None


def get_default_imagegen_client() -> OpenAIImageGenClient:
    """Return the shared default OpenAI image-generation client."""
    global _default_client
    if _default_client is None:
        _default_client = OpenAIImageGenClient()
    return _default_client


def _reset_default_imagegen_client() -> None:
    """Test-only: drop the cached client so the next get_*() rebuilds."""
    global _default_client
    _default_client = None
