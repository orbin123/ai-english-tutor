"""Azure Speech implementation of IPronunciationClient.

Uses Azure Speech Pronunciation Assessment because it exposes word- and
phoneme-level accuracy signals that OpenAI / Whisper do not.

Important local-runtime note:
  - WAV works without extra system dependencies.
  - Compressed audio (mp3 / ogg / flac / mp4 / m4a) requires GStreamer,
    per Azure's Speech SDK docs. We validate that up front so callers
    get a clean 400 instead of a cryptic native-SDK failure.
"""

from __future__ import annotations

import asyncio
import logging
import random
import shutil
import tempfile
from pathlib import Path
from typing import Any

from app.ai.pronunciation.exceptions import (
    PronunciationAuthError,
    PronunciationDependencyError,
    PronunciationError,
    PronunciationProviderError,
    PronunciationRateLimited,
    PronunciationTimeout,
    PronunciationUnsupportedFormat,
    PronunciationValidationError,
)
from app.ai.pronunciation.interface import (
    PhonemeScore,
    PronunciationResult,
    WordScore,
)
from app.core.ai_concurrency import ai_provider_slot
from app.core.config import settings

logger = logging.getLogger(__name__)

_SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {
        "wav",
        "mp3",
        "ogg",
        "flac",
        "mp4",
        "m4a",
    }
)
_COMPRESSED_EXTENSIONS: frozenset[str] = frozenset(
    {
        "mp3",
        "ogg",
        "flac",
        "mp4",
        "m4a",
    }
)
_DEFAULT_LANGUAGE = "en-US"
_MAX_RETRIES = 3


def _load_speechsdk() -> Any:
    """Import Azure Speech SDK lazily so startup doesn't hard-fail."""
    try:
        import azure.cognitiveservices.speech as speechsdk
    except ImportError as exc:
        raise PronunciationDependencyError(
            "Azure Speech SDK is not installed. Add "
            "`azure-cognitiveservices-speech`, sync dependencies, and "
            "restart the backend."
        ) from exc
    return speechsdk


def _has_gstreamer() -> bool:
    """Return True when GStreamer is available for compressed input."""
    return (
        shutil.which("gst-launch-1.0") is not None
        or shutil.which("gst-inspect-1.0") is not None
    )


