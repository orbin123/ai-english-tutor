"""SessionService — orchestrates the start / next / submit / complete lifecycle.

Public methods:
  - `start_session(...)`     — POST /sessions/start
  - `next_activity(...)`     — GET  /sessions/{id}/next-activity
  - `submit_activity(...)`   — POST /sessions/{id}/activities/{seq}/submit
  - `complete_session(...)`  — POST /sessions/{id}/complete
  - `get_scorecard(...)`     — GET  /sessions/{id}/scorecard

The service does its own commits at logical boundaries (one per public call).
Evaluator and FeedbackGenerator are injected — Phase 4 swaps in LLM-driven
implementations without touching this file.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any, NamedTuple
from uuid import uuid4

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.llm.eval_context import (
    get_eval_context,
    reset_eval_context,
    set_eval_context,
)
from app.ai.sessions.llm_evaluator import is_llm_backed_evaluation
from app.core.config import settings
from app.core.sentry import capture_to_sentry
from app.modules.sessions.contracts.agent_inputs import (
    EvaluatorAgentInput,
    FeedbackAgentInput,
    TaskGenAgentInput,
    build_agent_input,
)
from app.modules.sessions.contracts.validation import normalize_task_content
from app.modules.curriculum.file_source import (
    get_day_by_id as file_get_day_by_id,
    parse_day_id,
    resolve_archetypes as file_resolve_archetypes,
    task_spec_for as file_task_spec_for,
)
from app.modules.curriculum.repository import (
    CurriculumDayRepository,
    CurriculumWeekRepository,
    TaskArchetypeRepository,
)
from app.modules.preferences.repository import UserCoursePreferenceRepository
from app.modules.progress.repository import (
    SkillPointsLogRepository,
    SkillPointsRepository,
)
from app.modules.sessions.evaluator import Evaluator, EvaluationResult, StubEvaluator
from app.modules.sessions.exceptions import (
    AttemptAlreadySubmitted,
    AttemptNotFound,
    DayNotFound,
    NoActivitiesPlanned,
    SessionAdvanceBlocked,
    SessionAbandoned,
    SessionAlreadyCompleted,
    SessionAlreadyOpen,
    SessionNotFound,
)
from app.modules.sessions.feedback_generator import (
    FeedbackGenerator,
    FeedbackResult,
    StubFeedbackGenerator,
)
from app.modules.sessions.models import (
    ActivityAttempt,
    ActivityEvaluation,
    ActivityFeedback,
    AttemptStatus,
    DailySession,
    SessionScorecard,
    SessionStatus,
)
from app.modules.sessions.planner import plan_session
from app.modules.sessions.repository import (
    ActivityAttemptRepository,
    DailySessionRepository,
    EvaluationRepository,
    FeedbackRepository,
    ScorecardRepository,
)
from app.modules.sessions.scoring_writer import ApplyReport, apply_session_scorecard
from app.modules.sessions.task_generator import (
    StubTaskGenerator,
    TaskGenerator,
    is_valid_task_content,
)
from app.modules.skills.repository import SkillRepository
from app.scoring import (
    ActivityScore,
    ArchetypeSpec,
    CourseLength,
    SUB_SKILLS,
    base_reward,
    build_session_aggregation,
    distribute,
    get_archetype,
    tier_for_score,
)


log = structlog.get_logger(__name__)

# Cap on concurrent task generations per session start. Bounds OpenAI 429
# pressure while still collapsing wall time from sum(activities) to roughly
# max(activities).
_TASKGEN_CONCURRENCY = 4


class EvaluationPhase(NamedTuple):
    """First phase of a submit: grading is done, feedback is not yet generated.

    Yielded by :meth:`SessionService.submit_activity_phased` so the WebSocket
    layer can emit the score the instant grading finishes, before the (slower)
    feedback generation. The ``ActivityEvaluation`` row is added to the session
    but **not yet committed** (the single commit happens in the feedback phase).
    """

    attempt: ActivityAttempt
    evaluation: ActivityEvaluation


class FeedbackPhase(NamedTuple):
    """Second phase of a submit: feedback is ready and the transaction is
    committed (eval + feedback + streak in one commit, exactly as the legacy
    single-shot submit)."""

    feedback: ActivityFeedback


def _fallback_feedback(spec: ArchetypeSpec, raw_score: float) -> FeedbackResult:
    """Deterministic feedback card used when generation times out or fails.

    Carries the (already computed) score so the learner is never stranded under
    an empty scorecard; the summary invites a regenerate. Mirrors the stub
    ``LLMFeedbackGenerator`` produces on ``LLMError`` so both paths look alike.
    """
    rounded = int(round(raw_score))
    return FeedbackResult(
        score=rounded,
        summary=(
            f"Your score is {rounded}/10. Detailed feedback is taking longer "
            "than usual — you can regenerate it below."
        ),
        did_well=(),
        mistakes=(),
        next_tip=None,
        sub_skill_breakdown={skill: rounded for skill in spec.weight_map},
    )


def _validate_agent_input(model_cls, **fields) -> None:
    """Guard a service→agent boundary input.

    Raises under ``settings.strict_contracts``; otherwise logs and proceeds on
    the legacy path. Validation is for its side effect (catch missing/mistyped
    inputs early) — callers keep using their original values.
    """
    if build_agent_input(model_cls, strict=settings.strict_contracts, **fields) is None:
        log.warning(
            "agent_input_validation_failed",
            boundary=model_cls.__name__,
            note="proceeding on legacy path",
        )


class SessionService:
    """Orchestrator for the new sessions lifecycle."""

    def __init__(
        self,
        db: Session,
        *,
        evaluator: Evaluator | None = None,
        feedback_generator: FeedbackGenerator | None = None,
        task_generator: TaskGenerator | None = None,
        judge: Any | None = None,
    ) -> None:
        self.db = db
        # The three injectable agents default to stubs. Production wiring
        # (FastAPI dep / route factory) replaces these with the LLM-driven
        # implementations from `app.ai.sessions`.
        self.evaluator: Evaluator = evaluator or StubEvaluator()
        self.feedback_generator: FeedbackGenerator = (
            feedback_generator or StubFeedbackGenerator()
        )
        self.task_generator: TaskGenerator = task_generator or StubTaskGenerator()

        self.sessions_repo = DailySessionRepository(db)
        self.attempts_repo = ActivityAttemptRepository(db)
        self.evaluations_repo = EvaluationRepository(db)
        self.feedback_repo = FeedbackRepository(db)
        self.scorecards_repo = ScorecardRepository(db)
        self.days_repo = CurriculumDayRepository(db)
        self.weeks_repo = CurriculumWeekRepository(db)
        self.archetypes_repo = TaskArchetypeRepository(db)
        self.skills_repo = SkillRepository(db)
        self.points_repo = SkillPointsRepository(db)
        self.points_log_repo = SkillPointsLogRepository(db)
        self.preferences_repo = UserCoursePreferenceRepository(db)

        # RAG memory service — optional. When absent (tests, early phases),
        # activity memory storage and mentor note generation are skipped.
        self._rag_service: Any | None = None
        self._mentor_generator: Any | None = None
        self._pending_rag_tasks: list[asyncio.Task[None]] = []

        # LLM-as-judge quality scorer (Part B Phase 2) — optional. When absent
        # (tests, stub wiring) online quality sampling is skipped entirely.
        self._judge: Any | None = judge

    # ── start ──────────────────────────────────────────────────────

    async def start_session(
        self,
        *,
        user_id: int,
        day_id: str | None = None,
        course_length: CourseLength,
        tasks_per_day: int,
        allowed_activities: set[str],
        sub_level: int | None = None,
        user_interests: list[str] | None = None,
        now: datetime | None = None,
        week_number: int | None = None,
        day_index: int | None = None,
    ) -> DailySession:
        """Create a new session for `(user_id, day_id)`. Raises if one is open.

        If the day is file-authored (24w ``day_24_*`` or 48w ``day_48_*``,
        resolved via ``file_source``), the archetype order and task specs come
        from the composed band source files instead of the planner.
        """
        now = now or datetime.now(timezone.utc)
        t0 = time.perf_counter()

        if day_id is None:
            raise DayNotFound("day_id is required")

        day = self.days_repo.get_by_day_id(day_id)
        if day is None:
            raise DayNotFound(f"day_id={day_id!r} not found in curriculum_days")

        if (
            self.sessions_repo.get_in_progress(user_id=user_id, day_id=day_id)
            is not None
        ):
            raise SessionAlreadyOpen(
                f"user {user_id} already has an in-progress session for day {day_id!r}"
            )

        file_day_override = None
        try:
            file_day_override = file_get_day_by_id(day.day_id)
        except DayNotFound:
            file_day_override = None

        source_plan: list[tuple[int, ArchetypeSpec, dict]] | None = None
        if file_day_override is not None:
            source_plan = []
            for i, spec in enumerate(file_resolve_archetypes(file_day_override)):
                if spec.core_activity not in allowed_activities:
                    continue
                source_plan.append((i, spec, file_task_spec_for(file_day_override, i)))
            if not source_plan:
                raise NoActivitiesPlanned(
                    f"source day {day.day_id!r}: no archetypes match "
                    f"allowed activities {sorted(allowed_activities)}"
                )
        else:
            plan = plan_session(
                day,
                tasks_per_day=tasks_per_day,
                allowed_activities=allowed_activities,
            )
            if not plan:
                # `plan_session` already raises NoActivitiesPlanned in this case;
                # belt-and-suspenders for clarity.
                raise NoActivitiesPlanned(f"empty plan for day {day_id!r}")

        is_first = not self.sessions_repo.has_completed_for_day(
            user_id=user_id, day_id=day_id
        )

        session = DailySession(
            session_id=str(uuid4()),
            user_id=user_id,
            day_id=day.day_id,
            course_length=course_length.value,
            status=SessionStatus.IN_PROGRESS,
            is_first_attempt=is_first,
            started_at=now,
        )
        self.sessions_repo.add(session)

        # Look up the parent week so the task generator can pick a content
        # depth that matches the user's CEFR + sub_level. Falls back to the
        # week's sub_level_min if no explicit sub_level is provided.
        parent_week = day.week  # loaded via relationship
        if parent_week is None:
            raise DayNotFound(f"day_id={day_id!r} has no parent curriculum week")

        if file_day_override is not None and source_plan is not None:
            effective_sub_level = sub_level or file_day_override.sub_level_min
            items: list[dict] = [
                {
                    "day_topic": file_day_override.topic,
                    "explanation_brief": file_day_override.explanation_brief,
                    "archetype_id": spec.archetype_id,
                    "sequence": sequence,
                    "is_mandatory": True,
                    "cefr_level": file_day_override.cefr_level,
                    "sub_level": effective_sub_level,
                    "user_interests": user_interests,
                    "task_spec": task_spec or None,
                }
                for sequence, (_orig_index, spec, task_spec) in enumerate(
                    source_plan,
                    start=1,
                )
            ]
        else:
            effective_sub_level = sub_level or parent_week.sub_level_min
            items = [
                {
                    "day_topic": day.topic,
                    "explanation_brief": day.explanation_brief,
                    "archetype_id": activity.archetype_id,
                    "sequence": activity.sequence,
                    "is_mandatory": activity.is_mandatory,
                    "cefr_level": parent_week.cefr_level,
                    "sub_level": effective_sub_level,
                    "user_interests": user_interests,
                    "task_spec": None,
                }
                for activity in plan
            ]

        # Lazy task generation: start returns instantly. Each attempt is
        # persisted with a *placeholder* task_content that carries (a) the
        # generation recipe (``__pending_taskgen``) and (b) the deterministic
        # activity contract — so the blueprint and the position-reserving
        # skeletons resolve before any LLM runs. No task LLM is called here.
        # Real content is filled by a fire-and-forget background worker and, as
        # a safety net, on demand at delivery time via
        # ``prepare_attempt_for_delivery`` → ``ensure_attempt_content``.
        persist_t0 = time.perf_counter()
        for item in items:
            self._persist_attempt(
                session=session,
                archetype_id=item["archetype_id"],
                sequence=item["sequence"],
                is_mandatory=item["is_mandatory"],
                content=self._pending_task_content(item),
            )

        self.db.commit()
        self.db.refresh(session)
        self._schedule_lazy_taskgen(session_id=session.session_id, user_id=user_id)
        log.info(
            "session_start_timing",
            user_id=user_id,
            day_id=day_id,
            file_authored=file_day_override is not None,
            activity_count=len(items),
            lazy_taskgen=True,
            persist_ms=round((time.perf_counter() - persist_t0) * 1000),
            total_ms=round((time.perf_counter() - t0) * 1000),
        )
        return session

    # ── next ───────────────────────────────────────────────────────

    def next_activity(self, *, session_id: str, user_id: int) -> ActivityAttempt:
        """Return the next pending attempt + its task_content.

        Synchronous fetch only. Callers that ship the payload to the UI MUST
        also await `prepare_attempt_for_delivery(...)` to self-heal any
        attempt that was persisted with incomplete content by an older code
        path (e.g. listening attempts missing audio_script / items).

        Raises:
          SessionNotFound       — unknown session_id, or owned by another user
          SessionAlreadyCompleted — all attempts done; caller should call complete
          SessionAbandoned       — session was abandoned
        """
        session = self._load_owned(session_id=session_id, user_id=user_id)
        self._guard_open(session)

        next_attempt = self.attempts_repo.first_pending(session.id)
        if next_attempt is None:
            raise SessionAlreadyCompleted(
                f"session {session_id!r}: no pending attempts; call complete instead"
            )
        return next_attempt

    async def prepare_attempt_for_delivery(
        self, attempt: ActivityAttempt
    ) -> ActivityAttempt:
        """Heal `task_content` if it's broken for its archetype, then return.

        Keeps the UI from seeing the "Audio could not be prepared" dead-end
        on listening attempts whose content was persisted by an older
        StubTaskGenerator that didn't populate `audio_script` / `items` /
        `inner_widget`. Mutates the row in-place + commits when it
        regenerates so the eventual evaluator sees the same content the
        widget rendered.

        No-op when the existing content is already valid for its archetype.
        """
        # Lazy-gen safety net: if the learner reached this task before the
        # background worker filled it, generate it now (awaited). The chat shows
        # the task skeleton during this wait. No-op once content is real.
        attempt = await self.ensure_attempt_content(attempt)
        spec = get_archetype(attempt.archetype_id)
        content = dict(attempt.task_content or {})
        healed = normalize_task_content(spec.archetype_id, content)
        if spec.archetype_id == "SPEAK_PIC_DESC":
            from app.ai.sessions.llm_task_generator import LLMTaskGenerator

            image_alt = str(healed.get("image_alt") or "").strip()
            image_url = str(healed.get("image_url") or "").strip()
            if image_alt and not image_url and not healed.get("image_error"):
                healed = await LLMTaskGenerator._attach_required_image(
                    content=healed,
                    archetype=spec,
                )
        if healed != content:
            attempt.task_content = healed
            self.db.commit()
            self.db.refresh(attempt)
            content = healed
        if self._is_attempt_content_valid(content, spec):
            return attempt

        log.warning(
            "attempt_invalid_task_content_regenerating",
            attempt_id=attempt.id,
            archetype=attempt.archetype_id,
            phase=content.get("phase"),
            generator=type(self.task_generator).__name__,
        )
        repaired = await self._regenerate_task_content(
            attempt=attempt,
            archetype=spec,
            prior=content,
        )
        attempt.task_content = repaired
        self.db.commit()
        self.db.refresh(attempt)
        return attempt

    async def force_regenerate_attempt(
        self, attempt: ActivityAttempt
    ) -> ActivityAttempt:
        """Re-run the task agent for a pending attempt, ignoring cached content.

        Unconditional counterpart to ``prepare_attempt_for_delivery``: it does
        not consult ``_is_attempt_content_valid`` (which is lenient and can pass
        an empty-``items`` payload that the strict contract later rejects). It
        always calls the generator via ``_regenerate_task_content`` and replaces
        the persisted ``task_content``. Used by the chat "retry" affordance after
        a generation/validation failure, so the learner gets a genuinely fresh
        task rather than the same broken cached one.
        """
        spec = get_archetype(attempt.archetype_id)
        repaired = await self._regenerate_task_content(
            attempt=attempt,
            archetype=spec,
            prior=dict(attempt.task_content or {}),
        )
        attempt.task_content = repaired
        self.db.commit()
        self.db.refresh(attempt)
        return attempt

    @staticmethod
    def _is_attempt_content_valid(content: dict, spec: ArchetypeSpec) -> bool:
        return is_valid_task_content(spec.archetype_id, content)

    async def _regenerate_task_content(
        self,
        *,
        attempt: ActivityAttempt,
        archetype: ArchetypeSpec,
        prior: dict,
    ) -> dict:
        """Best-effort regeneration that reuses any context already on the row."""
        source_context = self._file_repair_context_for_attempt(attempt, archetype)
        day_topic = (
            (source_context[0].topic if source_context else "")
            or str(prior.get("topic") or "").strip()
            or str(prior.get("topic_name") or "").strip()
            or archetype.name
        )
        explanation_brief = (
            source_context[0].explanation_brief if source_context else ""
        ) or str(prior.get("explanation_brief") or "").strip()
        cefr_level = (
            (source_context[0].cefr_level if source_context else "")
            or str(prior.get("cefr_level") or "A1").strip()
            or "A1"
        )
        try:
            sub_level = int(
                source_context[0].sub_level_min
                if source_context
                else prior.get("sub_level") or 1
            )
        except (TypeError, ValueError):
            sub_level = 1

        task_spec: dict = (
            dict(source_context[1])
            if source_context and source_context[1]
            else {"topic_override": day_topic}
        )
        task_spec.setdefault("topic_override", day_topic)
        instructions = str(prior.get("instructions") or "").strip()
        if instructions and "instructions_override" not in task_spec:
            task_spec["instructions_override"] = instructions
        if prior.get("task_intro") and "task_intro" not in task_spec:
            task_spec["task_intro"] = prior["task_intro"]
        if (
            prior.get("estimated_time_minutes")
            and "estimated_time_minutes" not in task_spec
        ):
            task_spec["estimated_time_minutes"] = prior["estimated_time_minutes"]

        generated = await self.task_generator.generate(
            archetype=archetype,
            day_topic=day_topic,
            explanation_brief=explanation_brief,
            cefr_level=cefr_level,
            sub_level=sub_level,
            user_interests=None,
            task_spec=task_spec,
        )
        return self._attach_activity_contract(
            content=dict(generated.content),
            archetype=archetype,
            sequence=attempt.sequence,
            is_mandatory=attempt.is_mandatory,
            task_spec=task_spec,
        )

    @staticmethod
    def _file_repair_context_for_attempt(
        attempt: ActivityAttempt,
        archetype: ArchetypeSpec,
    ) -> tuple[Any, dict] | None:
        """Return file-authored day/spec context for stale persisted attempts."""
        try:
            day = file_get_day_by_id(attempt.session.day_id)
        except DayNotFound:
            return None

        matching_indexes = [
            index
            for index, archetype_id in enumerate(day.task_archetypes_used)
            if archetype_id == archetype.archetype_id
        ]
        if len(matching_indexes) == 1:
            spec_index = matching_indexes[0]
        else:
            spec_index = attempt.sequence - 1

        task_spec = file_task_spec_for(day, spec_index)
        return day, task_spec

    # ── submit ─────────────────────────────────────────────────────

    async def submit_activity(
        self,
        *,
        session_id: str,
        user_id: int,
        sequence: int,
        user_response: dict | None,
        now: datetime | None = None,
    ) -> tuple[ActivityAttempt, ActivityEvaluation, ActivityFeedback]:
        """Public entry point. Stamps one correlation ``trace_id`` on this submit
        so every LLM call it triggers (evaluator, feedback) shares a trace in
        ``ai_request_logs``, then drains the phased generator into the legacy
        ``(attempt, evaluation, feedback)`` triple — no behaviour change for
        non-streaming callers (REST route + tests). Reuses the ambient
        ``trace_id`` stamped by ``TraceIDMiddleware`` when present so logs, cost
        and quality all join on one id; mints a fresh one when called outside an
        HTTP request (e.g. tests). The WebSocket layer iterates
        :meth:`submit_activity_phased` directly so it can emit the score before
        feedback is ready."""
        existing = get_eval_context()
        token = set_eval_context(
            trace_id=existing.trace_id or uuid4().hex, user_id=user_id
        )
        try:
            attempt: ActivityAttempt | None = None
            evaluation: ActivityEvaluation | None = None
            feedback: ActivityFeedback | None = None
            async for phase in self.submit_activity_phased(
                session_id=session_id,
                user_id=user_id,
                sequence=sequence,
                user_response=user_response,
                now=now,
            ):
                if isinstance(phase, EvaluationPhase):
                    attempt, evaluation = phase.attempt, phase.evaluation
                else:
                    feedback = phase.feedback
            assert (
                attempt is not None and evaluation is not None and feedback is not None
            ), (
                "submit_activity_phased must yield both an evaluation and a feedback phase"
            )
            return attempt, evaluation, feedback
        finally:
            reset_eval_context(token)

    async def submit_activity_phased(
        self,
        *,
        session_id: str,
        user_id: int,
        sequence: int,
        user_response: dict | None,
        now: datetime | None = None,
    ) -> AsyncGenerator[EvaluationPhase | FeedbackPhase, None]:
        """Persist response, run evaluator + feedback generator, store results —
        in two phases that share **one** DB transaction and **one** commit.

        Yields ``EvaluationPhase`` the instant grading finishes (the
        ``ActivityEvaluation`` row is added but **not** committed), then
        ``FeedbackPhase`` once feedback is generated, the streak is recorded, and
        the single ``commit()`` lands. The WebSocket layer emits the score event
        between the two yields so the learner sees the score immediately.

        Trace context: the public ``submit_activity`` wrapper sets the eval
        context for non-streaming callers; the WebSocket caller is already
        wrapped by ``process_message_stream``'s per-message ``trace_id``. So both
        LLM calls share one trace in every path; this generator does not manage
        the eval context itself.

        Replay guard: ``attempt.status`` flips to ``EVALUATED`` only at the final
        commit, so a re-submit between phases re-enters cleanly; if the feedback
        phase throws, nothing is committed and the attempt stays re-deliverable.
        """
        now = now or datetime.now(timezone.utc)
        session = self._load_owned(session_id=session_id, user_id=user_id)
        self._guard_open(session)

        attempt = self.attempts_repo.get(session_pk=session.id, sequence=sequence)
        if attempt is None:
            raise AttemptNotFound(
                f"session {session_id!r}: no attempt at sequence {sequence}"
            )
        if attempt.status is AttemptStatus.EVALUATED:
            raise AttemptAlreadySubmitted(
                f"session {session_id!r} seq {sequence}: already evaluated"
            )

        spec = get_archetype(attempt.archetype_id)

        # Persist the user's response and flip to SUBMITTED.
        attempt.user_response = user_response
        attempt.submitted_at = now
        attempt.status = AttemptStatus.SUBMITTED

        # Lookup file-authored overrides for evaluator and feedback.
        file_overrides = self._file_overrides_for_day(session.day_id)

        # ── Phase 1: evaluate ──────────────────────────────────────────
        _validate_agent_input(
            EvaluatorAgentInput,
            archetype_id=attempt.archetype_id,
            task_content=attempt.task_content or {},
            user_response=user_response or {},
        )
        eval_result: EvaluationResult = await self.evaluator.evaluate(
            archetype=spec,
            task_content=attempt.task_content,
            user_response=user_response,
            evaluator_overrides=file_overrides.get("evaluator") or None,
        )
        course_length = CourseLength(session.course_length)
        reward = base_reward(eval_result.raw_score, course_length)
        weighted = distribute(reward, dict(spec.weight_map))

        evaluation = ActivityEvaluation(
            attempt_id=attempt.id,
            raw_score=eval_result.raw_score,
            rubric_scores=dict(eval_result.rubric_scores),
            base_reward=reward,
            weighted_points=weighted,
            evaluator_notes=eval_result.evaluator_notes,
        )
        self.evaluations_repo.add(evaluation)

        # Grading is done — hand the score to the caller before generating
        # feedback (no commit yet; the single commit lands in phase 2).
        yield EvaluationPhase(attempt, evaluation)

        # ── Phase 2: feedback (+ streak, single commit) ────────────────
        _validate_agent_input(
            FeedbackAgentInput,
            archetype_id=attempt.archetype_id,
            task_content=attempt.task_content or {},
            evaluation={
                "raw_score": eval_result.raw_score,
                "rubric_scores": dict(eval_result.rubric_scores or {}),
            },
            user_response=user_response or {},
        )
        # Phase 2 (flagged): make feedback memory-aware. Advisory only —
        # never changes the score. No-op when the flag is off or RAG is
        # unavailable.
        learner_history: str | None = None
        if settings.RAG_PER_ACTIVITY_FEEDBACK and self._rag_service is not None:
            try:
                learner_history = await asyncio.wait_for(
                    self._rag_service.retrieve_context_for_activity(
                        user_id=session.user_id,
                        archetype_id=attempt.archetype_id,
                        query_text=f"{spec.name}: {eval_result.evaluator_notes or ''}",
                    ),
                    timeout=settings.RAG_PER_ACTIVITY_TIMEOUT_S,
                )
            except Exception:
                # Best-effort: a slow/failed lookup must never block feedback.
                log.warning(
                    "per_activity_rag_retrieval_skipped",
                    attempt_id=attempt.id,
                    exc_info=True,
                )
                learner_history = None

        fb: FeedbackResult = await self._generate_feedback_bounded(
            spec=spec,
            evaluation=eval_result,
            user_response=user_response,
            task_content=attempt.task_content,
            feedback_overrides=file_overrides.get("feedback") or None,
            learner_history=learner_history,
        )
        feedback = ActivityFeedback(
            attempt_id=attempt.id,
            score=fb.score,
            summary=fb.summary,
            did_well=list(fb.did_well),
            mistakes=[
                {
                    "issue": m.issue,
                    "user_wrote": m.user_wrote,
                    "correction": m.correction,
                    "rule": m.rule,
                    "sub_skills_affected": list(m.sub_skills_affected),
                }
                for m in fb.mistakes
            ],
            next_tip=fb.next_tip,
            sub_skill_breakdown=dict(fb.sub_skill_breakdown),
        )
        self.feedback_repo.add(feedback)

        attempt.status = AttemptStatus.EVALUATED

        # Streak: first evaluated activity per local calendar day (same TX).
        # Kept here, right before the single commit, so its concurrent-double-
        # fire rollback path (streaks/service.py) has the same transaction scope
        # as the legacy single-shot submit.
        from app.modules.streaks.service import StreakService

        StreakService(self.db).record_in_same_tx(
            user_id=session.user_id,
            session_id=session.id,
            now_utc=now,
        )

        self.db.commit()
        self.db.refresh(attempt)
        self.db.refresh(evaluation)
        self.db.refresh(feedback)

        # NOTE: activity feedback is NOT indexed to the vector store here.
        # Doing so on `self.db` (the request/WebSocket-scoped session) from a
        # background task races the live chat flow — a SQLAlchemy Session is
        # not safe for concurrent use. Indexing happens in the post-completion
        # background worker (`run_post_completion_rag`), which opens its own
        # session and re-indexes every evaluated activity idempotently.

        # LLM-as-judge quality sampling (Part B Phase 2). Fire-and-forget after
        # commit, only for LLM-graded archetypes, at AI_EVAL_SAMPLE_RATE. Pure
        # observability — runs on its own DB session and never blocks/affects
        # the learner. Skipped when disabled, no judge wired, or arithmetic.
        if (
            settings.AI_EVAL_ENABLED
            and self._judge is not None
            and is_llm_backed_evaluation(spec)
            and random.random() < settings.AI_EVAL_SAMPLE_RATE
        ):
            self._schedule_ai_eval(
                trace_id=get_eval_context().trace_id,
                user_id=session.user_id,
                target_id=str(feedback.id),
                task_content=dict(attempt.task_content or {}),
                user_response=dict(user_response or {}),
                feedback={
                    "summary": feedback.summary,
                    "did_well": list(feedback.did_well or []),
                    "mistakes": list(feedback.mistakes or []),
                    "next_tip": feedback.next_tip,
                },
            )

        yield FeedbackPhase(feedback)

    async def _generate_feedback_bounded(
        self,
        *,
        spec: ArchetypeSpec,
        evaluation: EvaluationResult,
        user_response: dict | None,
        task_content: dict | None,
        feedback_overrides: dict | None,
        learner_history: str | None,
    ) -> FeedbackResult:
        """Generate feedback under a hard wall-clock cap.

        The learner has already seen their score; feedback must never block the
        turn past the frontend's ceiling nor cost them the graded attempt. We cap
        the generation at ``FEEDBACK_TIMEOUT_S`` and, on timeout OR any failure,
        return a deterministic fallback card built from the (already computed)
        score. Callers therefore always get a non-empty ``FeedbackResult`` and can
        commit the attempt — a slow model degrades to a fallback, not a rollback.
        """
        try:
            return await asyncio.wait_for(
                self.feedback_generator.generate(
                    archetype=spec,
                    evaluation=evaluation,
                    user_response=user_response,
                    task_content=task_content,
                    feedback_overrides=feedback_overrides,
                    learner_history=learner_history,
                ),
                timeout=settings.FEEDBACK_TIMEOUT_S,
            )
        except Exception:
            # Timeout, cancellation, LLM error, or an unexpected failure — the
            # score is safe; downgrade to a deterministic card so the attempt
            # still commits and the learner can regenerate.
            log.warning(
                "feedback_generation_fallback",
                archetype=spec.archetype_id,
                exc_info=True,
            )
            return _fallback_feedback(spec, evaluation.raw_score)

    async def regenerate_feedback(
        self,
        *,
        session_id: str,
        user_id: int,
        sequence: int,
    ) -> ActivityFeedback:
        """Re-run feedback for an already-evaluated attempt, in place.

        Reuses the stored :class:`ActivityEvaluation` (the score/rubric are NOT
        recomputed and the graded response/task are untouched) and overwrites the
        attempt's :class:`ActivityFeedback` with a freshly generated card. Bounded
        by the same cap as the submit path, so a persistent outage still yields a
        fallback card rather than an error. Used by the "Regenerate feedback"
        action when the first generation timed out to a fallback.
        """
        session = self._load_owned(session_id=session_id, user_id=user_id)
        attempt = self.attempts_repo.get(session_pk=session.id, sequence=sequence)
        if attempt is None:
            raise AttemptNotFound(
                f"session {session_id!r}: no attempt at sequence {sequence}"
            )
        if attempt.status is not AttemptStatus.EVALUATED or attempt.evaluation is None:
            raise AttemptNotFound(
                f"session {session_id!r} seq {sequence}: not evaluated yet"
            )

        spec = get_archetype(attempt.archetype_id)
        stored = attempt.evaluation
        eval_result = EvaluationResult(
            raw_score=float(stored.raw_score),
            rubric_scores=dict(stored.rubric_scores or {}),
            evaluator_notes=stored.evaluator_notes,
        )
        file_overrides = self._file_overrides_for_day(session.day_id)
        fb = await self._generate_feedback_bounded(
            spec=spec,
            evaluation=eval_result,
            user_response=attempt.user_response,
            task_content=attempt.task_content,
            feedback_overrides=file_overrides.get("feedback") or None,
            learner_history=None,
        )

        mistakes_payload = [
            {
                "issue": m.issue,
                "user_wrote": m.user_wrote,
                "correction": m.correction,
                "rule": m.rule,
                "sub_skills_affected": list(m.sub_skills_affected),
            }
            for m in fb.mistakes
        ]
        feedback = attempt.feedback
        if feedback is None:
            feedback = ActivityFeedback(attempt_id=attempt.id)
            self.feedback_repo.add(feedback)
        feedback.score = fb.score
        feedback.summary = fb.summary
        feedback.did_well = list(fb.did_well)
        feedback.mistakes = mistakes_payload
        feedback.next_tip = fb.next_tip
        feedback.sub_skill_breakdown = dict(fb.sub_skill_breakdown)

        self.db.commit()
        self.db.refresh(feedback)
        return feedback

    # ── complete ───────────────────────────────────────────────────

    async def complete_session(
        self,
        *,
        session_id: str,
        user_id: int,
        now: datetime | None = None,
    ) -> tuple[SessionScorecard, ApplyReport]:
        """Aggregate evaluations, persist scorecard, apply points (if first attempt).

        Semi-idempotent: calling `complete` twice on an already-COMPLETED session
        returns the existing scorecard — UNLESS the current attempt evaluations
        differ from the stored scorecard activities (e.g. after a session restart
        where scores were re-evaluated). In that case the stale scorecard is
        deleted and rebuilt so the scorecard always reflects the latest scores.
        """
        now = now or datetime.now(timezone.utc)
        session = self._load_owned(session_id=session_id, user_id=user_id)

        if session.status is SessionStatus.ABANDONED:
            raise SessionAbandoned(f"session {session_id!r} was abandoned")

        # Track whether a prior scorecard had already applied points.
        # Set to True in the COMPLETED rebuild path to prevent double-counting.
        old_points_applied: bool = False

        existing = self.scorecards_repo.get_for_session(session.id)

        if existing is not None:
            if session.status is SessionStatus.COMPLETED:
                # Check whether any attempt evaluation score has changed since the
                # scorecard was built.
                current_attempts = self.attempts_repo.list_for_session(session.id)
                stored_scores: dict[int, float] = {
                    a["attempt_id"]: float(a["raw_score"])
                    for a in (existing.activities or [])
                    if isinstance(a, dict)
                }
                scores_changed = False
                for att in current_attempts:
                    if (
                        att.status is not AttemptStatus.EVALUATED
                        or att.evaluation is None
                    ):
                        continue
                    current_raw = float(att.evaluation.raw_score)
                    stored_raw = stored_scores.get(att.id)
                    if stored_raw is None or abs(current_raw - stored_raw) > 0.05:
                        scores_changed = True
                        break

                if not scores_changed:
                    return existing, ApplyReport(
                        applied=False,
                        rows_written=0,
                        rows_skipped=0,
                        reason="session already completed",
                    )

                log.info(
                    "complete_session_rebuilding_stale_scorecard",
                    session_id=session_id,
                )

            # We either have an IN_PROGRESS session that was previously completed
            # (restarted) OR a COMPLETED session with stale scores. Delete to rebuild.
            old_points_applied = existing.points_applied
            self.db.delete(existing)
            self.db.flush()
            # Re-open the session so it can be completed again.
            session.status = SessionStatus.IN_PROGRESS

        # If the prior scorecard was already deleted on a reopen (per-activity
        # reset or full restart drop the scorecard, not the append-only points
        # log), the `existing` row is gone but the log still proves points were
        # awarded for this session. Treat that as already-applied so a
        # re-completion rebuilds the scorecard with the new scores WITHOUT
        # awarding a second batch of points.
        if not old_points_applied and self.points_log_repo.has_for_session(session.id):
            old_points_applied = True

        # Build ActivityScore list from every EVALUATED attempt.
        attempts = self.attempts_repo.list_for_session(session.id)
        scored: list[ActivityScore] = []
        activities_breakdown: list[dict] = []
        for attempt in attempts:
            if attempt.status is not AttemptStatus.EVALUATED:
                continue
            if attempt.evaluation is None:
                continue
            spec = get_archetype(attempt.archetype_id)
            scored.append(
                ActivityScore(
                    archetype_id=attempt.archetype_id,
                    raw_score=float(attempt.evaluation.raw_score),
                    weight_map=dict(spec.weight_map),
                )
            )
            raw = float(attempt.evaluation.raw_score)
            activities_breakdown.append(
                {
                    "attempt_id": attempt.id,
                    "sequence": attempt.sequence,
                    "archetype_id": attempt.archetype_id,
                    "archetype_label": spec.name,
                    "raw_score": raw,
                    "tier": tier_for_score(raw).value,
                    "base_reward": int(attempt.evaluation.base_reward),
                    "weighted_points": {
                        k: float(v)
                        for k, v in dict(attempt.evaluation.weighted_points).items()
                    },
                }
            )

        current_totals = self._current_points_for(session.user_id)
        course_length = CourseLength(session.course_length)
        aggregation = build_session_aggregation(
            scored,
            course_length,
            current_totals=current_totals,
        )

        scorecard = SessionScorecard(
            session_id=session.id,
            points_earned=dict(aggregation.points_earned),
            subskill_totals_after=dict(aggregation.subskill_totals_after or {}),
            dashboard_after=dict(aggregation.dashboard_after or {}),
            activities=activities_breakdown,
            completed_at=now,
            points_applied=False,
        )
        # Surface a cross-process completion race (audit B4) deterministically:
        # add() flushes the insert, so a duplicate trips the unique constraint
        # on session_scorecards.session_id here — BEFORE we apply points —
        # rather than failing inside apply_session_scorecard's own flush. The
        # constraint — not the in-memory guard — is the source of truth, so two
        # workers completing the same session resolve to one scorecard with
        # points applied once.
        try:
            self.scorecards_repo.add(scorecard)
        except IntegrityError:
            self.db.rollback()
            winner = self.scorecards_repo.get_for_session(session.id)
            if winner is None:
                raise
            return winner, ApplyReport(
                applied=False,
                rows_written=0,
                rows_skipped=0,
                reason="session already completed (concurrent completion)",
            )

        # Flush so apply_session_scorecard sees committed scorecard + session state.
        # If we are rebuilding a scorecard that already had its points applied
        # (e.g. after a session restart where scores improved), skip re-applying
        # to avoid double-counting points in SkillPoints.
        if old_points_applied:
            report = ApplyReport(
                applied=False,
                rows_written=0,
                rows_skipped=0,
                reason="rebuilt scorecard — points already applied from first completion",
            )
            scorecard.points_applied = True  # preserve applied status
        else:
            report = apply_session_scorecard(
                self.db, session=session, scorecard=scorecard
            )
            scorecard.points_applied = report.applied

        # The Coach's Note is NOT generated here. Completion stays fast and the
        # scorecard is committed with mentor_note=None; the note is produced by
        # the explicit, awaited ``ensure_mentor_note`` step (owned by the chat WS
        # / REST completion path) so it can be delivered to the client in-band
        # instead of racing a hard inline timeout. See ensure_mentor_note.
        session.status = SessionStatus.COMPLETED
        session.completed_at = now
        self._mark_course_complete_if_final(session=session, now=now)

        try:
            self.db.commit()
        except IntegrityError:
            # Cross-process race (audit B4): another worker committed the
            # scorecard for this session first. The unique constraint on
            # session_scorecards.session_id is the source of truth — roll back
            # this duplicate (which also discards our points writes, since they
            # share the transaction) and return the winner's scorecard so
            # completion is idempotent across workers without an in-memory lock.
            self.db.rollback()
            winner = self.scorecards_repo.get_for_session(session.id)
            if winner is None:
                raise
            return winner, ApplyReport(
                applied=False,
                rows_written=0,
                rows_skipped=0,
                reason="session already completed (concurrent completion)",
            )
        self.db.refresh(scorecard)

        # Background (own DB session): index per-activity vectors only. The note
        # and the day-level summary vector are handled by ensure_mentor_note.
        if self._rag_service is not None:
            self._schedule_post_completion_rag(
                session_id=session.session_id,
                user_id=session.user_id,
            )

        return scorecard, report

    async def run_post_completion_rag(
        self,
        *,
        session_id: str,
        user_id: int,
    ) -> None:
        """Index per-activity feedback vectors after completion.

        Runs after ``complete_session`` has committed. The mentor note and the
        day-level session-summary vector are NOT produced here — they belong to
        ``ensure_mentor_note`` (the awaited, in-band delivery path). Never raises.
        """
        try:
            session = self._load_owned(session_id=session_id, user_id=user_id)
            scorecard = self.scorecards_repo.get_for_session(session.id)
            if scorecard is None:
                return

            attempts = self.attempts_repo.list_for_session(session.id)

            if self._rag_service is not None:
                for attempt in attempts:
                    if attempt.status is not AttemptStatus.EVALUATED:
                        continue
                    if attempt.feedback is None:
                        continue
                    await self._store_activity_memory_safe(
                        user_id=session.user_id,
                        session_id=session.id,
                        attempt_id=attempt.id,
                        archetype_id=attempt.archetype_id,
                        day_id=session.day_id,
                        feedback=attempt.feedback,
                        spec=get_archetype(attempt.archetype_id),
                    )

            self.db.commit()
        except Exception:
            log.warning(
                "post_completion_rag_pipeline_failed",
                session_id=session_id,
                exc_info=True,
            )
            capture_to_sentry()
            self.db.rollback()

    async def ensure_mentor_note(
        self,
        *,
        session_id: str,
        user_id: int,
    ) -> str | None:
        """Generate (if needed) and persist the Coach's Note for a session.

        Idempotent: if the scorecard already carries a note it is returned
        without re-invoking the LLM. Otherwise the note is generated, persisted
        alongside the day-level session-summary vector, committed, and returned.
        Safe to call from the awaited completion path (chat WS / REST) and from a
        write-only background fallback. Never raises.
        """
        try:
            session = self._load_owned(session_id=session_id, user_id=user_id)
            scorecard = self.scorecards_repo.get_for_session(session.id)
            if scorecard is None:
                return None
            if scorecard.mentor_note:
                return scorecard.mentor_note
            if self._rag_service is None or self._mentor_generator is None:
                return None

            activities_breakdown = [
                dict(item)
                for item in (scorecard.activities or [])
                if isinstance(item, dict)
            ]
            mentor_note = await self._generate_mentor_note_safe(
                session=session,
                activities_breakdown=activities_breakdown,
                scorecard_id=scorecard.id,
            )
            if not mentor_note:
                return None

            scorecard.mentor_note = mentor_note
            # Day-level summary vector depends on the note, so it is stored here
            # rather than in the activity-indexing worker. Idempotent.
            await self._store_session_memory_safe(
                user_id=session.user_id,
                session_id=session.id,
                day_id=session.day_id,
                activities_summary=activities_breakdown,
                points_earned={
                    k: int(v) for k, v in dict(scorecard.points_earned or {}).items()
                },
                mentor_note=mentor_note,
            )
            self.db.commit()
            return mentor_note
        except Exception:
            log.warning(
                "ensure_mentor_note_failed",
                session_id=session_id,
                exc_info=True,
            )
            self.db.rollback()
            return None

    def _schedule_post_completion_rag(
        self,
        *,
        session_id: str,
        user_id: int,
    ) -> None:
        """Fire-and-forget mentor note + RAG indexing after completion commit."""
        task = asyncio.create_task(
            _run_post_completion_rag_worker(
                session_id=session_id,
                user_id=user_id,
            )
        )
        self._pending_rag_tasks.append(task)
        task.add_done_callback(self._discard_pending_rag_task)

    def _schedule_rag_delete(
        self,
        *,
        attempt_ids: list[int],
        session_pk: int,
        delete_summary: bool,
    ) -> None:
        """Fire-and-forget Pinecone/Postgres-mirror vector cleanup after a reset.

        Runs on its own DB session (the delete also touches the Postgres mirror),
        so it never shares the request-scoped ``self.db`` and never blocks the
        reset/restart commit. Best-effort: failures are logged, never raised.
        """
        task = asyncio.create_task(
            _run_rag_delete_worker(
                attempt_ids=list(attempt_ids),
                session_pk=session_pk,
                delete_summary=delete_summary,
            )
        )
        self._pending_rag_tasks.append(task)
        task.add_done_callback(self._discard_pending_rag_task)

    def _schedule_ai_eval(
        self,
        *,
        trace_id: str | None,
        user_id: int,
        target_id: str,
        task_content: dict,
        user_response: dict,
        feedback: dict,
    ) -> None:
        """Fire-and-forget LLM-as-judge quality scoring of one feedback output.

        Runs on its own DB session so it never shares the request/WebSocket
        ``self.db`` (same hazard as the RAG workers). Pure observability — the
        worker writes one ``ai_evaluations`` row and is best-effort; a judge
        failure is logged and dropped, never surfaced to the learner.
        """
        task = asyncio.create_task(
            _run_ai_eval_worker(
                trace_id=trace_id,
                user_id=user_id,
                target_id=target_id,
                task_content=task_content,
                user_response=user_response,
                feedback=feedback,
            )
        )
        self._pending_rag_tasks.append(task)
        task.add_done_callback(self._discard_pending_rag_task)

    def _schedule_mentor_note_eval(
        self,
        *,
        trace_id: str | None,
        user_id: int,
        target_id: str,
        note: str,
        rag_context: dict,
        today_activities: list[dict],
    ) -> None:
        """Fire-and-forget RAG-faithfulness judging of one mentor note.

        Runs on its own DB session (never shares ``self.db``) and is
        best-effort — the worker writes one ``ai_evaluations`` row
        (``target_type="mentor_note"``, with a ``faithfulness`` score) and a
        judge failure is logged and dropped, never surfaced to the learner.
        """
        task = asyncio.create_task(
            _run_mentor_note_eval_worker(
                trace_id=trace_id,
                user_id=user_id,
                target_id=target_id,
                note=note,
                rag_context=rag_context,
                today_activities=today_activities,
            )
        )
        self._pending_rag_tasks.append(task)
        task.add_done_callback(self._discard_pending_rag_task)

    def _discard_pending_rag_task(self, task: asyncio.Task[None]) -> None:
        try:
            self._pending_rag_tasks.remove(task)
        except ValueError:
            pass
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            log.warning(
                "post_completion_rag_background_task_failed",
                exc_info=exc,
            )

    # ── read ───────────────────────────────────────────────────────

    def get_scorecard(
        self, *, session_id: str, user_id: int
    ) -> SessionScorecard | None:
        session = self._load_owned(session_id=session_id, user_id=user_id)
        return self.scorecards_repo.get_for_session(session.id)

    def get_session(self, *, session_id: str, user_id: int) -> DailySession:
        return self._load_owned(session_id=session_id, user_id=user_id)

    # ── reset ──────────────────────────────────────────────────────

    async def reset_activity(
        self,
        *,
        session_id: str,
        user_id: int,
        sequence: int,
    ) -> ActivityAttempt:
        """Reset a single activity so it can be re-attempted.

        Deletes the attempt's evaluation + feedback and flips it back to
        PENDING (clearing the stored response). If the daily session was
        already COMPLETED, it is reopened (status → IN_PROGRESS, completed_at
        cleared) and its now-stale scorecard is deleted; the scorecard is
        rebuilt the next time the session is completed.

        Also purges the attempt's RAG memory vector (and the now-stale
        session-summary vector if the session was completed) so Pinecone
        stays in sync with Postgres. The RAG cleanup is additive and never
        blocks the reset.
        """
        session = self._load_owned(session_id=session_id, user_id=user_id)
        if session.status is SessionStatus.ABANDONED:
            raise SessionAbandoned(f"session {session_id!r} was abandoned")

        attempt = self.attempts_repo.get(session_pk=session.id, sequence=sequence)
        if attempt is None:
            raise AttemptNotFound(
                f"session {session_id!r}: no attempt at sequence {sequence}"
            )

        was_completed = session.status is SessionStatus.COMPLETED
        attempt_id = attempt.id
        session_pk = session.id

        self.evaluations_repo.delete_for_attempt(attempt.id)
        self.feedback_repo.delete_for_attempt(attempt.id)
        self.attempts_repo.reset_to_pending(attempt)

        if was_completed:
            self.scorecards_repo.delete_for_session(session.id)
            session.status = SessionStatus.IN_PROGRESS
            session.completed_at = None

        # Commit the V2 reset immediately so per-activity retry never waits on
        # Pinecone. Vector cleanup (which also touches the Postgres mirror) is
        # scheduled fire-and-forget on its own DB session afterwards.
        self.db.commit()
        self.db.refresh(attempt)

        if self._rag_service is not None:
            self._schedule_rag_delete(
                attempt_ids=[attempt_id],
                session_pk=session_pk,
                delete_summary=was_completed,
            )

        return attempt

    async def reset_session_full(
        self,
        *,
        session_id: str,
        user_id: int,
    ) -> DailySession:
        """Reset every activity in the day so it can be re-attempted from scratch.

        Deletes each attempt's evaluation + feedback, flips all attempts back to
        PENDING (clearing stored responses), deletes the SessionScorecard, and
        reopens the DailySession (status → IN_PROGRESS, completed_at cleared).
        The scorecard is rebuilt the next time the day is completed.

        Owns its commit so callers (e.g. the chat-layer ``restart_session``)
        don't have to duplicate V2 deletes. RAG vector cleanup is additive,
        runs in the background, and never blocks the restart.
        """
        session = self._load_owned(session_id=session_id, user_id=user_id)
        if session.status is SessionStatus.ABANDONED:
            raise SessionAbandoned(f"session {session_id!r} was abandoned")

        session_pk = session.id
        attempts = self.attempts_repo.list_for_session(session.id)
        attempt_ids = [attempt.id for attempt in attempts]

        for attempt in attempts:
            self.evaluations_repo.delete_for_attempt(attempt.id)
            self.feedback_repo.delete_for_attempt(attempt.id)
            self.attempts_repo.reset_to_pending(attempt)

        self.scorecards_repo.delete_for_session(session.id)
        session.status = SessionStatus.IN_PROGRESS
        session.completed_at = None

        # Commit the V2 reset immediately so restart never waits on Pinecone.
        self.db.commit()
        self.db.refresh(session)

        if self._rag_service is not None and attempt_ids:
            self._schedule_rag_delete(
                attempt_ids=attempt_ids,
                session_pk=session_pk,
                delete_summary=True,
            )

        return session

    # ── advance day ────────────────────────────────────────────────

    def _mark_course_complete_if_final(
        self, *, session: DailySession, now: datetime
    ) -> None:
        """Stamp ``course_completed_at`` the first time a learner finishes the
        final day of their course.

        Fires only when the just-completed session is genuinely the learner's
        final curriculum day (week == ``max_week``, day 7) AND their progress
        pointer is actually parked there. The pointer check is what makes a
        *preview/override* completion of the final day safe: a learner sitting
        at week 3 who previews week 24/day 7 completes that session, but their
        pointer is not at the end, so this never false-triggers.

        Idempotent: once set, the timestamp is never moved, so a final-day
        restart/replay (which re-runs ``complete_session``) is a no-op here.

        A pure read — no flush/commit — so it never disturbs the surrounding
        completion transaction. Every real learner has a preference row (it is
        the source of truth for ``current_week``/``current_day``); if it is
        somehow absent we simply cannot place the learner, so we no-op.
        """
        pref = self.preferences_repo.get_for_user(session.user_id)
        if pref is None or pref.course_completed_at is not None:
            return
        if session.course_length != pref.course_length:
            return
        try:
            _, session_week, session_day = parse_day_id(session.day_id)
        except ValueError:
            return

        weeks = self.weeks_repo.list_for_course(pref.course_length)
        course_cap = 24 if pref.course_length == "24w" else 48
        max_week = min(max((w.week_number for w in weeks), default=0), course_cap)
        if max_week <= 0:
            return

        is_final_day = session_week >= max_week and session_day >= 7
        pointer_at_final = (
            pref.current_week >= max_week and pref.current_day_in_week >= 7
        )
        if is_final_day and pointer_at_final:
            pref.course_completed_at = now

    def advance_day(self, *, user_id: int) -> tuple[int, int]:
        """Move the learner's preference pointer to the next unlocked day."""
        pref = self.preferences_repo.get_or_create_for_user(user_id)
        week = self.weeks_repo.get_by_number(
            course_length=pref.course_length,
            week_number=pref.current_week,
        )
        if week is None:
            raise DayNotFound(
                f"No curriculum week for course_length={pref.course_length!r} "
                f"week={pref.current_week}"
            )

        day = self.days_repo.get_for_week(
            week_pk=week.id,
            day_number=pref.current_day_in_week,
        )
        if day is None:
            raise DayNotFound(
                f"No curriculum day for week_id={week.week_id!r} "
                f"day={pref.current_day_in_week}"
            )

        latest = self.sessions_repo.get_latest_for_day(
            user_id=user_id,
            day_id=day.day_id,
        )
        if latest is None or latest.status is not SessionStatus.COMPLETED:
            raise SessionAdvanceBlocked(
                "Complete today's session before unlocking the next day."
            )

        weeks = self.weeks_repo.list_for_course(pref.course_length)
        course_cap = 24 if pref.course_length == "24w" else 48
        max_week = min(max((w.week_number for w in weeks), default=0), course_cap)
        if max_week <= 0:
            raise DayNotFound(
                f"No curriculum weeks for course_length={pref.course_length!r}"
            )
        if pref.current_week >= max_week and pref.current_day_in_week >= 7:
            raise SessionAdvanceBlocked("You are already at the final course day.")

        # Pre-flight: verify the target position exists before committing.
        if pref.current_day_in_week >= 7:
            next_week_num = pref.current_week + 1
            next_week_row = self.weeks_repo.get_by_number(
                course_length=pref.course_length,
                week_number=next_week_num,
            )
            if next_week_row is None:
                raise DayNotFound(
                    f"Cannot advance: week {next_week_num} is not seeded for "
                    f"course_length={pref.course_length!r}"
                )
            next_day_row = self.days_repo.get_for_week(
                week_pk=next_week_row.id,
                day_number=1,
            )
            if next_day_row is None:
                raise DayNotFound(
                    f"Cannot advance: day 1 not seeded for week {next_week_num}"
                )

        now = datetime.now(timezone.utc)
        if pref.current_day_in_week >= 7:
            pref.current_week += 1
            pref.current_day_in_week = 1
        else:
            pref.current_day_in_week += 1
        pref.current_day_started_at = now
        pref.last_completed_on = now.date()

        self.db.commit()
        self.db.refresh(pref)
        return pref.current_week, pref.current_day_in_week

    # ── helpers ────────────────────────────────────────────────────

    def _load_owned(self, *, session_id: str, user_id: int) -> DailySession:
        session = self.sessions_repo.get_by_session_id(session_id)
        if session is None or session.user_id != user_id:
            raise SessionNotFound(f"session {session_id!r} not found")
        return session

    @staticmethod
    def _guard_open(session: DailySession) -> None:
        if session.status is SessionStatus.COMPLETED:
            raise SessionAlreadyCompleted(
                f"session {session.session_id!r} already completed"
            )
        if session.status is SessionStatus.ABANDONED:
            raise SessionAbandoned(f"session {session.session_id!r} was abandoned")

    async def _generate_attempt_content(
        self,
        *,
        day_topic: str,
        explanation_brief: str,
        archetype_id: str,
        sequence: int,
        is_mandatory: bool,
        cefr_level: str,
        sub_level: int,
        user_interests: list[str] | None,
        task_spec: dict | None = None,
    ) -> dict:
        """Generate an attempt's task_content (LLM/TTS/imagegen).

        No DB access — safe to run concurrently for several activities.
        """
        spec = get_archetype(archetype_id)
        _validate_agent_input(
            TaskGenAgentInput,
            archetype_id=archetype_id,
            day_topic=day_topic,
            explanation_brief=explanation_brief,
            cefr_level=cefr_level,
            sub_level=sub_level,
            task_spec=task_spec or {},
        )
        generated = await self.task_generator.generate(
            archetype=spec,
            day_topic=day_topic,
            explanation_brief=explanation_brief,
            cefr_level=cefr_level,
            sub_level=sub_level,
            user_interests=user_interests,
            task_spec=task_spec,
        )
        return self._attach_activity_contract(
            content=dict(generated.content),
            archetype=spec,
            sequence=sequence,
            is_mandatory=is_mandatory,
            task_spec=task_spec,
        )

    # ── lazy task generation ───────────────────────────────────────

    def _pending_task_content(self, item: dict) -> dict:
        """Build a placeholder ``task_content`` for an as-yet-ungenerated attempt.

        Carries the deterministic activity contract (so the blueprint and the
        position-reserving skeletons resolve without an LLM call) plus the
        generation recipe under ``__pending_taskgen``. Replaced wholesale by
        ``ensure_attempt_content`` when the real content is generated.
        """
        spec = get_archetype(item["archetype_id"])
        content = self._attach_activity_contract(
            content={},
            archetype=spec,
            sequence=item["sequence"],
            is_mandatory=item["is_mandatory"],
            task_spec=item.get("task_spec"),
        )
        content["__pending_taskgen"] = dict(item)
        content["widget"] = spec.ui_widget
        return content

    async def ensure_attempt_content(self, attempt: ActivityAttempt) -> ActivityAttempt:
        """Turn a lazy-gen placeholder into real generated content.

        No-op unless the attempt is still ``PENDING`` and still carries a
        ``__pending_taskgen`` recipe. This is the single place that fills a
        placeholder — used by the background worker (``fill_pending_task_content``)
        and on demand by ``prepare_attempt_for_delivery`` when the learner
        reaches a task the worker hasn't filled yet.
        """
        recipe = (attempt.task_content or {}).get("__pending_taskgen")
        if not isinstance(recipe, dict) or attempt.status is not AttemptStatus.PENDING:
            return attempt

        generated = await self._generate_attempt_content(**recipe)

        # The re-read + assign + commit + refresh below is one synchronous
        # critical section (no ``await``), so concurrent fills of *different*
        # attempts on this same DB session can't interleave. Re-read first: a
        # separate DB session (the learner submitting) may have advanced this
        # attempt while we were generating — never clobber graded content.
        self.db.refresh(attempt)
        recipe_after = (attempt.task_content or {}).get("__pending_taskgen")
        if not isinstance(recipe_after, dict) or attempt.status is not (
            AttemptStatus.PENDING
        ):
            return attempt
        attempt.task_content = generated
        self.db.commit()
        self.db.refresh(attempt)
        return attempt

    async def fill_pending_task_content(self, *, session_id: str, user_id: int) -> None:
        """Generate real content for every placeholder attempt of a session.

        Runs in the background right after ``start_session`` (on its own DB
        session — see ``_run_lazy_taskgen_worker``). Generations run concurrently
        under the ``_TASKGEN_CONCURRENCY`` semaphore; each attempt is committed
        independently by ``ensure_attempt_content``. Best-effort: a single
        attempt's failure is logged and skipped — the on-demand delivery seam
        regenerates anything the worker missed.
        """
        session = self._load_owned(session_id=session_id, user_id=user_id)
        pending = [
            attempt
            for attempt in self.attempts_repo.list_for_session(session.id)
            if attempt.status is AttemptStatus.PENDING
            and isinstance((attempt.task_content or {}).get("__pending_taskgen"), dict)
        ]
        if not pending:
            return

        sem = asyncio.Semaphore(_TASKGEN_CONCURRENCY)

        async def _fill(attempt: ActivityAttempt) -> None:
            async with sem:
                await self.ensure_attempt_content(attempt)

        results = await asyncio.gather(
            *(_fill(attempt) for attempt in pending),
            return_exceptions=True,
        )
        failed = sum(1 for r in results if isinstance(r, BaseException))
        if failed:
            log.warning(
                "lazy_taskgen_partial",
                session_id=session_id,
                failed=failed,
                total=len(pending),
            )

    def _schedule_lazy_taskgen(self, *, session_id: str, user_id: int) -> None:
        """Fire-and-forget background fill of placeholder task content.

        Mirrors ``_schedule_post_completion_rag``: the worker opens a fresh
        ``SessionLocal`` (never touches the request/WebSocket ``self.db``) and
        reuses the *same* injected agents, so test stubs stay in force.
        """
        task = asyncio.create_task(
            _run_lazy_taskgen_worker(
                session_id=session_id,
                user_id=user_id,
                evaluator=self.evaluator,
                feedback_generator=self.feedback_generator,
                task_generator=self.task_generator,
            )
        )
        self._pending_rag_tasks.append(task)
        task.add_done_callback(self._discard_pending_rag_task)

    def _persist_attempt(
        self,
        *,
        session: DailySession,
        archetype_id: str,
        sequence: int,
        is_mandatory: bool,
        content: dict,
    ) -> ActivityAttempt:
        attempt = ActivityAttempt(
            session_id=session.id,
            archetype_id=archetype_id,
            sequence=sequence,
            is_mandatory=is_mandatory,
            status=AttemptStatus.PENDING,
            task_content=content,
        )
        self.db.add(attempt)
        self.db.flush()
        return attempt

    @staticmethod
    def _attach_activity_contract(
        *,
        content: dict,
        archetype: ArchetypeSpec,
        sequence: int,
        is_mandatory: bool,
        task_spec: dict | None,
    ) -> dict:
        """Persist deterministic blueprint metadata beside generated content."""

        spec = task_spec or {}
        contract = {
            "activity_id": spec.get("activity_id"),
            "sequence": sequence,
            "archetype_id": archetype.archetype_id,
            "activity": spec.get("activity") or archetype.core_activity,
            "task_widget": spec.get("task_widget")
            or content.get("widget")
            or content.get("ui_widget")
            or archetype.ui_widget,
            "evaluator_type": spec.get("evaluator_type") or "default",
            "evaluation_widget": spec.get("evaluation_widget") or "activity_score",
            "feedback_type": spec.get("feedback_type") or "default",
            "feedback_widget": spec.get("feedback_widget") or "feedback_card",
            "mandatory": bool(spec.get("mandatory", is_mandatory)),
        }
        contract = {
            key: value for key, value in contract.items() if value not in (None, "", {})
        }
        content["activity_contract"] = contract
        content.setdefault("task_widget", contract["task_widget"])
        content.setdefault("evaluator_type", contract["evaluator_type"])
        content.setdefault("evaluation_widget", contract["evaluation_widget"])
        content.setdefault("feedback_type", contract["feedback_type"])
        content.setdefault("feedback_widget", contract["feedback_widget"])
        if contract.get("activity_id") is not None:
            content.setdefault("activity_id", contract["activity_id"])
        return content

    def _current_points_for(self, user_id: int) -> dict[str, int]:
        """Build `{sub_skill: int_points}` for the user, filling missing skills with 0."""
        id_to_name = {v: k for k, v in self.skills_repo.name_to_id_map().items()}
        out: dict[str, int] = {skill: 0 for skill in SUB_SKILLS}
        for row in self.points_repo.get_all_for_user(user_id):
            name = id_to_name.get(row.skill_id)
            if name in out:
                out[name] = int(row.points)
        return out

    @staticmethod
    def _file_overrides_for_day(day_id: str) -> dict[str, dict]:
        """Return evaluator/feedback overrides from the file-authored day, if any.

        Returns ``{"evaluator": {...}, "feedback": {...}}`` when the day is
        file-authored (24w/48w, resolved via ``file_source``) and has non-empty
        override dicts. Returns ``{}`` for non-authored days or when
        ``file_source`` raises.
        """
        try:
            file_day = file_get_day_by_id(day_id)
        except DayNotFound:
            return {}
        result: dict[str, dict] = {}
        if file_day.evaluator_overrides:
            result["evaluator"] = dict(file_day.evaluator_overrides)
        if file_day.feedback_overrides:
            result["feedback"] = dict(file_day.feedback_overrides)
        return result

    # ── RAG helpers (fire-and-forget) ──────────────────────────────

    async def _store_activity_memory_safe(
        self,
        *,
        user_id: int,
        session_id: int,
        attempt_id: int,
        archetype_id: str,
        day_id: str,
        feedback: Any,
        spec: Any,
    ) -> None:
        """Store activity feedback in RAG memory. Never raises."""
        try:
            if self._rag_service is None:
                return
            await self._rag_service.store_activity_feedback(
                user_id=user_id,
                session_id=session_id,
                attempt_id=attempt_id,
                archetype_id=archetype_id,
                archetype_name=spec.name,
                day_id=day_id,
                score=feedback.score,
                mistakes=list(feedback.mistakes or []),
                did_well=list(feedback.did_well or []),
                next_tip=feedback.next_tip,
                summary=feedback.summary,
            )
        except Exception:
            log.warning(
                "store_activity_memory_failed",
                attempt_id=attempt_id,
                exc_info=True,
            )

    async def _store_session_memory_safe(
        self,
        *,
        user_id: int,
        session_id: int,
        day_id: str,
        activities_summary: list[dict],
        points_earned: dict[str, int],
        mentor_note: str,
    ) -> None:
        """Store session summary in RAG memory. Never raises."""
        try:
            if self._rag_service is None:
                return
            await self._rag_service.store_session_summary(
                user_id=user_id,
                session_id=session_id,
                day_id=day_id,
                activities_summary=activities_summary,
                points_earned=points_earned,
                mentor_note=mentor_note,
            )
        except Exception:
            log.warning(
                "store_session_memory_failed",
                session_id=session_id,
                exc_info=True,
            )

    async def _generate_mentor_note_safe(
        self,
        *,
        session: DailySession,
        activities_breakdown: list[dict],
        scorecard_id: int | None = None,
    ) -> str | None:
        """Retrieve RAG context and generate mentor note. Never raises.

        Returns None on any failure — scorecard is still returned.
        """
        if self._rag_service is None or self._mentor_generator is None:
            return None

        # Stamp a trace so the mentor-note LLM call is recorded with the learner
        # in ai_request_logs. Runs in a background worker with its own context.
        trace_id = uuid4().hex
        token = set_eval_context(trace_id=trace_id, user_id=session.user_id)
        try:
            # Collect today's mistakes from all attempts
            attempts = self.attempts_repo.list_for_session(session.id)
            today_mistakes: list[dict] = []
            for attempt in attempts:
                if attempt.feedback is not None:
                    today_mistakes.extend(attempt.feedback.mistakes or [])

            # Retrieve RAG context
            rag_context = await self._rag_service.retrieve_context_for_feedback(
                user_id=session.user_id,
                current_mistakes=today_mistakes,
                current_day_id=session.day_id,
                current_session_id=session.id,
            )

            # Collect points earned from activities_breakdown
            points_earned: dict[str, int] = {}
            for act in activities_breakdown:
                for skill, pts in act.get("weighted_points", {}).items():
                    points_earned[skill] = points_earned.get(skill, 0) + int(pts)

            # Generate mentor note
            mentor_note = await self._mentor_generator.generate(
                today_activities=activities_breakdown,
                today_mistakes=today_mistakes,
                rag_context=rag_context,
                points_earned=points_earned,
            )

            # RAG faithfulness judging (Part B Phase 3). Fire-and-forget on a
            # sample, only when a note was actually produced and we have the
            # scorecard id to key the eval to. Pure observability — runs on its
            # own DB session, shares the mentor-note trace_id, never blocks.
            if (
                mentor_note
                and scorecard_id is not None
                and settings.AI_EVAL_ENABLED
                and random.random() < settings.AI_EVAL_MENTOR_SAMPLE_RATE
            ):
                self._schedule_mentor_note_eval(
                    trace_id=trace_id,
                    user_id=session.user_id,
                    target_id=str(scorecard_id),
                    note=mentor_note,
                    rag_context=dict(rag_context or {}),
                    today_activities=activities_breakdown,
                )

            return mentor_note

        except Exception:
            log.warning(
                "mentor_note_generation_failed",
                session_id=session.session_id,
                exc_info=True,
            )
            return None
        finally:
            reset_eval_context(token)


