"""Factory for wiring the production LLM-driven agents.

Routes call `build_default_agents()` and pass the trio to `SessionService`.
The underlying LLM clients are process-wide singletons (they are stateless
w.r.t. user data — see ``OpenAILLMClient``'s docstring); only the cheap
per-call ``LoggingLLMClient`` wrappers, which carry the per-agent
``agent_name``, are constructed per request. Tests bypass this entirely and
inject the Stub* agents.

`build_rag_services()` returns the RAG + mentor-note pair for production.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from app.ai.llm.interface import ILLMClient
from app.ai.llm.logging_client import LoggingLLMClient, record_usage
from app.ai.llm.openai_client import OpenAILLMClient
from app.ai.sessions.llm_evaluator import LLMEvaluator
from app.ai.sessions.llm_feedback import LLMFeedbackGenerator
from app.ai.sessions.llm_task_generator import LLMTaskGenerator
from app.core.config import settings
from app.modules.sessions.evaluator import Evaluator
from app.modules.sessions.feedback_generator import FeedbackGenerator
from app.modules.sessions.task_generator import TaskGenerator

if TYPE_CHECKING:
    from app.ai.eval.judge import FeedbackJudge, MentorNoteJudge


# We deliberately don't reuse `get_default_llm_client()` here: that singleton
# has no usage sink, and wiring `record_usage` into the low-level client
# module would pull request-logging/DB imports into it. The cached httpx/
# ChatOpenAI internals bind lazily on first use, so creating these at import
# time is safe under uvicorn's single event loop.


@lru_cache(maxsize=1)
def _shared_default_client() -> OpenAILLMClient:
    return OpenAILLMClient(usage_sink=record_usage)


@lru_cache(maxsize=1)
def _shared_taskgen_client() -> OpenAILLMClient:
    """Dedicated client for the task generator.

    Task generation runs on its own client (``OPENAI_TASKGEN_MODEL``, the cheap
    non-reasoning ``gpt-4o-mini`` default) separate from the interactive agents,
    so it can be retuned independently from .env. ``temperature`` is not passed
    and ``reasoning_effort`` is inert for a non-reasoning model — both only take
    effect if the model is swapped back to a reasoning one.
    """
    return OpenAILLMClient(
        model=settings.OPENAI_TASKGEN_MODEL,
        reasoning_effort=settings.OPENAI_TASKGEN_REASONING_EFFORT,
        usage_sink=record_usage,
    )


@lru_cache(maxsize=1)
def _shared_feedback_client() -> OpenAILLMClient:
    """Dedicated client for the feedback generator with a tight time budget.

    Feedback runs on the same fast ``OPENAI_CHAT_MODEL`` as the evaluator, but it
    must NOT inherit the shared client's 60s × 3 ≈ 180s retry budget — that blows
    past the frontend's 90s loading ceiling and strands the learner under an
    empty scorecard. We cap it at ``OPENAI_FEEDBACK_TIMEOUT_S`` ×
    (``OPENAI_FEEDBACK_MAX_RETRIES`` + 1) so the worst case is ~40s, and the
    service further wraps the call in ``asyncio.wait_for(FEEDBACK_TIMEOUT_S)``.
    """
    return OpenAILLMClient(
        timeout=settings.OPENAI_FEEDBACK_TIMEOUT_S,
        max_retries=settings.OPENAI_FEEDBACK_MAX_RETRIES,
        usage_sink=record_usage,
    )


@lru_cache(maxsize=1)
def _shared_judge_client() -> OpenAILLMClient:
    return OpenAILLMClient(
        model=settings.AI_EVAL_JUDGE_MODEL,
        # temperature is inert for reasoning models (gpt-5) — the client drops
        # it; effort is controlled by reasoning_effort instead. Kept at 0.0 so
        # a non-reasoning judge model would still score deterministically.
        temperature=0.0,
        reasoning_effort=settings.AI_EVAL_JUDGE_REASONING_EFFORT,
        usage_sink=record_usage,
    )


@lru_cache(maxsize=1)
def _shared_embedding_generator():
    # Imported lazily to keep module import light (mirrors build_rag_services).
    from app.ai.embeddings.embedding_generator import OpenAIEmbeddingGenerator

    return OpenAIEmbeddingGenerator()


def build_default_agents(
    *,
    llm: ILLMClient | None = None,
) -> tuple[Evaluator, FeedbackGenerator, TaskGenerator]:
    """Return (evaluator, feedback_generator, task_generator) wired to the LLM.

    Pass `llm` to override the default OpenAI client (mainly for tests
    or for swapping providers in environment-specific code paths).

    The evaluator and feedback generator share the fast default client; the task
    generator gets its OWN client (``_shared_taskgen_client``,
    ``OPENAI_TASKGEN_MODEL``) so it can be retuned independently from .env.
    Each collaborator wraps its client in a ``LoggingLLMClient`` tagged with its
    own ``agent_name`` so every call is recorded to ``ai_request_logs`` (see
    Part B Phase 1). When ``llm`` is overridden (tests), no wrapping happens —
    logging stays inert.
    """
    if llm is not None:
        return (
            LLMEvaluator(llm),
            LLMFeedbackGenerator(llm),
            LLMTaskGenerator(llm),
        )

    client = _shared_default_client()
    model = client.model
    taskgen_client = _shared_taskgen_client()
    feedback_client = _shared_feedback_client()
    return (
        LLMEvaluator(
            LoggingLLMClient(client, agent_name="session.evaluator", model=model)
        ),
        LLMFeedbackGenerator(
            LoggingLLMClient(
                feedback_client,
                agent_name="session.feedback",
                model=feedback_client.model,
            )
        ),
        LLMTaskGenerator(
            LoggingLLMClient(
                taskgen_client,
                agent_name="session.task_generator",
                model=taskgen_client.model,
            )
        ),
    )


def build_rag_services(
    *,
    llm: ILLMClient | None = None,
):
    """Return (FeedbackRAGService_class, MentorNoteGenerator) for production.

    The RAG service needs a DB session at construction time, so we return
    the class + a pre-built mentor generator. The route wires the DB in.
    """
    from app.modules.feedback_memory.mentor_note_generator import MentorNoteGenerator

    embedding_gen = _shared_embedding_generator()
    if llm is not None:
        mentor_gen = MentorNoteGenerator(llm)
    else:
        client = _shared_default_client()
        mentor_gen = MentorNoteGenerator(
            LoggingLLMClient(
                client, agent_name="feedback.mentor_note", model=client.model
            )
        )
    return embedding_gen, mentor_gen


def build_judge(*, llm: ILLMClient | None = None) -> FeedbackJudge:
    """Return the production quality judge (Part B Phase 2).

    Uses the ``AI_EVAL_JUDGE_MODEL`` (default ``gpt-4.1``) at temperature 0.0 to
    reduce self-preference bias and keep scoring deterministic. The judge's own
    client is wrapped in a
    ``LoggingLLMClient`` tagged ``judge.feedback`` so its cost/latency is logged
    and joins the feedback call on the shared ``trace_id``. Pass ``llm`` (tests)
    to bypass wrapping — logging stays inert.
    """
    # Imported lazily to avoid a circular import: judge.py → prompt_loader →
    # app.ai.agents → app.ai.sessions → factory.
    from app.ai.eval.judge import FeedbackJudge

    if llm is not None:
        return FeedbackJudge(llm)

    client = _shared_judge_client()
    return FeedbackJudge(
        LoggingLLMClient(client, agent_name="judge.feedback", model=client.model)
    )


def build_mentor_judge(*, llm: ILLMClient | None = None) -> MentorNoteJudge:
    """Return the production RAG mentor-note judge (Part B Phase 3).

    Same model + effort (``AI_EVAL_JUDGE_MODEL``) as ``build_judge``, but
    scores the Coach's Note against its *retrieved* RAG
    context and adds a ``faithfulness`` axis. Its client is wrapped in a
    ``LoggingLLMClient`` tagged ``judge.mentor_note`` so the judge's own cost
    joins the mentor-note call on the shared ``trace_id``. Pass ``llm`` (tests)
    to bypass wrapping — logging stays inert.
    """
    # Lazy import: judge.py → prompt_loader → app.ai.agents → app.ai.sessions.
    from app.ai.eval.judge import MentorNoteJudge

    if llm is not None:
        return MentorNoteJudge(llm)

    client = _shared_judge_client()
    return MentorNoteJudge(
        LoggingLLMClient(client, agent_name="judge.mentor_note", model=client.model)
    )