class AzurePronunciationClient:
    """Concrete IPronunciationClient backed by Azure Speech SDK."""

    def __init__(
        self,
        *,
        subscription_key: str | None = None,
        region: str | None = None,
        max_retries: int = _MAX_RETRIES,
    ) -> None:
        self._subscription_key = subscription_key or settings.AZURE_SPEECH_KEY
        self._region = region or settings.AZURE_SPEECH_REGION
        self._max_retries = max_retries

    async def score(
        self,
        *,
        audio_bytes: bytes,
        filename: str,
        reference_text: str,
        language: str = _DEFAULT_LANGUAGE,
    ) -> PronunciationResult:
        """Score one short scripted audio clip against reference text."""
        validated = self._validate_inputs(
            audio_bytes=audio_bytes,
            filename=filename,
            reference_text=reference_text,
            language=language,
        )
        async with ai_provider_slot():
            return await self._score_with_retries(
                audio_bytes=audio_bytes,
                filename=validated["filename"],
                reference_text=validated["reference_text"],
                language=validated["language"],
            )

    async def _score_with_retries(
        self,
        *,
        audio_bytes: bytes,
        filename: str,
        reference_text: str,
        language: str,
    ) -> PronunciationResult:
        """Retry transient Azure Speech failures with exponential backoff."""
        last_exc: PronunciationError | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                return await asyncio.to_thread(
                    self._score_sync,
                    audio_bytes=audio_bytes,
                    filename=filename,
                    reference_text=reference_text,
                    language=language,
                )
            except (
                PronunciationValidationError,
                PronunciationUnsupportedFormat,
                PronunciationAuthError,
                PronunciationDependencyError,
            ):
                raise
            except (
                PronunciationRateLimited,
                PronunciationTimeout,
                PronunciationProviderError,
            ) as exc:
                last_exc = exc
                if attempt == self._max_retries:
                    break
                delay = (2 ** (attempt - 1)) * (1 + random.uniform(-0.25, 0.25))
                logger.warning(
                    "pronunciation_retry attempt=%d/%d delay=%.2fs err=%s",
                    attempt,
                    self._max_retries,
                    delay,
                    type(exc).__name__,
                )
                await asyncio.sleep(delay)

        assert last_exc is not None
        raise last_exc

    def _score_sync(
        self,
        *,
        audio_bytes: bytes,
        filename: str,
        reference_text: str,
        language: str,
    ) -> PronunciationResult:
        """Run the blocking Azure Speech SDK call."""
        speechsdk = _load_speechsdk()
        self._ensure_configured()

        tmp_path = self._write_temp_audio(audio_bytes=audio_bytes, filename=filename)
        try:
            speech_config = speechsdk.SpeechConfig(
                subscription=self._subscription_key,
                region=self._region,
            )
            speech_config.speech_recognition_language = language

            audio_config = speechsdk.audio.AudioConfig(filename=str(tmp_path))
            recognizer = speechsdk.SpeechRecognizer(
                speech_config=speech_config,
                audio_config=audio_config,
            )

            assessment_config = speechsdk.PronunciationAssessmentConfig(
                reference_text=reference_text,
                grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
                granularity=speechsdk.PronunciationAssessmentGranularity.Phoneme,
                enable_miscue=True,
            )
            # Microsoft Learn documents these knobs on the Python SDK:
            # - `phoneme_alphabet` accepts "IPA"
            # - `enable_prosody_assessment()` enables prosody scoring
            assessment_config.phoneme_alphabet = "IPA"
            assessment_config.enable_prosody_assessment()
            assessment_config.apply_to(recognizer)

            result = recognizer.recognize_once()
        except PronunciationError:
            raise
        except Exception as exc:
            raise PronunciationProviderError(
                f"Azure Speech pronunciation assessment failed unexpectedly: {exc}"
            ) from exc
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                logger.warning("pronunciation_temp_cleanup_failed path=%s", tmp_path)

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            assessment = speechsdk.PronunciationAssessmentResult(result)
            return self._normalize_result(assessment)

        if result.reason == speechsdk.ResultReason.NoMatch:
            raise PronunciationValidationError(
                "No speech could be recognized from the uploaded audio."
            )

        if result.reason == speechsdk.ResultReason.Canceled:
            details = speechsdk.CancellationDetails(result)
            raise self._translate_cancellation(details, speechsdk)

        raise PronunciationProviderError(
            f"Unexpected Azure Speech result reason: {result.reason}"
        )

    def _ensure_configured(self) -> None:
        """Fail fast with a clear message when Azure creds are missing."""
        if self._subscription_key and self._region:
            return
        raise PronunciationAuthError(
            "Azure Speech is not configured. Set AZURE_SPEECH_KEY and "
            "AZURE_SPEECH_REGION, then restart the backend."
        )

    def _validate_inputs(
        self,
        *,
        audio_bytes: bytes,
        filename: str,
        reference_text: str,
        language: str,
    ) -> dict[str, str]:
        """Pre-flight validation that catches caller issues early."""
        if not audio_bytes:
            raise PronunciationValidationError("audio_bytes must be non-empty")

        cleaned_reference = reference_text.strip()
        if not cleaned_reference:
            raise PronunciationValidationError("reference_text must be non-empty")

        cleaned_language = language.strip() or _DEFAULT_LANGUAGE

        suffix = Path(filename or "").suffix.lower()
        if not suffix:
            raise PronunciationValidationError(
                "filename must include an extension like '.wav' or '.mp3'"
            )

        extension = suffix.lstrip(".")
        if extension == "webm":
            raise PronunciationUnsupportedFormat(
                "WebM input is not supported by this Azure pronunciation "
                "integration yet. Upload a short WAV clip for now."
            )

        if extension not in _SUPPORTED_EXTENSIONS:
            raise PronunciationUnsupportedFormat(
                f"Unsupported pronunciation-audio format: .{extension}. "
                f"Supported: {sorted(_SUPPORTED_EXTENSIONS)}"
            )

        if extension in _COMPRESSED_EXTENSIONS and not _has_gstreamer():
            raise PronunciationUnsupportedFormat(
                "Compressed pronunciation-audio input requires GStreamer on "
                "the server for Azure Speech SDK decoding. Upload WAV for "
                "now, or install GStreamer first."
            )

        return {
            "filename": filename,
            "reference_text": cleaned_reference,
            "language": cleaned_language,
        }

    @staticmethod
    def _write_temp_audio(*, audio_bytes: bytes, filename: str) -> Path:
        """Persist uploaded bytes to a temp file for Azure's file input."""
        suffix = Path(filename).suffix or ".wav"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(audio_bytes)
            return Path(tmp.name)

    @staticmethod
    def _translate_cancellation(details: Any, speechsdk: Any) -> PronunciationError:
        """Map Azure cancellation details into our exception family."""
        error_code = getattr(details, "code", None)
        error_details = (getattr(details, "error_details", "") or "").strip()

        if error_code == speechsdk.CancellationErrorCode.AuthenticationFailure:
            return PronunciationAuthError(
                f"Azure Speech auth failed: {error_details or error_code}"
            )
        if error_code == speechsdk.CancellationErrorCode.Forbidden:
            return PronunciationAuthError(
                f"Azure Speech rejected the request: {error_details or error_code}"
            )
        if error_code == speechsdk.CancellationErrorCode.TooManyRequests:
            return PronunciationRateLimited(
                f"Azure Speech rate limit: {error_details or error_code}"
            )
        if error_code == speechsdk.CancellationErrorCode.ServiceTimeout:
            return PronunciationTimeout(
                f"Azure Speech timed out: {error_details or error_code}"
            )
        if error_code == speechsdk.CancellationErrorCode.BadRequest:
            return PronunciationValidationError(
                f"Azure Speech rejected the pronunciation request: "
                f"{error_details or error_code}"
            )

        return PronunciationProviderError(
            f"Azure Speech canceled pronunciation assessment: "
            f"{error_details or error_code or details}"
        )

    def _normalize_result(self, assessment: Any) -> PronunciationResult:
        """Translate the SDK object into our TypedDict contract."""
        words: list[WordScore] = []
        for word in getattr(assessment, "words", None) or []:
            phonemes: list[PhonemeScore] = [
                PhonemeScore(
                    phoneme=str(getattr(phoneme, "phoneme", "") or ""),
                    accuracy_score=round(
                        float(getattr(phoneme, "accuracy_score", 0.0) or 0.0), 2
                    ),
                )
                for phoneme in (getattr(word, "phonemes", None) or [])
            ]
            words.append(
                WordScore(
                    word=str(getattr(word, "word", "") or ""),
                    accuracy_score=round(
                        float(getattr(word, "accuracy_score", 0.0) or 0.0), 2
                    ),
                    error_type=self._normalize_error_type(
                        getattr(word, "error_type", None)
                    ),
                    phonemes=phonemes,
                )
            )

        return PronunciationResult(
            overall_score=round(
                float(getattr(assessment, "pronunciation_score", 0.0) or 0.0), 2
            ),
            accuracy_score=round(
                float(getattr(assessment, "accuracy_score", 0.0) or 0.0), 2
            ),
            fluency_score=round(
                float(getattr(assessment, "fluency_score", 0.0) or 0.0), 2
            ),
            completeness_score=round(
                float(getattr(assessment, "completeness_score", 0.0) or 0.0), 2
            ),
            prosody_score=round(
                float(getattr(assessment, "prosody_score", 0.0) or 0.0), 2
            ),
            words=words,
        )

    @staticmethod
    def _normalize_error_type(value: Any) -> str | None:
        """Normalize Azure word error types into simple lowercase strings."""
        if value is None:
            return None

        name = getattr(value, "name", None)
        text = str(name or value).strip()
        if "." in text:
            text = text.rsplit(".", 1)[-1]
        lowered = text.lower()
        if lowered in {"", "none", "noerror"}:
            return None
        return lowered


_default_client: AzurePronunciationClient | None = None


def get_default_pronunciation_client() -> AzurePronunciationClient:
    """Return the shared default Azure pronunciation client."""
    global _default_client
    if _default_client is None:
        _default_client = AzurePronunciationClient()
    return _default_client


def _reset_default_pronunciation_client() -> None:
    """Test-only: drop the cached client so the next get_*() rebuilds."""
    global _default_client
    _default_client = None
