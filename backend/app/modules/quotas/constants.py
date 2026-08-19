"""Usage quota metric and period identifiers."""

from enum import StrEnum


class QuotaMetric(StrEnum):
    COMPLETED_LESSONS = "completed_lessons"
    BLOB_WRITES = "blob_writes"
    SPEECH_MINUTES = "speech_minutes"
    TTS_CHARS = "tts_chars"
    LLM_TOKENS = "llm_tokens"
    IMAGE_GENS = "image_gens"


class QuotaPeriod(StrEnum):
    DAILY = "daily"
    MONTHLY = "monthly"
