"""Phase 1 (Part B) — operational AI request logging.

Covers the two new pieces:
  * ``LoggingLLMClient`` — writes one ai_request_logs row per call, carrying
    trace/user from the eval context and tokens from the usage sink; errors are
    logged + re-raised; disabled is a no-op.
  * ``OpenAILLMClient.generate_structured`` — recovers token usage via
    ``include_raw=True`` and forwards it to the usage sink.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (populate the mapper registry)
from app.ai.llm import logging_client as lc
from app.ai.llm.eval_context import reset_eval_context, set_eval_context
from app.ai.llm.exceptions import LLMValidationError
from app.ai.llm.logging_client import LoggingLLMClient, record_usage
from app.ai.llm.openai_client import OpenAILLMClient
from app.ai.llm.usage import UsageRecord
from app.core.database import Base
from app.modules.admin.models import AIRequestLog
from app.modules.auth.models import User


class _Out(BaseModel):
    value: int


@pytest.fixture()
def session_factory(monkeypatch):
    """In-memory SQLite bound into the logging client's SessionLocal."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[User.__table__, AIRequestLog.__table__])
    testing_session_local = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    monkeypatch.setattr(lc, "SessionLocal", testing_session_local)
    return testing_session_local


class _FakeInner:
    """Stand-in ILLMClient: optionally emits usage, optionally fails."""

    def __init__(self, *, fail: bool = False, emit_usage: bool = True) -> None:
        self.fail = fail
        self.emit_usage = emit_usage

    async def generate_structured(
        self, *, system_prompt, user_prompt, output_model, temperature=None
    ):
        if self.emit_usage:
            record_usage(
                UsageRecord(
                    model="gpt-4o-mini",
                    input_tokens=10,
                    output_tokens=5,
                    total_tokens=15,
                    cost_usd=0.001,
                )
            )
        if self.fail:
            raise RuntimeError("boom")
        return output_model(value=1)


@pytest.mark.asyncio
async def test_success_writes_one_row_with_context_and_usage(session_factory):
    token = set_eval_context(trace_id="trace-abc", user_id=42)
    try:
        client = LoggingLLMClient(
            _FakeInner(), agent_name="session.feedback", model="gpt-4o-mini"
        )
        result = await client.generate_structured(
            system_prompt="s", user_prompt="u", output_model=_Out
        )
    finally:
        reset_eval_context(token)

    assert isinstance(result, _Out)
    db = session_factory()
    try:
        rows = db.query(AIRequestLog).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.agent_name == "session.feedback"
        assert row.status == "success"
        assert row.trace_id == "trace-abc"
        assert row.user_id == 42
        assert row.input_tokens == 10
        assert row.output_tokens == 5
        assert row.latency_ms is not None and row.latency_ms >= 0
    finally:
        db.close()


@pytest.mark.asyncio
async def test_failure_writes_error_row_and_reraises(session_factory):
    client = LoggingLLMClient(
        _FakeInner(fail=True, emit_usage=False),
        agent_name="session.evaluator",
        model="gpt-4o-mini",
    )
    with pytest.raises(RuntimeError):
        await client.generate_structured(
            system_prompt="s", user_prompt="u", output_model=_Out
        )

    db = session_factory()
    try:
        rows = db.query(AIRequestLog).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.status == "error"
        assert row.agent_name == "session.evaluator"
        assert "boom" in (row.error_message or "")
        assert row.input_tokens is None
    finally:
        db.close()


@pytest.mark.asyncio
async def test_disabled_is_a_noop(session_factory, monkeypatch):
    monkeypatch.setattr(lc.settings, "AI_REQUEST_LOGGING_ENABLED", False)
    client = LoggingLLMClient(_FakeInner(), agent_name="x", model="gpt-4o-mini")
    result = await client.generate_structured(
        system_prompt="s", user_prompt="u", output_model=_Out
    )

    assert isinstance(result, _Out)
    db = session_factory()
    try:
        assert db.query(AIRequestLog).count() == 0
    finally:
        db.close()


