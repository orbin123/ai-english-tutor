"""Speech-to-Text client contract.

Implementation: OpenAI Whisper API (whisper-1).

Used by all speak_* task types: storyboard_narration,
retell_what_you_heard, and any future free-form speaking task.

Why one interface instead of two methods?
The same Whisper call handles both modes — the only difference is
whether `with_timestamps=True` flips the response_format from `json`
to `verbose_json`. Hiding that behind one method keeps callers simple
and lets a future provider (e.g. local Whisper, Deepgram) drop in
without changing call sites.
"""

from __future__ import annotations

from typing import Protocol

from typing_extensions import TypedDict


class WordTimestamp(TypedDict):
    """One transcribed word with its time bounds.

    Word-level timestamps power fluency analysis (pauses, speed,
    self-corrections) without a separate model.

    Note: Whisper-1 does not return per-word confidence scores.
    The `confidence` field is reserved for providers that do
    (e.g. Deepgram, AssemblyAI) — for whisper-1 it's always None.
    """

    word: str
    start_seconds: float
    end_seconds: float
    confidence: float | None


class TranscriptionResult(TypedDict):
    """Full STT output.

    `words` is None when timestamps weren't requested (cheaper + faster
    response). When requested, it's the full list of word timings.
    """

    text: str
    language: str
    duration_seconds: float
    words: list[WordTimestamp] | None


class ISTTClient(Protocol):
    """Minimal STT contract.

    A single method handles both plain and timestamped transcription —
    callers pass `with_timestamps=True` when they need word timings.
    """

    async def transcribe(
        self,
        *,
        audio_bytes: bytes,
        filename: str,
        language: str = "en",
        with_timestamps: bool = False,
    ) -> TranscriptionResult:
        """Transcribe audio bytes. Optionally include word timestamps.

        Args:
            audio_bytes: Raw audio bytes. Must fit the configured application
                upload limit (5 MiB by default).
            filename: A name like "recording.webm". The extension is what
                providers use to detect the audio format — bytes alone
                are not enough. Anything sensible works (e.g. "audio.mp3").
            language: ISO-639-1 code, default "en". Setting this avoids
                language mis-detection on short / noisy audio.
            with_timestamps: When True, returns word-level timing data
                in `result["words"]`. When False, that field is None.

        Returns:
            TranscriptionResult dict.

        Raises:
            STTValidationError: empty bytes, bad filename, oversized.
            STTPayloadTooLarge: audio over the application limit.
            STTAuthError: bad API key.
            STTRateLimited: rate-limited after all retries.
            STTTimeout: timed out after all retries.
            STTProviderError: any other provider failure.
        """
        ...
