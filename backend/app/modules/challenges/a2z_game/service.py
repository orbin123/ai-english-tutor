"""Business logic for the A2Z Challenge game.

Orchestrates progress tracking, round lifecycle (spin/pick → record → finish),
audio chunk ingestion with live STT, and game restart.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.ai.storage import get_default_blob_storage
from app.ai.storage.interface import IBlobStorage
from app.ai.stt import TranscriptionResult, get_default_stt_service
from app.core.audio_uploads import enforce_audio_duration
from app.modules.challenges.a2z_game import evaluator
from app.modules.challenges.a2z_game.constants import (
    A2Z_LETTERS,
    A2Z_SLUG,
    MAX_LEVEL,
    TOTAL_LETTERS,
)
from app.modules.challenges.a2z_game.repository import (
    A2ZProgressRepository,
    A2ZRoundRepository,
)
from app.modules.challenges.a2z_game.schemas import (
    A2ZLevelRead,
    A2ZProgressRead,
    AudioChunkResponse,
    FinishRoundResponse,
    StartRoundResponse,
)
from app.modules.challenges.models import ChallengeAttemptStatus
from app.modules.challenges.repository import (
    ChallengeAttemptRepository,
    ChallengeRepository,
)


# ── Exceptions ───────────────────────────────────────────────────────


class A2ZChallengeNotFound(Exception):
    """The A2Z challenge catalog entry is missing (seed not run)."""


class A2ZGameCompleted(Exception):
    """The game is already fully completed."""


class A2ZLetterNotAvailable(Exception):
    """The requested letter is not in the open set."""


class A2ZRoundNotFound(Exception):
    """No round with this ID for this user."""


class A2ZRoundNotInProgress(Exception):
    """The round is not in 'in_progress' state."""


class A2ZRestartNotAllowed(Exception):
    """Restart is only allowed after full completion."""


# ── Service ──────────────────────────────────────────────────────────


class A2ZService:
    """Stateless service — instantiate per-request with a DB session."""

    def __init__(
        self,
        db: Session,
        *,
        stt_service: object | None = None,
        blob_storage: IBlobStorage | None = None,
    ) -> None:
        self.db = db
        self._challenge_repo = ChallengeRepository(db)
        self._attempt_repo = ChallengeAttemptRepository(db)
        self._progress_repo = A2ZProgressRepository(db)
        self._round_repo = A2ZRoundRepository(db)
        self._stt = stt_service
        self._blob = blob_storage

    # -- Lazy DI defaults -------------------------------------------------

    @property
    def stt(self):
        if self._stt is None:
            self._stt = get_default_stt_service()
        return self._stt

    @property
    def blob(self) -> IBlobStorage:
        if self._blob is None:
            self._blob = get_default_blob_storage()
        return self._blob

    # -- Helpers -----------------------------------------------------------

    def _load_challenge(self):
        """Load the A2Z challenge catalog entry or raise."""
        challenge = self._challenge_repo.get_active_by_slug(A2Z_SLUG)
        if challenge is None:
            raise A2ZChallengeNotFound(
                f"Challenge '{A2Z_SLUG}' not found. Run the seed script."
            )
        return challenge

    @staticmethod
    def _resolve_current_level_number(cleared_by_level: dict) -> int:
        """First level where cleared < TOTAL_LETTERS, else MAX_LEVEL."""
        for lvl_num in range(1, MAX_LEVEL + 1):
            cleared = cleared_by_level.get(str(lvl_num), [])
            if len(cleared) < TOTAL_LETTERS:
                return lvl_num
        return MAX_LEVEL

    @staticmethod
    def _open_letters(cleared_by_level: dict, level_number: int) -> list[str]:
        """Letters not yet cleared on *level_number*."""
        cleared = set(cleared_by_level.get(str(level_number), []))
        return [ltr for ltr in A2Z_LETTERS if ltr not in cleared]

    def _build_progress_dto(self, challenge, progress) -> A2ZProgressRead:
        """Assemble the progress response DTO."""
        cleared = progress.cleared_letters or {"1": [], "2": [], "3": []}
        current_level = self._resolve_current_level_number(cleared)
        open_ltrs = self._open_letters(cleared, current_level)
        game_completed = progress.game_completed_at is not None

        levels = []
        for lvl in challenge.levels:
            cfg = lvl.config or {}
            levels.append(
                A2ZLevelRead(
                    level_number=lvl.level_number,
                    name=lvl.name,
                    target_words=cfg.get("target_words", lvl.time_limit_seconds),
                    round_time_seconds=cfg.get(
                        "round_time_seconds", lvl.time_limit_seconds
                    ),
                )
            )

        return A2ZProgressRead(
            challenge_slug=A2Z_SLUG,
            letters=A2Z_LETTERS,
            levels=levels,
            current_level_number=current_level,
            cleared_by_level=cleared,
            open_letters=open_ltrs,
            game_completed=game_completed,
            can_restart=game_completed,
        )

    # -- Public API --------------------------------------------------------

    def get_progress(self, user_id: int) -> A2ZProgressRead:
        """Return everything the home screen needs."""
        challenge = self._load_challenge()
        progress = self._progress_repo.get_or_create(
            user_id=user_id, challenge_id=challenge.id
        )
        return self._build_progress_dto(challenge, progress)

    def start_round(
        self,
        user_id: int,
        mode: str,
        letter: str | None = None,
    ) -> StartRoundResponse:
        """Start a new round: spin for a random open letter or pick one."""
        challenge = self._load_challenge()
        progress = self._progress_repo.get_or_create(
            user_id=user_id, challenge_id=challenge.id
        )
        cleared = progress.cleared_letters or {"1": [], "2": [], "3": []}
        current_level = self._resolve_current_level_number(cleared)
        open_ltrs = self._open_letters(cleared, current_level)

        # Check if game is already complete
        if progress.game_completed_at is not None:
            raise A2ZGameCompleted(
                "Game is already completed. Use restart to play again."
            )

        if not open_ltrs:
            # All letters cleared on current level — shouldn't happen because
            # level advance is handled in finish_round. Safety net:
            raise A2ZGameCompleted("All letters cleared. Advance or restart.")

        # Resolve the letter
        if mode == "spin":
            chosen_letter = random.choice(open_ltrs)
        else:  # pick
            if letter is None:
                raise A2ZLetterNotAvailable("Letter is required for pick mode.")
            chosen_letter = letter.upper()
            if chosen_letter not in open_ltrs:
                raise A2ZLetterNotAvailable(
                    f"Letter '{chosen_letter}' is not available. "
                    f"It may already be cleared or is excluded."
                )

        # Find the level row
        level_row = None
        for lvl in challenge.levels:
            if lvl.level_number == current_level:
                level_row = lvl
                break
        if level_row is None:
            raise A2ZChallengeNotFound(f"Level {current_level} not found in catalog.")

        cfg = level_row.config or {}
        target_words = cfg.get("target_words", 10)
        round_time = cfg.get("round_time_seconds", level_row.time_limit_seconds)

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=round_time)

        task_payload = {
            "game": "a2z",
            "letter": chosen_letter,
            "target_words": target_words,
            "round_time_seconds": round_time,
            "level_number": current_level,
        }

        attempt = self._attempt_repo.create(
            user_id=user_id,
            level_id=level_row.id,
            started_at=now,
            expires_at=expires_at,
            task_payload=task_payload,
        )
        # Commit so the round persists: the WS stream and finish_round run in
        # separate request sessions and must be able to load this attempt.
        self.db.commit()

        return StartRoundResponse(
            round_id=attempt.id,
            letter=chosen_letter,
            target_words=target_words,
            round_time_seconds=round_time,
            expires_at=expires_at,
            level_number=current_level,
        )

    async def ingest_audio_chunk(
        self,
        user_id: int,
        round_id: int,
        audio_bytes: bytes,
        chunk_index: int,
        content_type: str | None = None,
    ) -> AudioChunkResponse:
        """Store an audio chunk, transcribe it, and return newly found words."""
        attempt = self._round_repo.get_in_progress_for_user(
            round_id=round_id, user_id=user_id
        )
        if attempt is None:
            # Check if it exists at all
            exists = self._round_repo.get_for_user(round_id=round_id, user_id=user_id)
            if exists is None:
                raise A2ZRoundNotFound(f"Round {round_id} not found.")
            raise A2ZRoundNotInProgress(f"Round {round_id} is not in progress.")

        task = attempt.task_payload or {}
        if task.get("game") != "a2z":
            raise A2ZRoundNotFound(f"Round {round_id} is not an A2Z round.")

        letter = task["letter"]
        target_words = task.get("target_words", 10)

        # Store audio chunk in blob storage
        ext = "webm"
        if content_type and "wav" in content_type:
            ext = "wav"
        elif content_type and "ogg" in content_type:
            ext = "ogg"
        elif content_type and "mp4" in content_type:
            ext = "mp4"

        chunk_key = f"a2z/{user_id}/{round_id}/chunk_{chunk_index}.{ext}"
        await self.blob.put(
            key=chunk_key,
            data=audio_bytes,
            content_type=content_type or "audio/webm",
        )

        # Transcribe the chunk
        filename = f"chunk_{chunk_index}.{ext}"
        result: TranscriptionResult = await self.stt.transcribe(
            audio_bytes=audio_bytes,
            filename=filename,
            language="en",
            with_timestamps=False,
        )
        enforce_audio_duration(result.get("duration_seconds"))
        chunk_text = result.get("text", "").strip()

        # Store the latest full transcript for reference
        response = attempt.response_payload or {}
        response["running_transcript"] = chunk_text

        # Extract valid words from the latest transcript
        chunk_valid = evaluator.extract_valid_words(chunk_text, letter)

        # Union with all previously accepted words so words never vanish
        # (Whisper is probabilistic — later chunks may not re-mention earlier words)
        prev_accepted = set(response.get("accepted_words", []))
        combined = list(prev_accepted | set(chunk_valid))

        # Determine new words (not yet seen before this chunk)
        new_words = [w for w in combined if w not in prev_accepted]

        # Update accepted words (monotonically growing)
        all_valid = combined
        response["accepted_words"] = all_valid
        attempt.response_payload = response

        # Flag the column as modified for SQLAlchemy JSON mutation tracking
        from sqlalchemy.orm.attributes import flag_modified

        flag_modified(attempt, "response_payload")
        self.db.commit()

        return AudioChunkResponse(
            new_words=new_words,
            accepted_words=all_valid,
            valid_word_count=len(all_valid),
            target_words=target_words,
            passed_so_far=len(all_valid) >= target_words,
        )

    def finish_round(self, user_id: int, round_id: int) -> FinishRoundResponse:
        """Finalize a round: grade the transcript and update progress."""
        attempt = self._round_repo.get_for_user(round_id=round_id, user_id=user_id)
        if attempt is None:
            raise A2ZRoundNotFound(f"Round {round_id} not found.")
        if attempt.status != ChallengeAttemptStatus.IN_PROGRESS:
            raise A2ZRoundNotInProgress(f"Round {round_id} is not in progress.")

        task = attempt.task_payload or {}
        if task.get("game") != "a2z":
            raise A2ZRoundNotFound(f"Round {round_id} is not an A2Z round.")

        letter = task["letter"]
        target_words = task.get("target_words", 10)
        level_number = task.get("level_number", 1)

        # Use the union-accumulated accepted_words as the authoritative word list.
        # Re-grading from running_transcript alone would lose words that Whisper
        # correctly identified in earlier chunks but missed in the final chunk.
        response = attempt.response_payload or {}
        accumulated_words = response.get("accepted_words", [])

        # Fall back to grading the transcript if no chunks were processed
        if not accumulated_words:
            transcript = response.get("running_transcript", "")
            accumulated_words = evaluator.extract_valid_words(transcript, letter)

        passed = len(accumulated_words) >= target_words
        report = {
            "valid_words": accumulated_words,
            "valid_word_count": len(accumulated_words),
            "target_words": target_words,
            "passed": passed,
        }

        # Update attempt
        now = datetime.now(timezone.utc)
        attempt.status = ChallengeAttemptStatus.COMPLETED
        attempt.completed_at = now
        attempt.passed = passed
        attempt.evaluation_report = report
        attempt.overall_score = float(report["valid_word_count"])

        # Ensure response_payload has final accepted words
        response["accepted_words"] = report["valid_words"]
        attempt.response_payload = response

        from sqlalchemy.orm.attributes import flag_modified

        flag_modified(attempt, "response_payload")
        flag_modified(attempt, "evaluation_report")

        # Update progress if passed
        challenge = self._load_challenge()
        progress = self._progress_repo.get_or_create(
            user_id=user_id, challenge_id=challenge.id
        )
        cleared = progress.cleared_letters or {"1": [], "2": [], "3": []}
        level_key = str(level_number)

        level_cleared = False
        game_completed = False

        if passed:
            if level_key not in cleared:
                cleared[level_key] = []
            if letter not in cleared[level_key]:
                cleared[level_key].append(letter)

            progress.cleared_letters = cleared
            flag_modified(progress, "cleared_letters")

            # Check if this level is now fully cleared
            if len(cleared[level_key]) >= TOTAL_LETTERS:
                level_cleared = True
                # Check if game is complete (all levels cleared)
                if level_number >= MAX_LEVEL:
                    game_completed = True
                    progress.game_completed_at = now

        self._progress_repo.save(progress)
        self.db.commit()

        # Build progress DTO
        progress_dto = self._build_progress_dto(challenge, progress)

        return FinishRoundResponse(
            passed=passed,
            letter=letter,
            valid_words=report["valid_words"],
            valid_word_count=report["valid_word_count"],
            target_words=target_words,
            level_number=level_number,
            level_cleared=level_cleared,
            game_completed=game_completed,
            progress=progress_dto,
        )

    def restart_game(self, user_id: int) -> A2ZProgressRead:
        """Reset all progress. Only allowed after full completion."""
        challenge = self._load_challenge()
        progress = self._progress_repo.get_or_create(
            user_id=user_id, challenge_id=challenge.id
        )

        if progress.game_completed_at is None:
            raise A2ZRestartNotAllowed(
                "Restart is only allowed after completing all levels."
            )

        now = datetime.now(timezone.utc)
        progress.cleared_letters = {"1": [], "2": [], "3": []}
        progress.game_completed_at = None
        progress.last_restarted_at = now

        from sqlalchemy.orm.attributes import flag_modified

        flag_modified(progress, "cleared_letters")
        self._progress_repo.save(progress)
        self.db.commit()

        return self._build_progress_dto(challenge, progress)
