"""OpenAI implementation of ISTTClient.

Uses the `whisper-1` model because it's the ONLY OpenAI STT model
that supports word-level timestamps — gpt-4o-transcribe and
gpt-4o-mini-transcribe only return plain text. For a tutor app that
will eventually score fluency (pacing, pauses, run-ons), word
timestamps are not optional.

Notes on the SDK call:

1. Unlike TTS, the STT endpoint returns a **typed Pydantic object**,
   not a streaming binary response. So no `with_streaming_response`
   needed — `await client.audio.transcriptions.create(...)` returns
   a `Transcription` (or `TranscriptionVerbose`) object directly.

2. The SDK requires the file argument to be a tuple
   `(filename, bytes_or_file_obj, content_type)` so it can construct
   the multipart form. Passing only bytes silently fails because the
   SDK can't infer the audio format.

3. Streaming responses are explicitly NOT supported by whisper-1 (the
   docs say streaming is ignored). Don't bother.

4. We use `response_format="json"` for plain transcription and
   `response_format="verbose_json"` + `timestamp_granularities=["word"]`
   for the timestamped path. Both return Pydantic objects; we normalise
   them to our `TranscriptionResult` TypedDict at the boundary.

5. Pricing: whisper-1 bills per second of audio at $0.006/min. We log
   estimated cost based on the duration the API returns.
"""

from __future__ import annotations

import asyncio
import io
import logging
import random
from typing import Any

import openai
from openai import AsyncOpenAI

from app.ai.stt.exceptions import (
    STTAuthError,
    STTError,
    STTPayloadTooLarge,
    STTProviderError,
    STTRateLimited,
    STTTimeout,
    STTValidationError,
)
from app.ai.stt.interface import TranscriptionResult, WordTimestamp
from app.core.ai_concurrency import ai_provider_slot
from app.core.config import settings

logger = logging.getLogger(__name__)


# whisper-1 pricing: $0.006 per minute of audio.
# https://openai.com/api/pricing/  (last checked 2026-05)
_WHISPER_COST_PER_MINUTE_USD = 0.006

# Audio formats whisper-1 accepts. We don't enforce these in this layer
# (the SDK will reject unsupported formats at the API boundary), but
# we keep the list as documentation + for future pre-flight validation.
_SUPPORTED_AUDIO_FORMATS: frozenset[str] = frozenset(
    {
        "flac",
        "m4a",
        "mp3",
        "mp4",
        "mpeg",
        "mpga",
        "oga",
        "ogg",
        "wav",
        "webm",
    }
)


