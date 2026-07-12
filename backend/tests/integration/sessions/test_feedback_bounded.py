"""Bounded feedback generation + in-place regeneration.

Covers Fix 2: a slow or failing feedback generator must degrade to a
deterministic fallback card (never rolling back the graded attempt), and
``regenerate_feedback`` must re-run feedback in place without touching the
stored score.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.config import settings
from app.modules.sessions.evaluator import StubEvaluator
from app.modules.sessions.feedback_generator import (
    FeedbackResult,
    StubFeedbackGenerator,
)
from app.modules.sessions.models import AttemptStatus
from app.modules.sessions.service import FeedbackPhase, SessionService
from app.scoring import CourseLength

from tests.integration.sessions._lifecycle_support import _user_id


class _HangingFeedbackGenerator:
    """Sleeps past the feedback cap so ``asyncio.wait_for`` fires."""

    async def generate(self, **kwargs):
        await asyncio.sleep(5)
        raise AssertionError("should have been cancelled by the timeout")


class _RaisingFeedbackGenerator:
    """Raises a non-LLM error to exercise the broad fallback path."""

    async def generate(self, **kwargs):
        raise RuntimeError("boom")


class _MarkerFeedbackGenerator(StubFeedbackGenerator):
    """Stamps a recognizable summary so a regenerate can be observed."""

    def __init__(self, marker: str) -> None:
        self.marker = marker

    async def generate(self, **kwargs):
        base = await super().generate(**kwargs)
        return FeedbackResult(
            score=base.score,
            summary=self.marker,
            did_well=base.did_well,
            mistakes=base.mistakes,
            next_tip=base.next_tip,
            sub_skill_breakdown=base.sub_skill_breakdown,
        )


async def _start(db, *, feedback_generator, score=7.0):
    service = SessionService(
        db,
        evaluator=StubEvaluator(default_score=score),
        feedback_generator=feedback_generator,
    )
    session = await service.start_session(
        user_id=_user_id(db),
        day_id="day_24_09_03",
        course_length=CourseLength.WEEKS_24,
        tasks_per_day=2,
        allowed_activities={"read", "write", "listen", "speak"},
    )
    return service, session


@pytest.mark.asyncio
async def test_feedback_timeout_yields_fallback_and_preserves_score(
    db_session, monkeypatch
):
    monkeypatch.setattr(settings, "FEEDBACK_TIMEOUT_S", 0.05)
    service, session = await _start(
        db_session, feedback_generator=_HangingFeedbackGenerator()
    )

    attempt, evaluation, feedback = await service.submit_activity(
        session_id=session.session_id,
        user_id=session.user_id,
        sequence=1,
        user_response={"a": "b"},
    )

    # The graded attempt survived: committed, EVALUATED, score intact.
    assert attempt.status is AttemptStatus.EVALUATED
    assert evaluation.raw_score == pytest.approx(7.0)
    # A fallback card was still written, carrying the score.
    assert feedback.score == 7
    assert "longer" in feedback.summary.lower()

    refreshed = service.get_session(
        session_id=session.session_id, user_id=session.user_id
    )
    graded = refreshed.attempts[0]
    assert graded.feedback is not None
    assert graded.evaluation.raw_score == pytest.approx(7.0)


@pytest.mark.asyncio
async def test_feedback_phase_flags_fallback_on_timeout(db_session, monkeypatch):
    """The FeedbackPhase carries fallback=True so the WS layer can offer
    "Regenerate feedback" only when the card is a degraded placeholder."""
    monkeypatch.setattr(settings, "FEEDBACK_TIMEOUT_S", 0.05)
    service, session = await _start(
        db_session, feedback_generator=_HangingFeedbackGenerator()
    )
    gen = service.submit_activity_phased(
        session_id=session.session_id,
        user_id=session.user_id,
        sequence=1,
        user_response={"a": "b"},
    )
    await anext(gen)  # evaluation phase
    fb_phase = await anext(gen)
    assert isinstance(fb_phase, FeedbackPhase)
    assert fb_phase.fallback is True
    with pytest.raises(StopAsyncIteration):
        await anext(gen)


@pytest.mark.asyncio
async def test_feedback_phase_not_fallback_on_success(db_session):
    """A healthy generated card must NOT be flagged as a fallback."""
    service, session = await _start(
        db_session, feedback_generator=StubFeedbackGenerator()
    )
    gen = service.submit_activity_phased(
        session_id=session.session_id,
        user_id=session.user_id,
        sequence=1,
        user_response={"a": "b"},
    )
    await anext(gen)
    fb_phase = await anext(gen)
    assert isinstance(fb_phase, FeedbackPhase)
    assert fb_phase.fallback is False
    with pytest.raises(StopAsyncIteration):
        await anext(gen)


@pytest.mark.asyncio
async def test_feedback_error_yields_fallback(db_session):
    service, session = await _start(
        db_session, feedback_generator=_RaisingFeedbackGenerator()
    )

    attempt, evaluation, feedback = await service.submit_activity(
        session_id=session.session_id,
        user_id=session.user_id,
        sequence=1,
        user_response={"a": "b"},
    )

    assert attempt.status is AttemptStatus.EVALUATED
    assert evaluation.raw_score == pytest.approx(7.0)
    assert feedback.score == 7


@pytest.mark.asyncio
async def test_regenerate_feedback_reruns_without_touching_score(db_session):
    service, session = await _start(
        db_session, feedback_generator=_MarkerFeedbackGenerator("FIRST")
    )
    await service.submit_activity(
        session_id=session.session_id,
        user_id=session.user_id,
        sequence=1,
        user_response={"a": "b"},
    )

    # Swap in a generator that produces a distinct card, then regenerate.
    service.feedback_generator = _MarkerFeedbackGenerator("SECOND")
    regenerated, is_fallback = await service.regenerate_feedback(
        session_id=session.session_id,
        user_id=session.user_id,
        sequence=1,
    )

    assert regenerated.summary == "SECOND"
    assert is_fallback is False

    refreshed = service.get_session(
        session_id=session.session_id, user_id=session.user_id
    )
    graded = refreshed.attempts[0]
    # Feedback was replaced in place; the stored score/evaluation is untouched.
    assert graded.feedback.summary == "SECOND"
    assert graded.status is AttemptStatus.EVALUATED
    assert graded.evaluation.raw_score == pytest.approx(7.0)
