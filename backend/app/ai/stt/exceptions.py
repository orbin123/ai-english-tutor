"""STT client exceptions.

Same pattern as the LLM and TTS exception families: callers catch ONE
base class (`STTError`) instead of N provider-specific exception types.
"""


class STTError(Exception):
    """Base class for any STT call failure."""


class STTTimeout(STTError):
    """Provider took too long. Usually safe to retry."""


class STTRateLimited(STTError):
    """Provider rate-limited us. Back off + retry."""


class STTAuthError(STTError):
    """Bad / missing API key. NOT retryable — fix config."""


class STTProviderError(STTError):
    """Catch-all for any other provider-side failure (5xx, malformed
    response, etc). Treated as transient by the retry policy."""


class STTValidationError(STTError):
    """Caller passed invalid input (empty audio, file too large,
    unsupported format).

    Not provider-side — caller bug, never retried.
    """


class STTPayloadTooLarge(STTValidationError):
    """Audio exceeds the application's configured upload limit.

    Surfaced as 413 by routes. Subclass of STTValidationError so callers
    that catch the broader type still handle it; specific catchers can
    differentiate to give a clearer error message.
    """
