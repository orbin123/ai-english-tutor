"""Feedback generator interface + Phase 3 deterministic stub.

The interface is what `SessionService` depends on; Phase 4 swaps in the
LLM-driven Feedback Agent. The output shape is fixed (matches spec §14) so
the wiring doesn't change when the implementation does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.modules.sessions.evaluator import EvaluationResult
from app.scoring import ArchetypeSpec


@dataclass(frozen=True)
class MistakeOut:
    issue: str
    user_wrote: str | None = None
    correction: str | None = None
    rule: str | None = None
    sub_skills_affected: tuple[str, ...] = ()


@dataclass(frozen=True)
class FeedbackResult:
    score: int  # 0..10, rounded raw_score
    summary: str
    did_well: tuple[str, ...] = ()
    mistakes: tuple[MistakeOut, ...] = ()
    next_tip: str | None = None
    sub_skill_breakdown: dict[str, int] = field(default_factory=dict)
    # True when this is a degraded placeholder (LLM error / timeout) rather than
    # real generated feedback. Drives the UI's "Regenerate feedback" affordance,
    # which is shown ONLY on a fallback card. Not persisted as a DB column — it
    # rides the WS/JSON feedback payload.
    fallback: bool = False


class FeedbackGenerator(Protocol):
    """Turn an EvaluationResult into structured, user-facing feedback.

    Async because production implementations call out to an LLM (Phase 4+).
    """

    async def generate(
        self,
        *,
        archetype: ArchetypeSpec,
        evaluation: EvaluationResult,
        user_response: dict | None,
        task_content: dict | None = None,
        feedback_overrides: dict | None = None,
        learner_history: str | None = None,
    ) -> FeedbackResult: ...


class StubFeedbackGenerator:
    """Deterministic feedback. Used in tests and as offline fallback.

    Produces a minimal but valid `FeedbackResult` so the lifecycle and
    persistence paths work end-to-end. Production uses the LLM-driven
    feedback agent from `app.ai.sessions`.
    """

    async def generate(
        self,
        *,
        archetype: ArchetypeSpec,
        evaluation: EvaluationResult,
        user_response: dict | None,
        task_content: dict | None = None,
        feedback_overrides: dict | None = None,
        learner_history: str | None = None,  # ignored by the stub
    ) -> FeedbackResult:
        rounded = int(round(evaluation.raw_score))
        if user_response is None:
            return FeedbackResult(
                score=0,
                summary=f"No response submitted for {archetype.name}.",
                did_well=(),
                mistakes=(),
                next_tip="Try submitting an answer next time, even a short one.",
                sub_skill_breakdown={skill: 0 for skill in archetype.weight_map},
            )
        return FeedbackResult(
            score=rounded,
            summary=(
                f"Stub feedback for {archetype.name} — scored {rounded}/10. "
                "Production uses archetype-aware LLM feedback."
            ),
            did_well=("Submitted a response on time.",),
            mistakes=(),
            next_tip=None,
            sub_skill_breakdown={skill: rounded for skill in archetype.weight_map},
        )
