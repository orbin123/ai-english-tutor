"""Real-time A2Z audio streaming via Deepgram WebSocket.

Flow:
  Browser ──audio bytes──▶ this WS endpoint ──audio bytes──▶ Deepgram
  Browser ◀──word events── this WS endpoint ◀──transcripts── Deepgram

The handler:
  1. Authenticates the JWT passed as a ?token= query param.
  2. Loads the active round and its target letter.
  3. Opens a Deepgram streaming connection.
  4. Relays raw audio chunks (WebM/Opus from MediaRecorder) to Deepgram.
  5. On each final transcript, extracts valid words, accumulates them,
     persists to DB, and pushes an AudioChunkResponse JSON to the browser.
  6. Closes gracefully when the browser disconnects or the target is met.
"""

from __future__ import annotations

import asyncio
import json
import logging

import websockets
import websockets.exceptions
from fastapi import WebSocket, WebSocketDisconnect
from websockets import ClientConnection as DgConnection
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.ai_concurrency import ai_provider_slot
from app.core.ai_rate_limit import get_limiter
from app.core.config import settings
from app.core.security import decode_token
from app.core.sentry import capture_to_sentry
from app.modules.auth.models import ROLE_LEARNER, ROLE_SUPER_ADMIN
from app.modules.auth.repository import UserRepository
from app.modules.subscriptions.dependencies import (
    WS_PAYMENT_REQUIRED,
    check_ws_access,
)
from app.modules.challenges.a2z_game import evaluator
from app.modules.challenges.a2z_game.repository import A2ZRoundRepository
from app.modules.challenges.a2z_game.schemas import AudioChunkResponse

logger = logging.getLogger(__name__)

# Deepgram streaming endpoint with tuned parameters:
#   interim_results=true   → we receive rapid interim events + confirmed finals
#   endpointing=300        → declare utterance end after 300 ms of silence
#   punctuate=false        → no punctuation added (our evaluator doesn't need it)
_DG_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?model=nova-2"
    "&language=en"
    "&interim_results=true"
    "&endpointing=300"
    "&punctuate=false"
    "&smart_format=false"
)

# Extra seconds granted after the client stops sending audio for Deepgram to
# flush final transcripts for the tail (the lagged last words) before we tear
# the stream down. A backstop only — the normal drain completes in ~1-2s.
_DRAIN_MARGIN_SECONDS = 20


async def _send_error(
    websocket: WebSocket,
    *,
    code: str,
    message: str,
    close_code: int = 1000,
) -> None:
    """Send a structured error frame, then close the (already-accepted) socket.

    The browser handles ``{"type": "error", ...}`` text frames to show an
    explicit message instead of silently treating the close as a finished round.
    """
    try:
        await websocket.send_text(
            json.dumps({"type": "error", "code": code, "message": message})
        )
    except Exception:
        pass
    try:
        await websocket.close(code=close_code)
    except Exception:
        pass


def _resolve_user_id(token: str, db: Session) -> int | None:
    """Verify the JWT and return the user_id, or None if invalid."""
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None
    user = UserRepository(db).get_by_id(user_id)
    if user is None or not user.is_active:
        return None
    if not user.has_any_role({ROLE_LEARNER, ROLE_SUPER_ADMIN}):
        return None
    return user_id