async def _run_post_completion_rag_worker(
    *,
    session_id: str,
    user_id: int,
) -> None:
    """Background worker with its own DB session for post-completion RAG."""
    from app.core.database import SessionLocal
    from app.modules.sessions.routes import _make_session_service

    db = SessionLocal()
    try:
        service = _make_session_service(db)
        await service.run_post_completion_rag(
            session_id=session_id,
            user_id=user_id,
        )
    except Exception:
        log.warning(
            "post_completion_rag_worker_failed",
            session_id=session_id,
            exc_info=True,
        )
        db.rollback()
    finally:
        db.close()


async def _run_lazy_taskgen_worker(
    *,
    session_id: str,
    user_id: int,
    evaluator: Evaluator,
    feedback_generator: FeedbackGenerator,
    task_generator: TaskGenerator,
) -> None:
    """Background worker (own DB session) that fills placeholder task content.

    Reuses the *same* injected agents as the scheduling service (so test stubs
    stay in force) but on a fresh ``SessionLocal`` — the request/WebSocket
    ``self.db`` must never be touched from a background task. Best-effort: a
    failure is logged and dropped; the on-demand delivery seam covers any gap.
    """
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        service = SessionService(
            db,
            evaluator=evaluator,
            feedback_generator=feedback_generator,
            task_generator=task_generator,
        )
        await service.fill_pending_task_content(
            session_id=session_id,
            user_id=user_id,
        )
    except Exception:
        log.warning(
            "lazy_taskgen_worker_failed",
            session_id=session_id,
            exc_info=True,
        )
        db.rollback()
    finally:
        db.close()