# ── OpenAILLMClient.generate_structured: usage recovery via include_raw ──


class _FakeRaw:
    def __init__(self, meta: dict) -> None:
        self.usage_metadata = meta


class _FakeStructured:
    def __init__(self, result: dict) -> None:
        self._result = result

    async def ainvoke(self, _messages):
        return self._result


class _FakeChat:
    def __init__(self, result: dict) -> None:
        self._result = result

    def with_structured_output(self, _model, include_raw: bool = False):
        assert include_raw is True
        return _FakeStructured(self._result)


@pytest.mark.asyncio
async def test_generate_structured_forwards_usage_to_sink(monkeypatch):
    captured: list[UsageRecord] = []
    client = OpenAILLMClient(usage_sink=captured.append)
    out = _Out(value=7)
    result = {
        "raw": _FakeRaw({"input_tokens": 12, "output_tokens": 4, "total_tokens": 16}),
        "parsed": out,
        "parsing_error": None,
    }
    monkeypatch.setattr(
        client, "_maybe_rebind_temperature", lambda _t: _FakeChat(result)
    )

    parsed = await client.generate_structured(
        system_prompt="s", user_prompt="u", output_model=_Out, temperature=0.0
    )

    assert parsed is out
    assert len(captured) == 1
    assert captured[0].input_tokens == 12
    assert captured[0].output_tokens == 4


@pytest.mark.asyncio
async def test_generate_structured_raises_on_parsing_error(monkeypatch):
    client = OpenAILLMClient()
    result = {"raw": _FakeRaw({}), "parsed": None, "parsing_error": ValueError("bad")}
    monkeypatch.setattr(
        client, "_maybe_rebind_temperature", lambda _t: _FakeChat(result)
    )

    with pytest.raises(LLMValidationError):
        await client.generate_structured(
            system_prompt="s", user_prompt="u", output_model=_Out
        )


# ── factory client sharing ──────────────────────────────────────────


def test_build_default_agents_shares_one_inner_client():
    """Repeated factory calls must reuse the process-wide client singletons;
    only the cheap per-agent LoggingLLMClient wrappers are rebuilt.

    The evaluator rides the fast default client; feedback and the task generator
    each ride their OWN dedicated client (feedback for a tight time budget,
    task-gen for OPENAI_TASKGEN_MODEL), so neither shares the default inner
    client.
    """
    from app.ai.sessions import factory

    factory._shared_default_client.cache_clear()
    factory._shared_taskgen_client.cache_clear()
    factory._shared_feedback_client.cache_clear()
    try:
        eval_a, fb_a, gen_a = factory.build_default_agents()
        eval_b, fb_b, gen_b = factory.build_default_agents()

        inner_a = eval_a.llm._inner
        # The evaluator reuses the default inner client across calls.
        assert eval_b.llm._inner is inner_a
        # Feedback uses a SEPARATE (tight-budget) inner client, reused across calls.
        assert fb_a.llm._inner is not inner_a
        assert fb_a.llm._inner is fb_b.llm._inner
        assert fb_a.llm._inner is factory._shared_feedback_client()
        # The task generator uses a SEPARATE (reasoning-model) inner client.
        assert gen_a.llm._inner is not inner_a
        assert gen_a.llm._inner is gen_b.llm._inner
        assert gen_a.llm._inner is factory._shared_taskgen_client()
        # Wrappers stay per-call/per-agent so agent_name attribution holds.
        assert eval_a.llm is not eval_b.llm
        assert eval_a.llm._agent_name == "session.evaluator"
        assert fb_a.llm._agent_name == "session.feedback"
        assert gen_a.llm._agent_name == "session.task_generator"
    finally:
        factory._shared_default_client.cache_clear()
        factory._shared_feedback_client.cache_clear()
        factory._shared_taskgen_client.cache_clear()
