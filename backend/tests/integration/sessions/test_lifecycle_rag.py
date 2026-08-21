"""RAG resilience: the vector store must never block or break the chat flow.

Split out of the former monolithic ``test_session_lifecycle.py``.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.sessions.evaluator import StubEvaluator
from app.modules.sessions.feedback_generator import StubFeedbackGenerator
from app.modules.sessions.models import AttemptStatus, SessionStatus
from app.modules.sessions.service import SessionService
from app.core.config import settings
from app.scoring import CourseLength

from tests.integration.sessions._lifecycle_support import _user_id


class TestRagResilience:
    """RAG is best-effort and must never block or break the chat flow.

    - ``submit_activity`` never touches the vector store synchronously.
    - ``complete_session`` is fully decoupled from the Coach's Note: it commits
      the scorecard with ``mentor_note=None`` and never awaits the generator, so
      a slow/hanging note can never stall completion.
    - ``ensure_mentor_note`` is the single, idempotent owner of note generation
      (retrieve context → generate → store the session-summary vector). It is
      awaited in-band by the chat WS / REST completion paths.
    - The background worker only re-indexes per-activity vectors.
    """

    @pytest.fixture(autouse=True)
    def _enable_rag_for_rag_contract_tests(self, monkeypatch):
        """Exercise the RAG contract independently of its production flag."""
        monkeypatch.setattr(settings, "ENABLE_RAG_FEEDBACK", True)

    async def _start(self, db, tasks_per_day=2, score=8.0):
        service = SessionService(
            db,
            evaluator=StubEvaluator(default_score=score),
            feedback_generator=StubFeedbackGenerator(),
        )
        session = await service.start_session(
            user_id=_user_id(db),
            day_id="day_24_09_03",
            course_length=CourseLength.WEEKS_24,
            tasks_per_day=tasks_per_day,
            allowed_activities={"read", "write", "listen", "speak"},
        )
        return service, session

    async def _submit_all(self, service, session, count):
        for seq in range(1, count + 1):
            await service.submit_activity(
                session_id=session.session_id,
                user_id=session.user_id,
                sequence=seq,
                user_response={"a": "b"},
            )

    @staticmethod
    def _mock_rag(order):
        async def rec_activity(**_kw):
            order.append("activity")
            return "act_x"

        async def rec_retrieve(**_kw):
            order.append("retrieve")
            return {}

        async def rec_session(**_kw):
            order.append("session")
            return "sess_x"

        async def rec_mentor(**_kw):
            order.append("mentor")
            return "Watch your tenses next time."

        rag = MagicMock()
        rag.store_activity_feedback = AsyncMock(side_effect=rec_activity)
        rag.retrieve_context_for_feedback = AsyncMock(side_effect=rec_retrieve)
        rag.store_session_summary = AsyncMock(side_effect=rec_session)
        mentor = MagicMock()
        mentor.generate = AsyncMock(side_effect=rec_mentor)
        return rag, mentor

    @pytest.mark.asyncio
    async def test_submit_does_not_touch_rag_synchronously(self, db_session):
        """The submit path must never call the vector store (it would race the
        shared WebSocket DB session)."""
        service, session = await self._start(db_session, tasks_per_day=2)
        rag = MagicMock()
        rag.store_activity_feedback = AsyncMock()
        rag.retrieve_context_for_activity = AsyncMock()
        service._rag_service = rag

        await service.submit_activity(
            session_id=session.session_id,
            user_id=session.user_id,
            sequence=1,
            user_response={"a": "b"},
        )

        assert rag.store_activity_feedback.await_count == 0
        assert rag.retrieve_context_for_activity.await_count == 0

    @pytest.mark.asyncio
    async def test_complete_session_does_not_generate_note(self, db_session):
        """Completion is decoupled from the note: even with RAG wired, the
        scorecard commits with mentor_note=None and the generator is untouched.
        Note generation is owned by the awaited ensure_mentor_note step."""
        service, session = await self._start(db_session, tasks_per_day=2)
        await self._submit_all(service, session, 2)

        order: list[str] = []
        rag, mentor = self._mock_rag(order)
        service._rag_service = rag
        service._mentor_generator = mentor
        service._schedule_post_completion_rag = lambda **kwargs: None  # isolate

        scorecard, _report = await service.complete_session(
            session_id=session.session_id,
            user_id=session.user_id,
        )

        assert scorecard.mentor_note is None
        assert order == []  # no retrieve / mentor / session on the completion path
        assert mentor.generate.await_count == 0

    @pytest.mark.asyncio
    async def test_complete_session_never_awaits_a_hanging_note(self, db_session):
        """A hanging generator cannot stall completion, because completion no
        longer awaits the note at all."""
        service, session = await self._start(db_session, tasks_per_day=2)
        await self._submit_all(service, session, 2)

        async def hang(**_kw):
            await asyncio.sleep(60)

        rag = MagicMock()
        rag.retrieve_context_for_feedback = AsyncMock(side_effect=hang)
        mentor = MagicMock()
        mentor.generate = AsyncMock(side_effect=hang)
        service._rag_service = rag
        service._mentor_generator = mentor
        service._schedule_post_completion_rag = lambda **kwargs: None

        scorecard, _report = await asyncio.wait_for(
            service.complete_session(
                session_id=session.session_id,
                user_id=session.user_id,
            ),
            timeout=2.0,
        )

        assert scorecard.mentor_note is None
        assert rag.retrieve_context_for_feedback.await_count == 0
        assert mentor.generate.await_count == 0
        refreshed = service.get_session(
            session_id=session.session_id,
            user_id=session.user_id,
        )
        assert refreshed.status is SessionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_ensure_mentor_note_generates_persists_and_stores_summary(
        self, db_session
    ):
        """ensure_mentor_note retrieves context, generates the note, persists it
        on the scorecard, and stores the day-level summary vector — in order."""
        service, session = await self._start(db_session, tasks_per_day=2)
        await self._submit_all(service, session, 2)
        scorecard, _report = await service.complete_session(
            session_id=session.session_id,
            user_id=session.user_id,
        )
        assert scorecard.mentor_note is None

        order: list[str] = []
        rag, mentor = self._mock_rag(order)
        service._rag_service = rag
        service._mentor_generator = mentor

        note = await service.ensure_mentor_note(
            session_id=session.session_id,
            user_id=session.user_id,
        )

        assert note == "Watch your tenses next time."
        assert order == ["retrieve", "mentor", "session"]
        db_session.refresh(scorecard)
        assert scorecard.mentor_note == "Watch your tenses next time."

    @pytest.mark.asyncio
    async def test_ensure_mentor_note_is_idempotent(self, db_session):
        """A second ensure_mentor_note returns the persisted note without
        re-invoking the LLM or re-storing the summary."""
        service, session = await self._start(db_session, tasks_per_day=2)
        await self._submit_all(service, session, 2)
        await service.complete_session(
            session_id=session.session_id,
            user_id=session.user_id,
        )

        order: list[str] = []
        rag, mentor = self._mock_rag(order)
        service._rag_service = rag
        service._mentor_generator = mentor

        first = await service.ensure_mentor_note(
            session_id=session.session_id,
            user_id=session.user_id,
        )
        second = await service.ensure_mentor_note(
            session_id=session.session_id,
            user_id=session.user_id,
        )

        assert first == second == "Watch your tenses next time."
        assert mentor.generate.await_count == 1  # not regenerated
        assert rag.store_session_summary.await_count == 1  # not re-stored

    @pytest.mark.asyncio
    async def test_ensure_mentor_note_generates_from_empty_context(self, db_session):
        """When RAG retrieval degrades to an empty context (slow/failed vectors),
        the note is still generated from the activity data alone."""
        service, session = await self._start(db_session, tasks_per_day=2)
        await self._submit_all(service, session, 2)
        await service.complete_session(
            session_id=session.session_id,
            user_id=session.user_id,
        )

        rag = MagicMock()
        rag.retrieve_context_for_feedback = AsyncMock(return_value={})  # degraded
        rag.store_session_summary = AsyncMock()
        mentor = MagicMock()
        mentor.generate = AsyncMock(return_value="Keep practising your tenses.")
        service._rag_service = rag
        service._mentor_generator = mentor

        note = await service.ensure_mentor_note(
            session_id=session.session_id,
            user_id=session.user_id,
        )

        assert note == "Keep practising your tenses."
        assert mentor.generate.await_count == 1

    @pytest.mark.asyncio
    async def test_worker_indexes_activities_only(self, db_session):
        """The background worker only re-indexes per-activity vectors; it does
        NOT retrieve context, generate the note, or store the summary."""
        service, session = await self._start(db_session, tasks_per_day=2)
        await self._submit_all(service, session, 2)
        scorecard, _report = await service.complete_session(
            session_id=session.session_id,
            user_id=session.user_id,
        )
        assert scorecard.mentor_note is None

        order: list[str] = []
        rag, mentor = self._mock_rag(order)
        service._rag_service = rag
        service._mentor_generator = mentor

        await service.run_post_completion_rag(
            session_id=session.session_id,
            user_id=session.user_id,
        )

        assert order == ["activity", "activity"]
        assert mentor.generate.await_count == 0
        assert rag.store_session_summary.await_count == 0
        db_session.refresh(scorecard)
        assert scorecard.mentor_note is None

    @pytest.mark.asyncio
    async def test_reset_activity_returns_without_awaiting_rag_delete(self, db_session):
        """Per-activity retry commits the V2 reset immediately and only
        *schedules* the (potentially slow) vector cleanup — it never awaits
        Pinecone, so a hanging delete cannot stall the retry."""
        service, session = await self._start(db_session, tasks_per_day=2)
        await self._submit_all(service, session, 2)
        await service.complete_session(
            session_id=session.session_id,
            user_id=session.user_id,
        )

        async def hang(*_a, **_kw):
            await asyncio.sleep(60)

        rag = MagicMock()
        rag.delete_for_attempt = AsyncMock(side_effect=hang)
        rag.delete_session_summary = AsyncMock(side_effect=hang)
        service._rag_service = rag
        scheduled: list[dict] = []
        service._schedule_rag_delete = lambda **kw: scheduled.append(kw)

        attempt = await asyncio.wait_for(
            service.reset_activity(
                session_id=session.session_id,
                user_id=session.user_id,
                sequence=1,
            ),
            timeout=2.0,
        )

        # V2 reset committed; the hanging delete was NOT awaited on the path.
        assert attempt.status is AttemptStatus.PENDING
        assert rag.delete_for_attempt.await_count == 0
        # Cleanup was scheduled fire-and-forget with the right scope.
        assert scheduled and scheduled[0]["delete_summary"] is True
        assert scheduled[0]["attempt_ids"] == [attempt.id]
        # The day was reopened and its now-stale scorecard dropped.
        refreshed = service.get_session(
            session_id=session.session_id,
            user_id=session.user_id,
        )
        assert refreshed.status is SessionStatus.IN_PROGRESS
        assert (
            service.get_scorecard(
                session_id=session.session_id,
                user_id=session.user_id,
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_reset_session_full_resets_all_and_schedules_delete(self, db_session):
        """Full restart resets every attempt to PENDING, drops the scorecard,
        reopens the day, commits immediately, and schedules background vector
        cleanup — without awaiting Pinecone."""
        service, session = await self._start(db_session, tasks_per_day=2)
        await self._submit_all(service, session, 2)
        await service.complete_session(
            session_id=session.session_id,
            user_id=session.user_id,
        )

        async def hang(*_a, **_kw):
            await asyncio.sleep(60)

        rag = MagicMock()
        rag.delete_for_attempt = AsyncMock(side_effect=hang)
        rag.delete_session_summary = AsyncMock(side_effect=hang)
        service._rag_service = rag
        scheduled: list[dict] = []
        service._schedule_rag_delete = lambda **kw: scheduled.append(kw)

        reopened = await asyncio.wait_for(
            service.reset_session_full(
                session_id=session.session_id,
                user_id=session.user_id,
            ),
            timeout=2.0,
        )

        assert reopened.status is SessionStatus.IN_PROGRESS
        assert reopened.completed_at is None
        attempts = service.attempts_repo.list_for_session(reopened.id)
        assert attempts
        assert all(a.status is AttemptStatus.PENDING for a in attempts)
        assert (
            service.get_scorecard(
                session_id=session.session_id,
                user_id=session.user_id,
            )
            is None
        )
        # Background cleanup scheduled for all attempts incl. session summary;
        # the hanging delete was never awaited on the request path.
        assert rag.delete_for_attempt.await_count == 0
        assert scheduled and scheduled[0]["delete_summary"] is True
        assert sorted(scheduled[0]["attempt_ids"]) == sorted(a.id for a in attempts)