async def _run_ai_eval_worker(
    *,
    trace_id: str | None,
    user_id: int,
    target_id: str,
    task_content: dict,
    user_response: dict,
    feedback: dict,
) -> None:
    """Background worker (own DB session) that judges one feedback output.

    Opens a fresh ``SessionLocal``, re-stamps the eval context with the same
    ``trace_id`` so the judge's own ``ai_request_logs`` row joins the feedback
    call, runs the judge under a timeout, and writes one ``ai_evaluations`` row
    (``target_type="feedback"``, ``eval_mode="online"``). Never raises — quality
    scoring is observability and must never affect the learner.
    """
    from app.ai.sessions.factory import build_judge
    from app.core.database import SessionLocal
    from app.modules.admin.models import AIEvaluation

    token = set_eval_context(trace_id=trace_id, user_id=user_id)
    db = SessionLocal()
    try:
        judge = build_judge()
        scores = await asyncio.wait_for(
            judge.score(
                task=task_content,
                user_answer=user_response,
                feedback=feedback,
            ),
            timeout=settings.AI_EVAL_TIMEOUT_S,
        )
        db.add(
            AIEvaluation(
                trace_id=trace_id,
                target_type="feedback",
                target_id=target_id,
                judge_model=settings.AI_EVAL_JUDGE_MODEL,
                accuracy=scores.accuracy,
                relevance=scores.relevance,
                helpfulness=scores.helpfulness,
                correctness=scores.correctness,
                faithfulness=None,
                rationale=(scores.rationale or "")[:1000] or None,
                eval_mode="online",
            )
        )
        db.commit()
    except Exception:
        log.warning(
            "ai_quality_judge_failed",
            target_type="feedback",
            target_id=target_id,
            exc_info=True,
        )
        db.rollback()
    finally:
        db.close()
        reset_eval_context(token)


