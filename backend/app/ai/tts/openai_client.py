"""OpenAI implementation of ITTSClient.

Notes on what's different from the LLM client:

1. We use the raw `openai.AsyncOpenAI` SDK here, not LangChain. LangChain
   doesn't wrap the audio endpoints meaningfully — it would just add a
   layer with no benefit.

2. Retries are done manually (small loop, exponential backoff) since the
   audio.speech.create() call doesn't have a built-in `max_retries` knob
   we can rely on the same way as ChatOpenAI.

3. `gpt-4o-mini-tts` supports the `instructions` parameter — text like
   "speak slowly and clearly" or "sound encouraging". This is the killer
   feature for a tutor app and we expose it via the `style_instructions`
   argument on synthesize().

4. We do NOT cache here. Caching is the responsibility of the next layer
   (cache.py) so providers stay simple and the cache logic is testable
   in isolation.

5. Cost-tracking: OpenAI bills TTS by characters, not tokens. We log
   character count + estimated cost on every successful call.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

import openai
from openai import AsyncOpenAI

from app.ai.tts.exceptions import (
    TTSAuthError,
    TTSError,
    TTSProviderError,
    TTSRateLimited,
    TTSTimeout,
    TTSValidationError,
)
from app.ai.tts.interface import DialogueTurn, SynthesizedAudio
from app.core.ai_concurrency import ai_provider_slot
from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Voices supported by gpt-4o-mini-tts.
# Source: https://platform.openai.com/docs/guides/text-to-speech (2026-05).
# Older models (tts-1, tts-1-hd) support a smaller subset — if you ever
# switch model, narrow this list accordingly.
# ---------------------------------------------------------------------------
_VALID_VOICES_GPT4O_MINI_TTS: frozenset[str] = frozenset(
    {
        "alloy",
        "ash",
        "ballad",
        "coral",
        "echo",
        "fable",
        "onyx",
        "nova",
        "sage",
        "shimmer",
        "verse",
    }
)

# Pricing for gpt-4o-mini-tts. OpenAI bills TTS per *character* of input
# (not output tokens). Source: openai.com/pricing — last checked 2026-05.
# If the model isn't in this table we still synthesize, just don't price.
_PRICING_PER_1M_CHARS: dict[str, float] = {
    "gpt-4o-mini-tts": 0.60,  # $0.60 per 1M input characters
    "tts-1": 15.00,
    "tts-1-hd": 30.00,
}

# Audio format -> approximate seconds of audio per byte. Used ONLY to
# estimate `duration_seconds` without parsing the mp3 header. The number
# is rough but consistent enough for UI purposes (e.g. "show a 3s
# loading bar"). For exact duration, parse the file with mutagen later.
#
# Empirically calibrated: 7-second gpt-4o-mini-tts mp3 = ~127 KB → ~18 KB/s.
# If you switch model or response_format, recalibrate by synthesizing a
# known-duration clip and checking len(bytes) / actual_seconds.
_BYTES_PER_SECOND_ESTIMATE: dict[str, int] = {
    "mp3": 18_000,  # gpt-4o-mini-tts default
    "opus": 18_000,
    "aac": 18_000,
    "flac": 80_000,
    "wav": 48_000,  # 16-bit, 24kHz, mono
    "pcm": 48_000,
}


class OpenAITTSClient:
    """Concrete `ITTSClient` backed by OpenAI's Audio API.

    Stateless — safe to reuse as a singleton.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        voice: str | None = None,
        response_format: str = "mp3",
        timeout: float = 60.0,
        max_retries: int = 3,
    ) -> None:
        self._model = model or settings.OPENAI_TTS_MODEL
        self._voice = voice or settings.OPENAI_TTS_VOICE
        self._format = response_format
        self._timeout = timeout
        self._max_retries = max_retries
        # AsyncOpenAI is the canonical async client. It handles connection
        # pooling internally so a singleton is fine.
        self._client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=timeout,
        )

    @property
    def model_name(self) -> str:
        """Public read-only access for cache-key construction."""
        return self._model

    @property
    def default_voice_id(self) -> str:
        """Public read-only access for cache-key construction."""
        return self._voice

    @property
    def response_format(self) -> str:
        """Public read-only access for storage/content-type decisions."""
        return self._format

    def estimate_duration_seconds(self, *, audio_bytes: bytes) -> float:
        """Estimate duration for provider audio already cached on disk."""
        return self._estimate_duration(audio_bytes)

    # ------------------------------------------------------------------
    # Public — synthesize plain text
    # ------------------------------------------------------------------
    async def synthesize(
        self,
        *,
        text: str,
        voice_id: str | None = None,
        speed: float = 1.0,
        style_instructions: str | None = None,
    ) -> SynthesizedAudio:
        """Generate audio bytes for `text`.

        Returns raw provider output only. The cache layer is
        responsible for persisting these bytes and turning them into a
        public URL.

        Args:
            text: What to speak. Non-empty, <= 2000 tokens (provider
                limit; ~6000-8000 chars in practice).
            voice_id: Override the configured default voice.
            speed: 0.25 .. 4.0 (provider limit). 1.0 = normal.
            style_instructions: gpt-4o-mini-tts only — guides delivery
                ("speak slowly and warmly", "sound like a patient teacher").
                Silently ignored on tts-1 / tts-1-hd.

        Raises:
            TTSValidationError: empty text, bad voice, bad speed.
            TTSAuthError: bad API key.
            TTSRateLimited: rate-limited after all retries.
            TTSTimeout: timed out after all retries.
            TTSProviderError: any other provider failure.
        """
        voice = voice_id or self._voice
        self._validate_inputs(text=text, voice=voice, speed=speed)

        kwargs: dict[str, Any] = {
            "model": self._model,
            "voice": voice,
            "input": text,
            "response_format": self._format,
            "speed": speed,
        }
        # `instructions` is gpt-4o-mini-tts-only. Sending it to tts-1 or
        # tts-1-hd raises an InvalidRequestError, so guard.
        if style_instructions and self._model == "gpt-4o-mini-tts":
            kwargs["instructions"] = style_instructions

        async with ai_provider_slot():
            audio_bytes = await self._call_with_retries(kwargs)

        result: SynthesizedAudio = {
            "audio_bytes": audio_bytes,
            "duration_seconds": self._estimate_duration(audio_bytes),
        }
        self._log_usage(text=text, audio_bytes=audio_bytes, voice=voice)
        return result

    # ------------------------------------------------------------------
    # Public — synthesize multi-voice dialogue (NOT YET SUPPORTED)
    # ------------------------------------------------------------------
    async def synthesize_dialogue(
        self,
        *,
        turns: list[DialogueTurn],
    ) -> SynthesizedAudio:
        """OpenAI TTS is single-voice per call. True multi-voice
        dialogue would need: synthesize each turn separately, then
        stitch the mp3s together (e.g. with ffmpeg or pydub).

        That's a Phase 2.5 feature — explicitly out of scope for now.
        Raising loudly so anyone calling this gets a clear message.
        """
        raise NotImplementedError(
            "Dialogue synthesis is not implemented in the OpenAI TTS "
            "client. Each OpenAI TTS call uses one voice. "
            "Implement this by calling synthesize() per turn and "
            "concatenating mp3s with ffmpeg/pydub, or switch to "
            "ElevenLabs for native multi-voice support."
        )

    # ------------------------------------------------------------------
    # Internal — input validation
    # ------------------------------------------------------------------
    def _validate_inputs(self, *, text: str, voice: str, speed: float) -> None:
        """Cheap pre-flight checks that catch caller bugs before we burn
        an API call. All raise TTSValidationError so the caller sees ONE
        error type for "you passed something wrong"."""
        if not text or not text.strip():
            raise TTSValidationError("text must be non-empty")
        if not (0.25 <= speed <= 4.0):
            raise TTSValidationError(f"speed must be in [0.25, 4.0], got {speed}")
        if (
            self._model == "gpt-4o-mini-tts"
            and voice not in _VALID_VOICES_GPT4O_MINI_TTS
        ):
            raise TTSValidationError(
                f"Voice {voice!r} is not supported by gpt-4o-mini-tts. "
                f"Supported: {sorted(_VALID_VOICES_GPT4O_MINI_TTS)}"
            )

    # ------------------------------------------------------------------
    # Internal — retry loop with exponential backoff
    # ------------------------------------------------------------------
    async def _call_with_retries(self, kwargs: dict[str, Any]) -> bytes:
        """Call the OpenAI audio.speech endpoint with manual retries.

        Uses `with_streaming_response.create(...)` (the recommended v2.x
        SDK pattern) instead of the legacy `.create(...).content`. The
        legacy path is deprecated in `openai>=2.x` and can hang in
        async contexts because the response body is never explicitly
        consumed. Streaming + `.read()` makes consumption explicit and
        works reliably across all SDK versions in our pinned range.

        Backoff: 1s, 2s, 4s + small random jitter.
        Validation/auth errors are re-raised IMMEDIATELY without retry.
        """
        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                async with self._client.audio.speech.with_streaming_response.create(
                    **kwargs
                ) as response:
                    # `.read()` pulls all chunks into one bytes object.
                    # For our use case (full-file caching) we never want
                    # to stream chunks individually — we just want the
                    # whole mp3 so we can hash + write it.
                    return await response.read()
            except (openai.AuthenticationError, openai.BadRequestError) as exc:
                # Don't retry caller bugs.
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
                # Exponential backoff: 1s, 2s, 4s with ±25% jitter
                delay = (2 ** (attempt - 1)) * (1 + random.uniform(-0.25, 0.25))
                logger.warning(
                    "tts_retry attempt=%d/%d delay=%.2fs err=%s",
                    attempt,
                    self._max_retries,
                    delay,
                    type(exc).__name__,
                )
                await asyncio.sleep(delay)
            except Exception as exc:
                # Anything else — wrap and propagate without retry.
                raise self._translate_exception(exc) from exc

        # Out of retries
        assert last_exc is not None  # for type checkers
        raise self._translate_exception(last_exc) from last_exc

    # ------------------------------------------------------------------
    # Internal — exception translation + logging
    # ------------------------------------------------------------------
    @staticmethod
    def _translate_exception(exc: Exception) -> TTSError:
        """Map provider exceptions into our TTSError family."""
        if isinstance(exc, openai.AuthenticationError):
            return TTSAuthError(f"OpenAI auth failed: {exc}")
        if isinstance(exc, openai.RateLimitError):
            return TTSRateLimited(f"OpenAI rate limit: {exc}")
        if isinstance(exc, openai.APITimeoutError):
            return TTSTimeout(f"OpenAI request timed out: {exc}")
        if isinstance(exc, openai.BadRequestError):
            # 400s are almost always our fault — bad voice, bad speed,
            # text too long. Surface as ValidationError.
            return TTSValidationError(f"OpenAI rejected request: {exc}")
        if isinstance(exc, openai.APIError):
            return TTSProviderError(f"OpenAI API error: {exc}")
        return TTSProviderError(f"Unexpected TTS failure: {exc}")

    def _estimate_duration(self, audio_bytes: bytes) -> float:
        """Rough estimate of duration. Not exact — parsing mp3 headers
        for exact length is overkill at this stage. Good enough for UI."""
        bytes_per_sec = _BYTES_PER_SECOND_ESTIMATE.get(self._format, 4000)
        return round(len(audio_bytes) / bytes_per_sec, 2)

    def _log_usage(self, *, text: str, audio_bytes: bytes, voice: str) -> None:
        """One log line per successful TTS call.

        OpenAI bills TTS by *character count* of the input, not tokens.
        We log chars + estimated cost so this lines up with the bill.
        """
        chars = len(text)
        rate_per_1m = _PRICING_PER_1M_CHARS.get(self._model)
        cost_usd = (
            round(chars * rate_per_1m / 1_000_000, 6)
            if rate_per_1m is not None
            else None
        )
        logger.info(
            "tts_usage %s",
            {
                "model": self._model,
                "voice": voice,
                "chars": chars,
                "bytes": len(audio_bytes),
                "cost_usd": cost_usd,
            },
        )


# ---------------------------------------------------------------------------
# Process-wide singleton (lazy)
# ---------------------------------------------------------------------------
_default_client: OpenAITTSClient | None = None


def get_default_tts_client() -> OpenAITTSClient:
    """Return the shared default OpenAI TTS client.

    Lazy so settings are read on first use, not at import time.
    """
    global _default_client
    if _default_client is None:
        _default_client = OpenAITTSClient()
    return _default_client
