"""HTTP + WebSocket endpoints for chat-driven learning sessions."""

from __future__ import annotations

import json
import logging

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token
from app.core.sentry import capture_to_sentry
from app.core.ai_rate_limit import RATE_LIMIT_MESSAGE, ai_rate_limit, get_limiter
from app.modules.subscriptions.dependencies import (
    WS_PAYMENT_REQUIRED,
    check_ws_access,
    require_active_access,
)
from app.core.config import settings
from app.modules.auth.dependencies import get_current_user, require_learner
from app.modules.auth.models import ROLE_LEARNER, ROLE_SUPER_ADMIN, User
from app.modules.auth.repository import UserRepository
from app.modules.learning_session.schemas import (
    LearningSessionSnapshotRead,
    LearningSessionStateRead,
    RegenerateFeedbackResponse,
    StartSessionRequest,
    StartSessionResponse,
    WSIncomingMessage,
    WSOutgoingMessage,
)

from app.modules.learning_session.service import (
    LearningSessionService,
    LearningSessionTaskUnavailable,
)
from app.ai.sessions.exceptions import TaskGenerationFailed
from app.modules.sessions.contracts.projection import ContractValidationError
from app.modules.sessions.exceptions import (
    AttemptNotFound,
    SessionNotFound,
)

logger = logging.getLogger(__name__)

# Surfaced to the dashboard so the "Start session" button can flip to a red
# "Retry session" affordance instead of a dead-end 500. See DailyTaskPanel.
TASK_GENERATION_FAILED_DETAIL = {
    "code": "task_generation_failed",
    "message": "We couldn't prepare today's lesson. Please try again.",
}

# Learner-facing copy for a mid-session task-generation/validation failure on the
# WebSocket flow. Replaces the raw pydantic/contract error string in the chat and
# pairs with `code="task_generation_failed"` so the client shows a retry icon.
TASK_REGEN_FAILED_CHAT_DETAIL = (
    "We couldn't prepare this activity. Tap the retry icon below to generate a "
    "fresh one."
)


# --- REST -------------------------------------------------------------

rest_router = APIRouter(
    prefix="/learning",
    tags=["learning_session"],
    dependencies=[Depends(require_learner)],
)