class OpenAISTTClient:
    """Concrete `ISTTClient` backed by OpenAI's Whisper API.

    Stateless — safe to reuse as a singleton.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        timeout: float = 120.0,  # transcription can take a while for long audio
        max_retries: int = 3,
    ) -> None:
        self._model = model or settings.OPENAI_STT_MODEL
        self._timeout = timeout
        self._max_retries = max_retries
        self._client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=timeout,
        )

    # ------------------------------------------------------------------
    # Public — transcribe (single method, handles both modes)
    # ------------------------------------------------------------------
    async def transcribe(
        self,
        *,
        audio_bytes: bytes,
        filename: str,
        language: str = "en",
        with_timestamps: bool = False,
    ) -> TranscriptionResult:
        """Transcribe audio bytes via Whisper. See ISTTClient docstring."""
        self._validate_inputs(audio_bytes=audio_bytes, filename=filename)

        # Build the multipart "file" tuple. The filename's extension is
        # how OpenAI detects the audio format — passing raw bytes alone
        # fails. We default the content_type to None and let httpx infer
        # it from the extension, which the SDK does correctly.
        file_arg = (filename, io.BytesIO(audio_bytes))

        kwargs: dict[str, Any] = {
            "model": self._model,
            "file": file_arg,
            "language": language,
        }

        if with_timestamps:
            # `verbose_json` is required to get the `duration` field +
            # the `words` array. `timestamp_granularities=["word"]` is a
            # LIST, not a string — the API treats it as a multi-value
            # form field.
            kwargs["response_format"] = "verbose_json"
            kwargs["timestamp_granularities"] = ["word"]
        else:
            # Even without word timestamps, we use `verbose_json` so the
            # response includes a real `duration` field. Without it, we'd
            # have to estimate duration from byte size, which is wildly
            # wrong for different audio formats (mp3 vs webm vs wav each
            # have different bytes/sec). One extra small JSON field is
            # worth not lying about duration in our response.
            kwargs["response_format"] = "verbose_json"

        async with ai_provider_slot():
            raw = await self._call_with_retries(kwargs)
        result = self._normalize_response(
            raw=raw,
            audio_bytes=audio_bytes,
            with_timestamps=with_timestamps,
        )
        self._log_usage(
            duration_seconds=result["duration_seconds"],
            chars=len(result["text"]),
            with_timestamps=with_timestamps,
        )
        return result

    # ------------------------------------------------------------------
    # Internal — input validation
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_inputs(*, audio_bytes: bytes, filename: str) -> None:
        """Pre-flight checks. All raise STTValidationError or its
        STTPayloadTooLarge subclass."""
        if not audio_bytes:
            raise STTValidationError("audio_bytes must be non-empty")
        if len(audio_bytes) > settings.MAX_AUDIO_UPLOAD_BYTES:
            raise STTPayloadTooLarge(
                f"Audio is {len(audio_bytes):,} bytes; "
                f"the application limit is {settings.MAX_AUDIO_UPLOAD_BYTES:,} "
                "bytes (5 MiB). Record a shorter clip before transcribing."
            )
        if not filename or "." not in filename:
            raise STTValidationError(
                f"filename must include an extension so the provider can "
                f"detect the audio format (e.g. 'recording.webm'). Got: {filename!r}"
            )

    # ------------------------------------------------------------------
    # Internal — retry loop
    # ------------------------------------------------------------------
    async def _call_with_retries(self, kwargs: dict[str, Any]) -> Any:
        """Call audio.transcriptions.create with manual retries.

        Same retry shape as the TTS client: 1s, 2s, 4s with ±25% jitter
        on transient failures (rate limit, timeout, 5xx). Caller bugs
        (auth, bad request) are re-raised immediately.
        """
        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                # IMPORTANT: each attempt rebuilds the BytesIO inside the
                # `file` tuple isn't enough on its own — once httpx reads
                # the stream, it's consumed. We rewind here so retries
                # don't send 0 bytes.
                self._rewind_file_arg(kwargs)
                return await self._client.audio.transcriptions.create(**kwargs)
            except (openai.AuthenticationError, openai.BadRequestError) as exc:
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
                    "stt_retry attempt=%d/%d delay=%.2fs err=%s",
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
    def _rewind_file_arg(kwargs: dict[str, Any]) -> None:
        """Reset the BytesIO pointer in the `file` tuple so retries can
        re-send the same bytes. If the stream has been consumed and not
        rewound, the next attempt sends an empty body and 400s.
        """
        file_arg = kwargs.get("file")
        if isinstance(file_arg, tuple) and len(file_arg) >= 2:
            stream = file_arg[1]
            if isinstance(stream, io.IOBase):
                try:
                    stream.seek(0)
                except (OSError, ValueError):
                    # Some streams aren't seekable; nothing we can do.
                    pass

    # ------------------------------------------------------------------
    # Internal — response normalization
    # ------------------------------------------------------------------
    def _normalize_response(
        self,
        *,
        raw: Any,
        audio_bytes: bytes,
        with_timestamps: bool,
    ) -> TranscriptionResult:
        """Translate the SDK's typed response into our TypedDict.

        Both modes use `verbose_json`, so we always have access to
        `text`, `language`, and `duration` from the response. The only
        difference is whether we asked for the `words` array.

        Note: `audio_bytes` is unused now — kept in the signature so
        future fallback paths (e.g. switching to plain JSON for cost)
        can re-introduce the byte-size estimate if needed.
        """
        text = (getattr(raw, "text", "") or "").strip()
        duration = float(getattr(raw, "duration", 0.0) or 0.0)
        language = getattr(raw, "language", "en") or "en"

        if with_timestamps:
            raw_words = getattr(raw, "words", None) or []
            words: list[WordTimestamp] | None = [
                WordTimestamp(
                    word=getattr(w, "word", ""),
                    start_seconds=float(getattr(w, "start", 0.0) or 0.0),
                    end_seconds=float(getattr(w, "end", 0.0) or 0.0),
                    # whisper-1 doesn't expose per-word confidence
                    confidence=None,
                )
                for w in raw_words
            ]
        else:
            words = None

        return TranscriptionResult(
            text=text,
            language=language,
            duration_seconds=round(duration, 2),
            words=words,
        )

    # ------------------------------------------------------------------
    # Internal — exception translation + logging
    # ------------------------------------------------------------------
    @staticmethod
    def _translate_exception(exc: Exception) -> STTError:
        """Map provider exceptions into our STTError family."""
        if isinstance(exc, openai.AuthenticationError):
            return STTAuthError(f"OpenAI auth failed: {exc}")
        if isinstance(exc, openai.RateLimitError):
            return STTRateLimited(f"OpenAI rate limit: {exc}")
        if isinstance(exc, openai.APITimeoutError):
            return STTTimeout(f"OpenAI request timed out: {exc}")
        if isinstance(exc, openai.BadRequestError):
            # 400s are usually our fault — bad format, bad params.
            return STTValidationError(f"OpenAI rejected request: {exc}")
        if isinstance(exc, openai.APIError):
            return STTProviderError(f"OpenAI API error: {exc}")
        return STTProviderError(f"Unexpected STT failure: {exc}")

    def _log_usage(
        self, *, duration_seconds: float, chars: int, with_timestamps: bool
    ) -> None:
        """One log line per successful STT call.

        Whisper bills by minute of audio. Cost is rough because we may
        be using estimated duration on plain-JSON calls.
        """
        cost_usd = round((duration_seconds / 60.0) * _WHISPER_COST_PER_MINUTE_USD, 6)
        logger.info(
            "stt_usage %s",
            {
                "model": self._model,
                "duration_seconds": duration_seconds,
                "transcript_chars": chars,
                "with_timestamps": with_timestamps,
                "cost_usd": cost_usd,
            },
        )


# ---------------------------------------------------------------------------
# Process-wide singleton (lazy)
# ---------------------------------------------------------------------------
_default_client: OpenAISTTClient | None = None


def get_default_stt_client() -> OpenAISTTClient:
    """Return the shared default OpenAI STT client.

    Lazy so settings are read on first use, not at import time.
    """
    global _default_client
    if _default_client is None:
        _default_client = OpenAISTTClient()
    return _default_client


def _reset_default_stt_client() -> None:
    """Test-only: drop the cached client so the next get_*() rebuilds."""
    global _default_client
    _default_client = None
