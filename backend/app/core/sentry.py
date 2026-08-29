"""Sentry error-tracking integration.

Logging tells us what we *chose* to record; Sentry surfaces the unexpected
exceptions — full stack trace, request context, grouped by fingerprint. This
module owns three things so ``main.py`` stays thin and the filtering logic is
unit-testable:

* :func:`init_sentry` — one-time SDK init, a no-op when ``SENTRY_DSN`` is empty
  (the local/test default), so dev and CI are untouched unless a DSN is set.
* :func:`_before_send` — drops the *expected/recoverable* LLM/TTS/STT/etc.
  errors (timeouts, rate-limits, validation) so the dashboard only shows
  genuine surprises, not the failures we already catch and retry.
* :func:`capture_to_sentry` — for workers that intentionally swallow an
  exception with a warning log: the existing log line stays, and this adds one
  call that forwards the exception to Sentry tagged with the request
  ``trace_id`` so the event links back to the structured logs.

The ``trace_id`` is the same id ``app.ai.llm.eval_context`` already stamps on
every structured log and ``AIRequestLog`` row, so a Sentry event joins the same
correlation timeline.
"""

from __future__ import annotations

import logging
import sys
from urllib.parse import urlsplit

import sentry_sdk
from sentry_sdk.types import Event, Hint

from app.ai.imagegen.exceptions import (
    ImageGenRateLimited,
    ImageGenTimeout,
    ImageGenValidationError,
)
from app.ai.llm.eval_context import get_eval_context
from app.ai.llm.exceptions import LLMRateLimited, LLMTimeout, LLMValidationError
from app.ai.pronunciation.exceptions import (
    PronunciationRateLimited,
    PronunciationTimeout,
    PronunciationValidationError,
)
from app.ai.stt.exceptions import STTPayloadTooLarge, STTRateLimited, STTTimeout
from app.ai.tts.exceptions import TTSRateLimited, TTSTimeout
from app.core.config import settings

logger = logging.getLogger(__name__)

# Common .env placeholder values — treated as "disabled", not real DSNs.
_PLACEHOLDER_DSNS = frozenset(
    {"replace-me", "<sentry-dsn>", "changeme", "none", "false", "disabled"}
)

# Expected/recoverable failures we already catch and retry. Reporting these to
# Sentry would be noise — they are normal operating conditions, not bugs.
RECOVERABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    LLMTimeout,
    LLMRateLimited,
    LLMValidationError,
    TTSTimeout,
    TTSRateLimited,
    STTTimeout,
    STTRateLimited,
    STTPayloadTooLarge,
    PronunciationTimeout,
    PronunciationRateLimited,
    PronunciationValidationError,
    ImageGenTimeout,
    ImageGenRateLimited,
    ImageGenValidationError,
)


def _before_send(event: Event, hint: Hint) -> Event | None:
    """Drop expected/recoverable exceptions; tag everything else with ``trace_id``.

    Sentry passes the live exception in ``hint["exc_info"]`` (a standard
    ``(type, value, traceback)`` tuple). We inspect the value rather than the
    serialized ``event`` so the check is a plain ``isinstance``.

    Before returning, we stamp the request-scoped ``trace_id`` onto the event's
    tags. ``before_send`` runs at capture time, still inside the request's
    contextvar scope, so this correlates **both** auto-captured unhandled 500s
    (the real prod bugs) and explicit :func:`capture_to_sentry` calls back to the
    same id used by the structured logs / ``AIRequestLog`` — i.e. CloudWatch.
    ``setdefault`` never overwrites a tag a call set explicitly; a no-op when no
    trace_id is bound.
    """

    exc_info = hint.get("exc_info")
    if exc_info:
        exc = exc_info[1]
        if isinstance(exc, RECOVERABLE_EXCEPTIONS):
            return None

    trace_id = get_eval_context().trace_id
    if trace_id:
        tags = event.setdefault("tags", {})
        tags.setdefault("trace_id", trace_id)
    return event


def _sentry_dsn_is_configured(dsn: str) -> bool:
    """Return True only for a non-empty, non-placeholder DSN Sentry can parse."""

    dsn = dsn.strip()
    if not dsn or dsn.lower() in _PLACEHOLDER_DSNS:
        return False
    parts = urlsplit(dsn)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def init_sentry() -> None:
    """Initialise Sentry once at startup. No-op when no DSN is configured."""

    if not _sentry_dsn_is_configured(settings.sentry_dsn):
        if settings.sentry_dsn.strip():
            logger.warning(
                "SENTRY_DSN is set but invalid or a placeholder — Sentry disabled"
            )
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,  # never ship learner data to a third party
        before_send=_before_send,
    )


def capture_to_sentry(exc: BaseException | None = None) -> None:
    """Forward a swallowed exception to Sentry, tagged with the request ``trace_id``.

    Call this inside an ``except`` block at a site that intentionally
    logs-and-continues — *in addition to* the existing warning log, not as a
    replacement. When ``exc`` is omitted the currently-handled exception is used
    (``sys.exc_info``), so it works whether or not the handler bound an
    ``as exc`` name and regardless of the logger style at the call site.

    The ``trace_id`` is set on a forked scope so it tags only this event, never
    leaking into other concurrently-handled requests. Everything here is a
    harmless no-op when the SDK was never initialised (empty DSN).
    """

    if exc is None:
        exc = sys.exc_info()[1]
    if exc is None:
        return

    trace_id = get_eval_context().trace_id
    with sentry_sdk.new_scope() as scope:
        if trace_id:
            scope.set_tag("trace_id", trace_id)
        sentry_sdk.capture_exception(exc)
