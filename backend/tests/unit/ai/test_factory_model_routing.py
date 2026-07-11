"""Phase 2 — per-agent model routing in the sessions factory.

Task generation rides its OWN client (``OPENAI_TASKGEN_MODEL``, the cheap
``gpt-4o-mini`` default); feedback rides its OWN client too (same
``OPENAI_CHAT_MODEL`` as the evaluator but a tight ``OPENAI_FEEDBACK_TIMEOUT_S``
× ``OPENAI_FEEDBACK_MAX_RETRIES`` budget so a slow generation can't strand the
learner); the evaluator keeps the shared interactive default. These tests pin
that wiring so a future config change can't silently collapse them together.
"""

from __future__ import annotations

from app.ai.sessions import factory
from app.core.config import Settings, settings


def test_taskgen_config_defaults() -> None:
    """The committed defaults keep task generation on the cheap non-reasoning
    gpt-4o-mini and the interactive agents on gpt-4.1-mini — independent of any
    local .env override (asserted against the class field defaults)."""
    fields = Settings.model_fields
    assert fields["OPENAI_TASKGEN_MODEL"].default == "gpt-4o-mini"
    assert fields["OPENAI_CHAT_MODEL"].default == "gpt-4.1-mini"


def test_task_generator_uses_dedicated_client() -> None:
    """build_default_agents wires the task generator and the feedback generator
    to their own clients, leaving the evaluator on the shared interactive
    default."""
    factory._shared_default_client.cache_clear()
    factory._shared_taskgen_client.cache_clear()
    factory._shared_feedback_client.cache_clear()
    try:
        evaluator, feedback, task_gen = factory.build_default_agents()

        gen_inner = task_gen.llm._inner
        eval_inner = evaluator.llm._inner
        fb_inner = feedback.llm._inner

        # Task generator: dedicated client on the configured task-gen model.
        assert gen_inner.model == settings.OPENAI_TASKGEN_MODEL
        # Only a reasoning task-gen model carries the effort knob; the default
        # gpt-4o-mini is non-reasoning, so this branch is skipped for it.
        if gen_inner._is_reasoning:
            assert (
                gen_inner._reasoning_effort == settings.OPENAI_TASKGEN_REASONING_EFFORT
            )

        # Evaluator: the shared fast interactive default client.
        assert eval_inner.model == settings.OPENAI_CHAT_MODEL

        # Feedback: its OWN client — same interactive model, but a deliberately
        # tight time budget so a slow generation can't strand the learner.
        assert fb_inner is not eval_inner
        assert fb_inner.model == settings.OPENAI_CHAT_MODEL
        assert fb_inner._timeout == settings.OPENAI_FEEDBACK_TIMEOUT_S
        assert fb_inner._max_retries == settings.OPENAI_FEEDBACK_MAX_RETRIES

        # Neither task-gen nor feedback rides the interactive evaluator client.
        assert gen_inner is not eval_inner
        assert gen_inner is not fb_inner
    finally:
        factory._shared_default_client.cache_clear()
        factory._shared_taskgen_client.cache_clear()
        factory._shared_feedback_client.cache_clear()