@rest_router.post(
    "/sessions/start",
    response_model=StartSessionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_active_access),
        Depends(ai_rate_limit("learning_start")),
    ],
)
async def start_session(
    payload: StartSessionRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StartSessionResponse:
    service = LearningSessionService(db)
    try:
        return await service.create_session(
            user_id=current_user.id,
            daily_session_id=payload.daily_session_id if payload else None,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LearningSessionTaskUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except TaskGenerationFailed as exc:
        # Transient: the LLM couldn't produce renderable content for an
        # activity after retries. Tell the client to retry rather than 500.
        logger.warning(
            "start_session task generation failed for user_id=%s: %s",
            current_user.id,
            exc,
        )
        raise HTTPException(
            status_code=503, detail=TASK_GENERATION_FAILED_DETAIL
        ) from exc
    except Exception as exc:  # pragma: no cover — unexpected
        logger.exception("start_session failed for user_id=%s", current_user.id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@rest_router.post(
    "/sessions/{session_id}/restart",
    response_model=StartSessionResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[
        Depends(require_active_access),
        Depends(ai_rate_limit("learning_start")),
    ],
)
async def restart_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StartSessionResponse:
    service = LearningSessionService(db)
    try:
        return await service.restart_session(
            session_id=session_id,
            user_id=current_user.id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover — unexpected
        logger.exception(
            "restart_session failed session_id=%s user_id=%s",
            session_id,
            current_user.id,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@rest_router.get(
    "/sessions/{session_id}/state",
    response_model=LearningSessionStateRead,
    status_code=status.HTTP_200_OK,
)
async def get_session_state(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LearningSessionStateRead:
    """Return everything the chat UI needs to render without the WebSocket.

    Used on mount to hydrate phase/messages/task_queue, the current actionable
    task, completed-activity summaries, and the resume checkpoint.

    Errors:
      404 — no chat session with this id belonging to the user
      403 — session belongs to another user
    """
    service = LearningSessionService(db)
    try:
        snapshot = await service.get_state_snapshot(
            session_id=session_id,
            user_id=current_user.id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return LearningSessionStateRead(**snapshot)


@rest_router.post(
    "/sessions/{session_id}/activities/{sequence}/reset",
    response_model=StartSessionResponse,
    status_code=status.HTTP_200_OK,
)
async def reset_activity(
    session_id: str,
    sequence: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StartSessionResponse:
    """Reset a single activity so the learner can retry it without restarting.

    Errors:
      404 — chat session or attempt not found
      403 — session belongs to another user
    """
    service = LearningSessionService(db)
    try:
        return await service.reset_activity(
            session_id=session_id,
            user_id=current_user.id,
            sequence=sequence,
        )
    except (LookupError, AttemptNotFound, SessionNotFound) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover — unexpected
        logger.exception(
            "reset_activity failed session_id=%s sequence=%s user_id=%s",
            session_id,
            sequence,
            current_user.id,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@rest_router.post(
    "/sessions/{session_id}/activities/{sequence}/regenerate-feedback",
    response_model=RegenerateFeedbackResponse,
    status_code=status.HTTP_200_OK,
)
async def regenerate_feedback(
    session_id: str,
    sequence: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RegenerateFeedbackResponse:
    """Re-generate feedback for one already-graded activity, in place.

    Reuses the stored evaluation — the score and graded response are untouched —
    and returns a fresh feedback card. Used by the chat "Regenerate feedback"
    action when the first generation fell back to a placeholder.

    Errors:
      404 — chat session or attempt not found, or the attempt isn't evaluated yet
      403 — session belongs to another user
    """
    service = LearningSessionService(db)
    try:
        feedback = await service.regenerate_feedback(
            session_id=session_id,
            user_id=current_user.id,
            sequence=sequence,
        )
    except (LookupError, AttemptNotFound, SessionNotFound) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover — unexpected
        logger.exception(
            "regenerate_feedback failed session_id=%s sequence=%s user_id=%s",
            session_id,
            sequence,
            current_user.id,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return RegenerateFeedbackResponse(sequence=sequence, feedback=feedback)


@rest_router.get(
    "/sessions/by-daily-session/{daily_session_id}",
    response_model=LearningSessionSnapshotRead,
    status_code=status.HTTP_200_OK,
)
def get_session_by_daily_session(
    daily_session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LearningSessionSnapshotRead:
    """Return the chat session linked to a given V2 DailySession (by int PK).

    Used for resume / history views that have the V2 session id but want
    the chat conversation snapshot.

    Errors:
      404 — no chat session found for this daily session belonging to user
    """
    from app.modules.learning_session.models import LearningSession

    session = (
        db.query(LearningSession)
        .filter(
            LearningSession.daily_session_id == daily_session_id,
            LearningSession.user_id == current_user.id,
        )
        .order_by(LearningSession.id.desc())
        .first()
    )
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="No chat session found for this daily session",
        )

    return LearningSessionSnapshotRead(
        session_id=session.session_id,
        daily_session_id=session.daily_session_id,
        topic=session.topic,
        skill_name=session.skill_name,
        task_type=session.task_type,
        phase=session.phase,
        messages=session.messages or [],
        pre_generated_tasks=session.pre_generated_tasks,
        user_submission=session.user_submission,
        evaluation=session.evaluation,
        feedback=session.feedback,
        task_queue=session.task_queue or [],
        created_at=session.created_at,
    )


@rest_router.get(
    "/sessions/{session_id}/scorecard",
    status_code=status.HTTP_200_OK,
)
async def get_scorecard_for_chat_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the V2 SessionScorecard for the DailySession backing this chat.

    The chat URL carries the LearningSession id, but the scorecard endpoint
    is keyed by the DailySession UUID. This bridges the two so the chat UI
    can render the day-level scorecard without leaking the V2 id.
    """
    from app.modules.learning_session.models import LearningSession
    from app.modules.sessions.models import DailySession
    from app.modules.sessions.routes import _make_session_service, _serialize_scorecard

    chat = (
        db.query(LearningSession)
        .filter(
            LearningSession.session_id == session_id,
            LearningSession.user_id == current_user.id,
        )
        .first()
    )
    if chat is None:
        raise HTTPException(status_code=404, detail="chat session not found")

    daily = db.get(DailySession, chat.daily_session_id)
    if daily is None:
        raise HTTPException(status_code=404, detail="daily session not found")

    service = _make_session_service(db)

    # Guard: only try to complete (or rebuild) when all attempts are evaluated
    # OR when the session is already COMPLETED (for stale-scorecard rebuild).
    # Avoids creating a partial scorecard for an in-progress session.
    from app.modules.sessions.models import AttemptStatus as _AttemptStatus
    from app.modules.sessions.models import SessionStatus as _SessionStatus
    from app.modules.sessions.repository import ActivityAttemptRepository as _AttRepo

    _all_evaluated = False
    if daily.status == _SessionStatus.COMPLETED:
        _all_evaluated = True
    else:
        _attempts = _AttRepo(db).list_for_session(daily.id)
        _all_evaluated = bool(_attempts) and all(
            a.status is _AttemptStatus.EVALUATED for a in _attempts
        )

    if _all_evaluated:
        try:
            # complete_session is now semi-idempotent: it detects when activity
            # scores have changed since the stored scorecard was built and
            # rebuilds the scorecard automatically.  This handles the common
            # case where the first attempt had a 0.0 speak score (e.g. transient
            # Azure API failure) and the learner re-ran the session to get a
            # real pronunciation score.
            await service.complete_session(
                session_id=daily.session_id,
                user_id=current_user.id,
            )
        except Exception:  # noqa: BLE001
            # Unexpected error — roll back so the DB session is clean for the
            # get_scorecard() query below (avoids PendingRollbackError).
            db.rollback()

    # Defense-in-depth: a scorecard only describes a COMPLETED day. If the day
    # is in-progress (e.g. an activity was reset/retried after completion, which
    # reopens it and drops the scorecard) there is nothing to return yet. The
    # orphan scorecard is already deleted on restart/reset, but guard here too.
    if daily.status != _SessionStatus.COMPLETED:
        raise HTTPException(
            status_code=404,
            detail="session has no scorecard yet",
        )

    scorecard = service.get_scorecard(
        session_id=daily.session_id,
        user_id=current_user.id,
    )
    if scorecard is None:
        raise HTTPException(
            status_code=404,
            detail="session has no scorecard yet",
        )
    result = _serialize_scorecard(daily.session_id, scorecard, db=db)
    # Hydrate the viewer's reaction on the Coach's Note so the chat UI can
    # show persisted 👍/👎 state on reload. COACH_NOTE reactions key on the
    # scorecard id (already set on `result.scorecard_id`).
    from typing import Literal, cast

    from app.modules.feedback.service import lookup_reaction
    from app.modules.sessions.models import FeedbackType

    if result.scorecard_id is not None:
        result.user_reaction = cast(
            "Literal['LIKE', 'DISLIKE'] | None",
            lookup_reaction(
                db,
                user_id=current_user.id,
                feedback_id=result.scorecard_id,
                feedback_type=FeedbackType.COACH_NOTE.value,
            ),
        )
    return result


# Coach's Note reactions now go through the unified POST /feedback/reaction
# endpoint (feedback_type=COACH_NOTE, feedback_id=scorecard.id); the legacy
# per-session rag-feedback/rating endpoints were removed in the reaction
# redesign. The viewer's reaction is hydrated onto the scorecard read above.


# --- WebSocket --------------------------------------------------------

ws_router = APIRouter()


def _resolve_user_from_token(token: str | None, db: Session) -> User | None:
    if not token:
        return None
    payload = decode_token(token)
    if payload is None:
        return None
    sub = payload.get("sub")
    if sub is None:
        return None
    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        return None
    return UserRepository(db).get_by_id(user_id)


async def _send(ws: WebSocket, msg: WSOutgoingMessage) -> None:
    await ws.send_text(msg.model_dump_json(exclude_none=True))


@ws_router.websocket("/ws/learning/{session_id}")
async def learning_session_ws(
    websocket: WebSocket,
    session_id: str,
    token: str | None = None,
    db: Session = Depends(get_db),
) -> None:
    user = _resolve_user_from_token(token, db)
    if user is None:
        await websocket.close(code=4401)
        return

    if not user.has_any_role({ROLE_LEARNER, ROLE_SUPER_ADMIN}):
        await websocket.close(code=4403)
        return

    if not check_ws_access(user, db):
        await websocket.close(code=WS_PAYMENT_REQUIRED)
        return

    service = LearningSessionService(db)

    session = service.session_repo.get_by_session_id(session_id)
    if session is None or session.user_id != user.id:
        await websocket.close(code=4404)
        return

    await websocket.accept()

    try:
        if not session.messages:
            async for msg in service.initial_messages_stream(session_id):
                await _send(websocket, msg)
        else:
            async for msg in service.resume_messages_stream(session_id):
                await _send(websocket, msg)

        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
                incoming = WSIncomingMessage.model_validate(payload)
            except (json.JSONDecodeError, ValidationError) as exc:
                await _send(
                    websocket,
                    WSOutgoingMessage(type="error", content=f"Bad message: {exc}"),
                )
                continue

            # Heartbeat: the client pings every ~25s to keep traffic flowing so
            # the ALB's 120s idle timeout never drops the socket. Reply with a
            # pong and skip the rate-limit guard + session pipeline entirely — a
            # ping is a keepalive, not a learner action, so it must not consume
            # the message-rate budget or touch session state.
            if incoming.type == "ping":
                await _send(websocket, WSOutgoingMessage(type="pong"))
                continue

            # Per-user message-rate guard: every accepted message can fan out
            # into LLM calls, so throttle at the submit boundary. The
            # connection stays open — the client already renders error frames.
            if settings.AI_RATE_LIMIT_ENABLED and not get_limiter().allow(
                f"ws:learning:{user.id}",
                limit=settings.WS_MESSAGE_RATE_PER_MINUTE,
                window_seconds=60,
            ):
                await _send(
                    websocket,
                    WSOutgoingMessage(type="error", content=RATE_LIMIT_MESSAGE),
                )
                continue

            try:
                stream = service.process_message_stream(session_id, incoming)
                async for msg in stream:
                    await _send(websocket, msg)
            except (ContractValidationError, TaskGenerationFailed) as exc:
                # Recoverable: the LLM/contract couldn't produce renderable task
                # content. Surface a friendly, tagged error so the client can offer
                # a retry (which forces a fresh generation, bypassing the cached
                # broken content) rather than wedging the session on a raw error.
                logger.warning(
                    "ws task generation failed session_id=%s: %s", session_id, exc
                )
                capture_to_sentry(exc)
                await _send(
                    websocket,
                    WSOutgoingMessage(
                        type="error",
                        code="task_generation_failed",
                        content=TASK_REGEN_FAILED_CHAT_DETAIL,
                    ),
                )
                continue
            except Exception as exc:  # pragma: no cover — unexpected
                logger.exception("ws process_message failed session_id=%s", session_id)
                capture_to_sentry(exc)
                await _send(
                    websocket,
                    WSOutgoingMessage(type="error", content=str(exc)),
                )
                continue

    except WebSocketDisconnect:
        return
