"""Unit tests for the Sentry integration (app.core.sentry).

These never hit the network: Sentry is disabled by default (empty DSN), and we
monkeypatch ``sentry_sdk`` to record calls instead of sending events.
"""

from __future__ import annotations

import app.core.sentry as sentry
from app.ai.llm.eval_context import reset_eval_context, set_eval_context
from app.ai.llm.exceptions import LLMTimeout
from app.core.config import settings


# ── _before_send filtering ────────────────────────────────────────────────


def _hint_for(exc: BaseException) -> dict:
    return {"exc_info": (type(exc), exc, exc.__traceback__)}


def test_before_send_drops_recoverable_exception():
    event = {"event_id": "abc"}
    assert sentry._before_send(event, _hint_for(LLMTimeout("slow"))) is None


def test_before_send_keeps_unexpected_exception():
    event = {"event_id": "abc"}
    assert sentry._before_send(event, _hint_for(RuntimeError("boom"))) is event


def test_before_send_keeps_event_without_exc_info():
    event = {"event_id": "abc"}
    assert sentry._before_send(event, {}) is event


def test_before_send_tags_bound_trace_id():
    event: dict = {"event_id": "abc"}
    token = set_eval_context(trace_id="trace-123", user_id=None)
    try:
        result = sentry._before_send(event, _hint_for(RuntimeError("boom")))
    finally:
        reset_eval_context(token)

    assert result is event
    assert event["tags"]["trace_id"] == "trace-123"


def test_before_send_noop_tag_without_trace_id():
    event: dict = {"event_id": "abc"}
    # No eval-context bound → no trace_id tag added.
    result = sentry._before_send(event, _hint_for(RuntimeError("boom")))

    assert result is event
    assert "tags" not in event


def test_before_send_does_not_overwrite_explicit_trace_id():
    event: dict = {"event_id": "abc", "tags": {"trace_id": "explicit"}}
    token = set_eval_context(trace_id="trace-123", user_id=None)
    try:
        sentry._before_send(event, _hint_for(RuntimeError("boom")))
    finally:
        reset_eval_context(token)

    assert event["tags"]["trace_id"] == "explicit"


# ── init_sentry ────────────────────────────────────────────────────────────


def test_init_sentry_noop_without_dsn(monkeypatch):
    calls: list = []
    monkeypatch.setattr(sentry.sentry_sdk, "init", lambda **kw: calls.append(kw))
    monkeypatch.setattr(settings, "sentry_dsn", "")

    sentry.init_sentry()

    assert calls == []


def test_init_sentry_noop_with_placeholder_dsn(monkeypatch):
    calls: list = []
    monkeypatch.setattr(sentry.sentry_sdk, "init", lambda **kw: calls.append(kw))
    monkeypatch.setattr(settings, "sentry_dsn", "replace-me")

    sentry.init_sentry()

    assert calls == []


def test_init_sentry_noop_with_invalid_dsn(monkeypatch):
    calls: list = []
    monkeypatch.setattr(sentry.sentry_sdk, "init", lambda **kw: calls.append(kw))
    monkeypatch.setattr(settings, "sentry_dsn", "not-a-valid-dsn")

    sentry.init_sentry()

    assert calls == []


def test_init_sentry_initialises_with_dsn(monkeypatch):
    calls: list = []
    monkeypatch.setattr(sentry.sentry_sdk, "init", lambda **kw: calls.append(kw))
    monkeypatch.setattr(settings, "sentry_dsn", "https://k@example.ingest.sentry.io/1")
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "sentry_traces_sample_rate", 0.25)

    sentry.init_sentry()

    assert len(calls) == 1
    kw = calls[0]
    assert kw["dsn"].endswith("/1")
    assert kw["environment"] == "production"
    assert kw["traces_sample_rate"] == 0.25
    assert kw["send_default_pii"] is False
    assert kw["before_send"] is sentry._before_send


# ── capture_to_sentry ──────────────────────────────────────────────────────


def test_capture_to_sentry_forwards_exception(monkeypatch):
    captured: list = []
    monkeypatch.setattr(
        sentry.sentry_sdk, "capture_exception", lambda exc: captured.append(exc)
    )

    err = ValueError("unexpected")
    sentry.capture_to_sentry(err)

    assert captured == [err]


def test_capture_to_sentry_uses_current_exception(monkeypatch):
    captured: list = []
    monkeypatch.setattr(
        sentry.sentry_sdk, "capture_exception", lambda exc: captured.append(exc)
    )

    try:
        raise KeyError("missing")
    except KeyError:
        sentry.capture_to_sentry()

    assert len(captured) == 1
    assert isinstance(captured[0], KeyError)


def test_capture_to_sentry_noop_without_exception(monkeypatch):
    captured: list = []
    monkeypatch.setattr(
        sentry.sentry_sdk, "capture_exception", lambda exc: captured.append(exc)
    )

    sentry.capture_to_sentry()  # called outside any except block

    assert captured == []


def test_capture_to_sentry_tags_trace_id(monkeypatch):
    tags: dict = {}

    class _Scope:
        def set_tag(self, key, value):
            tags[key] = value

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(sentry.sentry_sdk, "new_scope", lambda: _Scope())
    monkeypatch.setattr(sentry.sentry_sdk, "capture_exception", lambda exc: None)

    token = set_eval_context(trace_id="trace-xyz", user_id=None)
    try:
        sentry.capture_to_sentry(RuntimeError("boom"))
    finally:
        reset_eval_context(token)

    assert tags["trace_id"] == "trace-xyz"