async def _run_mentor_note_eval_worker(
    *,
    trace_id: str | None,
    user_id: int,
    target_id: str,
    note: str,
    rag_context: dict,
    today_activities: list[dict],
) -> None:
    """Background worker (own DB session) that judges one mentor note for RAG
    faithfulness (Part B Phase 3).

    Opens a fresh ``SessionLocal``, re-stamps the eval context with the same
    ``trace_id`` so the judge's own ``ai_request_logs`` row joins the
    mentor-note call, runs the judge under a timeout, and writes one
    ``ai_evaluations`` row (``target_type="mentor_note"``, ``eval_mode="online"``,
    with the RAG-specific ``faithfulness`` score). Never raises — quality
    scoring is observability and must never affect the learner.
    """
    from app.ai.sessions.factory import build_mentor_judge
    from app.core.database import SessionLocal
    from app.modules.admin.models import AIEvaluation

    token = set_eval_context(trace_id=trace_id, user_id=user_id)
    db = SessionLocal()
    try:
        judge = build_mentor_judge()
        scores = await asyncio.wait_for(
            judge.score(
                note=note,
                rag_context=rag_context,
                today_activities=today_activities,
            ),
            timeout=settings.AI_EVAL_TIMEOUT_S,
        )
        db.add(
            AIEvaluation(
                trace_id=trace_id,
                target_type="mentor_note",
                target_id=target_id,
                judge_model=settings.AI_EVAL_JUDGE_MODEL,
                accuracy=scores.accuracy,
                relevance=scores.relevance,
                helpfulness=scores.helpfulness,
                correctness=scores.correctness,
                faithfulness=scores.faithfulness,
                rationale=(scores.rationale or "")[:1000] or None,
                eval_mode="online",
            )
        )
        db.commit()
    except Exception:
        log.warning(
            "ai_quality_judge_failed",
            target_type="mentor_note",
            target_id=target_id,
            exc_info=True,
        )
        db.rollback()
    finally:
        db.close()
        reset_eval_context(token)