async def stream_round(
    *,
    websocket: WebSocket,
    round_id: int,
    token: str,
    db: Session,
) -> None:
    """
    Main entry point: called from the WebSocket route.

    Authenticates, loads the round, proxies audio to Deepgram, and
    streams validated word events back to the browser.
    """
    # Accept the handshake first so the browser can read a structured error
    # frame for any failure below. Closing before accept() rejects the upgrade
    # with a bare 403 the client cannot interpret.
    await websocket.accept()

    user_id = _resolve_user_id(token, db)
    if user_id is None:
        await _send_error(
            websocket,
            code="unauthorized",
            message="Your session has expired. Please sign in again.",
            close_code=4001,
        )
        return

    user = UserRepository(db).get_by_id(user_id)
    if user is None or not check_ws_access(user, db):
        await _send_error(
            websocket,
            code="payment_required",
            message="Your trial has ended — upgrade to continue.",
            close_code=WS_PAYMENT_REQUIRED,
        )
        return

    if not settings.DEEPGRAM_API_KEY:
        await _send_error(
            websocket,
            code="streaming_not_configured",
            message="Real-time speech recognition is not configured on the server.",
            close_code=4000,
        )
        return

    attempt = A2ZRoundRepository(db).get_in_progress_for_user(
        round_id=round_id, user_id=user_id
    )
    if attempt is None:
        await _send_error(
            websocket,
            code="round_not_found",
            message="This round could not be found or has already ended. Start a new round.",
            close_code=4004,
        )
        return

    # Connection-level guard only: each accepted stream costs Deepgram money,
    # but audio frames inside an accepted stream are never throttled (that
    # would break real-time transcription mid-round).
    if settings.AI_RATE_LIMIT_ENABLED and not get_limiter().allow(
        f"ws:a2z:{user_id}",
        limit=settings.WS_A2Z_STREAMS_PER_MINUTE,
        window_seconds=60,
    ):
        await _send_error(
            websocket,
            code="rate_limited",
            message="Too many round attempts in a short time. Please wait a moment.",
            close_code=4029,
        )
        return

    task = attempt.task_payload or {}
    letter: str = task.get("letter", "")
    target_words: int = task.get("target_words", 10)
    round_time = min(
        int(task.get("round_time_seconds", 60) or 60),
        int(settings.MAX_AUDIO_DURATION_SECONDS),
    )
    accepted: set[str] = set((attempt.response_payload or {}).get("accepted_words", []))

    dg_headers = {"Authorization": f"Token {settings.DEEPGRAM_API_KEY}"}
    done = asyncio.Event()

    async def _push_words(new_words: list[str], raw_transcript: str) -> None:
        """Accumulate words in DB and send an event to the browser."""
        accepted.update(new_words)
        all_accepted = list(accepted)

        resp = attempt.response_payload or {}
        resp["accepted_words"] = all_accepted
        resp["running_transcript"] = (
            resp.get("running_transcript", "") + " " + raw_transcript
        ).strip()
        attempt.response_payload = resp
        flag_modified(attempt, "response_payload")
        # Commit so finish_round (a separate request session) can grade these
        # accumulated words. A flush alone would be rolled back at WS close.
        db.commit()

        event = AudioChunkResponse(
            new_words=new_words,
            accepted_words=all_accepted,
            valid_word_count=len(all_accepted),
            target_words=target_words,
            passed_so_far=len(all_accepted) >= target_words,
        )
        await websocket.send_text(event.model_dump_json())

    async def _forward_audio(dg_ws: DgConnection) -> None:
        """Browser → Deepgram: relay raw audio bytes until the client stops.

        Reads raw WS frames so we can tell audio (binary) apart from the
        ``{"type": "stop"}`` control frame the client sends when the round ends.
        On stop (or disconnect) we send Deepgram a ``CloseStream`` so it flushes
        the final transcripts for the tail — the lagged last words — and we do
        **not** set ``done``: the drain in ``_handle_transcripts`` must keep
        reading those flushed finals.
        """
        try:
            while not done.is_set():
                try:
                    message = await asyncio.wait_for(websocket.receive(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue

                if message.get("type") == "websocket.disconnect":
                    break

                data = message.get("bytes")
                if data is not None:
                    try:
                        await dg_ws.send(data)
                    except websockets.exceptions.ConnectionClosed:
                        break
                    continue

                text = message.get("text")
                if text:
                    try:
                        ctrl = json.loads(text)
                    except json.JSONDecodeError:
                        continue
                    if ctrl.get("type") == "stop":
                        break
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            logger.debug("a2z _forward_audio exit: %s", exc)
        finally:
            # No more audio: ask Deepgram to finalize the buffered tail before it
            # closes. Do NOT set `done` here — the transcript drain must continue.
            try:
                await dg_ws.send(json.dumps({"type": "CloseStream"}))
            except Exception:
                pass

    async def _handle_transcripts(dg_ws: DgConnection) -> None:
        """Deepgram → filter → browser: emit newly accepted words.

        Runs until Deepgram closes the connection. After the client stops,
        Deepgram flushes the buffered tail as final transcripts (triggered by
        the ``CloseStream`` sent in ``_forward_audio``) and only then closes — so
        by the time this loop ends, every spoken word has been graded and
        committed. We then send a single ``final`` frame so the browser knows the
        authoritative word list is persisted and it can safely score the round.
        """
        try:
            async for raw_msg in dg_ws:
                if isinstance(raw_msg, bytes):
                    continue
                try:
                    evt = json.loads(raw_msg)
                except json.JSONDecodeError:
                    continue

                # Only process confirmed final results (not interim guesses)
                if not evt.get("is_final", False) or evt.get("type") != "Results":
                    continue

                transcript = (
                    evt.get("channel", {})
                    .get("alternatives", [{}])[0]
                    .get("transcript", "")
                ).strip()

                if not transcript:
                    continue

                chunk_valid = evaluator.extract_valid_words(transcript, letter)
                new_words = [w for w in chunk_valid if w not in accepted]
                if new_words:
                    await _push_words(new_words, transcript)

                if len(accepted) >= target_words:
                    done.set()
                    break

        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as exc:
            logger.debug("a2z _handle_transcripts exit: %s", exc)
        finally:
            done.set()
            # The drained word list is committed — tell the browser it's safe to
            # finish and grade. Distinct `type` so the client routes it to its
            # finalize path instead of treating it as a live word update.
            all_accepted = list(accepted)
            try:
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "final",
                            "accepted_words": all_accepted,
                            "valid_word_count": len(all_accepted),
                            "target_words": target_words,
                            "passed_so_far": len(all_accepted) >= target_words,
                        }
                    )
                )
            except Exception:
                pass

    # Overall ceiling: the active round plus a margin for Deepgram to flush the
    # tail after the client stops. A backstop against a zombie upstream only —
    # the normal drain finishes within ~1-2s once CloseStream is sent.
    stream_deadline = round_time + _DRAIN_MARGIN_SECONDS

    try:
        async with ai_provider_slot():
            async with websockets.connect(
                _DG_URL, additional_headers=dg_headers
            ) as dg_ws:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(
                            _forward_audio(dg_ws),
                            _handle_transcripts(dg_ws),
                        ),
                        timeout=stream_deadline,
                    )
                except asyncio.TimeoutError:
                    logger.warning("a2z stream drain timeout round=%d", round_id)
                    done.set()
    except Exception as exc:
        logger.exception("a2z stream error round=%d: %s", round_id, exc)
        capture_to_sentry(exc)
        await _send_error(
            websocket,
            code="upstream_failed",
            message="Speech service is unavailable right now. Please try again.",
            close_code=1011,
        )
        return

    try:
        await websocket.close()
    except Exception:
        pass