async def generate_mentor_note_async(
    *,
    session_id: str,
    user_id: int,
) -> str | None:
    """Ensure the Coach's Note on a dedicated DB session, off the request loop.

    Used both as the chat WS in-band generator (awaited under a ceiling via
    ``asyncio.shield`` so a timeout never cancels the DB work) and as the
    write-only fallback when that await times out — in either case the note is
    persisted for later scorecard/dashboard reads. Never raises.
    """
    from app.core.database import SessionLocal
    from app.modules.sessions.routes import _make_session_service

    db = SessionLocal()
    try:
        service = _make_session_service(db)
        return await service.ensure_mentor_note(
            session_id=session_id,
            user_id=user_id,
        )
    except Exception:
        log.warning(
            "mentor_note_worker_failed",
            session_id=session_id,
            exc_info=True,
        )
        db.rollback()
        return None
    finally:
        db.close()


async def _run_rag_delete_worker(
    *,
    attempt_ids: list[int],
    session_pk: int,
    delete_summary: bool,
) -> None:
    """Background worker (own DB session) that purges stale RAG vectors.

    Called fire-and-forget after a per-activity or full-session reset has
    committed. Removes the activity-feedback vector(s) for each reset attempt
    and, when the day was reopened, the now-stale session-summary vector.
    The underlying delete also writes the Postgres mirror, so it must run on a
    dedicated session rather than the request-scoped one. Never raises.
    """
    from app.core.database import SessionLocal
    from app.modules.sessions.routes import _make_session_service

    db = SessionLocal()
    try:
        service = _make_session_service(db)
        rag = service._rag_service
        if rag is None:
            return
        for attempt_id in attempt_ids:
            await rag.delete_for_attempt(attempt_id)
        if delete_summary:
            await rag.delete_session_summary(session_pk)
    except Exception:
        log.warning(
            "rag_delete_worker_failed",
            session_pk=session_pk,
            attempt_ids=attempt_ids,
            exc_info=True,
        )
        db.rollback()
    finally:
        db.close()
