"""Business logic for chat-driven learning sessions.

LearningSession is the **conversation envelope** layered on top of the
V2 `DailySession`. The V2 row owns the task content, the evaluation, the
feedback rows, the scorecard, and the scoring writeback. This service
owns the conversation (messages, phase, teacher persona, streaming).

The flow:

  1. ``create_session`` — find/create the V2 DailySession for today via
     UserCoursePreference (or accept an explicit `daily_session_id`),
     run the PlannerAgent against the V2 curriculum row to build a
     teacher persona, persist a LearningSession row, return the
     session_id the frontend opens a WebSocket against.

  2. ``process_message_stream`` — the WebSocket message handler. Routes
     by `phase` + incoming message type, calls the V2 SessionService for
     evaluation/feedback/completion, formats results as chat messages.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any, cast

import structlog
from sqlalchemy.orm import Session

from app.ai.agents.planner import PlannerAgent
from app.ai.agents.relevance_classifier import classify_reply_relevance
from app.ai.agents.teacher import stream_teaching_turn
from app.ai.llm.eval_context import reset_eval_context, set_eval_context
from app.core.config import settings
from app.core.sentry import capture_to_sentry
from app.modules.curriculum.file_source import (
    SCRIPTED_PLAN_KEY,
    build_teacher_instructions as file_build_teacher_instructions,
    get_day_by_id as file_get_day_by_id,
    resolve_archetypes as file_resolve_archetypes,
    split_scripted_plan,
)
from app.ai.graphs.nodes import (
    stream_answer_question,
    task_delivery_node,
)
from app.ai.graphs.state import LearningSessionState, PhaseType
from app.modules.auth.models import User
from app.modules.auth.repository import UserProfileRepository
from app.modules.curriculum.adapters import v2_course_topic
from app.modules.curriculum.repository import (
    CurriculumDayRepository,
    TaskArchetypeRepository,
)
from app.modules.learning_session.models import LearningSession
from app.modules.learning_session.orchestrator import (
    SessionEventOrchestrator,
    activity_contract_from_content,
    runtime_blueprint_from_attempts,
    runtime_blueprint_from_session,
)
from app.modules.learning_session.repository import LearningSessionRepository
from app.modules.learning_session.schemas import (
    StartSessionResponse,
    WSIncomingMessage,
    WSOutgoingMessage,
)
from app.modules.preferences.service import PreferenceService
from app.modules.sessions.exceptions import (
    AttemptAlreadySubmitted,
    AttemptNotFound,
    DayNotFound,
    SessionAbandoned,
    SessionAlreadyCompleted,
    SessionAlreadyOpen,
    SessionNotFound,
)
from app.modules.sessions.models import (
    ActivityAttempt,
    AttemptStatus,
    DailySession,
    SessionScorecard,
    SessionStatus,
)
from app.modules.sessions.repository import (
    ActivityAttemptRepository,
    DailySessionRepository,
    ScorecardRepository,
)
from app.modules.sessions.contracts import (
    ContractValidationError,
    TeacherAgentInput,
    build_agent_input,
    contract_widgets,
    project_evaluation,
    project_feedback,
    project_task_payload,
)
from app.modules.sessions.evaluator import EvaluationResult
from app.modules.sessions.feedback_generator import FeedbackResult, MistakeOut
from app.modules.sessions.service import (
    EvaluationPhase,
    FeedbackPhase,
    SessionService,
    generate_mentor_note_async,
)
from app.modules.sessions.widget_mapping import normalize_widget_key
from app.modules.skills.repository import SkillRepository
from app.scoring import CourseLength, get_archetype

log = structlog.get_logger(__name__)

# Same-process fast path against concurrent complete_session calls (e.g. WS
# submit + resume) so one worker doesn't redundantly re-run completion work.
# This is per-process and NOT the correctness boundary across workers — the
# unique constraint on session_scorecards.session_id is the source of truth
# (SessionService.complete_session catches the IntegrityError). See audit B4.
_completing_daily_uuids: set[str] = set()

# Strong refs to in-flight Coach's Note workers so a timed-out (shielded) task
# is not garbage-collected before it finishes persisting the note.
_pending_note_tasks: set[asyncio.Task[str | None]] = set()

# evaluator_notes substrings that mark an infra/structural fallback rather than a
# genuine low score. The pass-mark gate is bypassed for these so a transient
# failure (LLM/STT/Azure down, malformed/empty payload) never traps the learner
# in an unwinnable retry loop. A real low score (incl. "No response submitted")
# is NOT in this list and so is gated normally.
_GATE_BYPASS_MARKERS: tuple[str, ...] = (
    "unavailable",
    "malformed",
    "no mcq items",
    "no blanks",
    "neutral fallback",
)


def _is_gate_bypass(evaluator_notes: str | None) -> bool:
    """True when evaluator_notes signal an error/structural fallback score."""
    if not evaluator_notes:
        return False
    notes = evaluator_notes.lower()
    return any(marker in notes for marker in _GATE_BYPASS_MARKERS)


# Friendly labels for the four core activities, used in the compact
# completed-activity summary rows the chat UI renders on resume.
_CORE_ACTIVITY_LABELS = {
    "read": "Reading",
    "write": "Writing",
    "listen": "Listening",
    "speak": "Speaking",
}

# Single farewell shown when the learner finishes all daily activities.
_DAILY_COMPLETE_MESSAGE = (
    "Today's activities are complete. Go back to the dashboard "
    "to review the day and advance when you're ready."
)

# Shown when the learner leaves while an activity is still below the pass-mark
# threshold — the day stays open so they can come back and retry it.
_DAILY_GATE_INCOMPLETE_MESSAGE = (
    "No problem — this day is still open. Come back any time to retry the "
    "activity and pass it when you're ready."
)

# Short chat hand-off streamed after a graded activity, carrying the
# "Next activity" / "Go to dashboard" buttons. The detailed feedback already
# lives in the feedback card above it, so this MUST only acknowledge completion
# and point at the buttons — never restate the feedback summary or next tip, or
# the same text shows up twice on screen.
_ACTIVITY_COMPLETE_MESSAGE = (
    "Activity complete — your feedback is in the card above. Choose "
    '"Next activity" to keep going, or "Go to dashboard" to take a break.'
)

# follow_up_action the chat sends when the learner taps the retry icon on a
# failed-task-generation error bubble. Routed in `_stream_followup_response` to a
# forced fresh generation (bypasses the broken cached task_content).
REGENERATE_TASK_ACTION = "Regenerate task"


def _validate_teacher_input(**fields) -> None:
    """Guard the teacher-agent boundary. Raises under ``strict_contracts``;
    otherwise logs and proceeds. Validation is for its side effect."""
    if (
        build_agent_input(TeacherAgentInput, strict=settings.strict_contracts, **fields)
        is None
    ):
        log.warning(
            "teacher_input_validation_failed",
            note="proceeding on legacy path",
        )


_READY_RESPONSE_PHRASES = (
    "ready",
    "yes",
    "yeah",
    "yep",
    "sure",
    "ok",
    "okay",
    "let's go",
    "lets go",
    "i'm ready",
    "im ready",
    "go ahead",
    "begin",
    "start",
)

_READY_RESPONSE_PATTERNS = tuple(
    re.compile(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])")
    for phrase in _READY_RESPONSE_PHRASES
)

# Short canonical affirmatives used for typo-tolerant matching. A user reply
# of a single short token (≤6 chars, letters only) is treated as a "ready"
# response when its edit distance to one of these words is ≤ 1, so common
# typos like "yys", "yse", "okk", "redy" still progress the session.
_SHORT_AFFIRMATIVES = (
    "yes",
    "yeah",
    "yep",
    "ok",
    "okay",
    "sure",
    "ready",
)


def _edit_distance_le_1(a: str, b: str) -> bool:
    """Return True if `a` and `b` differ by at most one typo.

    Counts single substitution, single insertion/deletion, or one adjacent
    transposition (Damerau-Levenshtein distance ≤ 1). Used only for very
    short strings so we avoid the full DP table.
    """
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        diffs = [(x, y) for x, y in zip(a, b) if x != y]
        if len(diffs) == 1:
            return True
        if len(diffs) == 2:
            # Allow a single adjacent transposition (e.g. "yes" vs "yse").
            (x1, y1), (x2, y2) = diffs
            i1 = next(i for i, (x, y) in enumerate(zip(a, b)) if x != y)
            i2 = next(i for i in range(i1 + 1, la) if a[i] != b[i])
            if i2 == i1 + 1 and x1 == y2 and x2 == y1:
                return True
        return False
    short, long = (a, b) if la < lb else (b, a)
    i = j = 0
    edited = False
    while i < len(short) and j < len(long):
        if short[i] == long[j]:
            i += 1
            j += 1
            continue
        if edited:
            return False
        edited = True
        j += 1
    return True


def _is_typo_of_short_affirmative(token: str) -> bool:
    """True if `token` is within edit distance 1 of a short affirmative."""
    if not token or len(token) > 6 or not token.isalpha():
        return False
    return any(_edit_distance_le_1(token, word) for word in _SHORT_AFFIRMATIVES)


_NON_UNDERSTANDING_PHRASES = (
    "i don't understand",
    "i dont understand",
    "i do not understand",
    "i didn't understand",
    "i didnt understand",
    "i did not understand",
    "don't understand",
    "dont understand",
    "do not understand",
    "didn't understand",
    "didnt understand",
    "did not understand",
    "not understand",
    "not clear",
    "unclear",
    "confused",
    "i don't get",
    "i dont get",
    "i didn't get",
    "i didnt get",
    "not ready",
    "not yet",
    "wait",
    "explain again",
)

_NON_UNDERSTANDING_PATTERNS = tuple(
    re.compile(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])")
    for phrase in _NON_UNDERSTANDING_PHRASES
)

_READINESS_PROMPT_PATTERNS = (
    re.compile(
        r"\b(do you|does this|is this|that|it)\s+(feel\s+)?(clear|make sense)\b"
    ),
    re.compile(r"\b(are you|do you feel|feel)\s+ready\b"),
    re.compile(r"\bready\s+(for|to)\s+(practice|try|start|begin)\b"),
    re.compile(r"\bready to try the practice task\b"),
    re.compile(r"\bif\s+(that|this|it)\s+feels\s+clear\b"),
    re.compile(r"\bif\s+you\s+(feel\s+)?(ready|clear)\b"),
    re.compile(r"\bsay\s+['\"]?(ready|yes|okay|ok)['\"]?\b"),
    # Soft-transition phrasings the teacher LLM tends to use after a typo
    # recovery or affirmative reply — all anchored on the literal substring
    # `practice (task|exercise|activity)` to keep false positives low.
    re.compile(
        r"\b(let'?s|let us)\s+"
        r"(get\s+started|start|begin|move|jump|kick\s+off)\s+"
        r"(with\s+)?(the\s+)?practice\s+(task|exercise|activity)\b"
    ),
    re.compile(
        r"\b(let'?s|let us)\s+(get\s+started|start|begin)\s+"
        r"with\s+(the\s+)?practice\b"
    ),
    re.compile(
        r"\b(time|ready)\s+(to|for)\s+(the\s+)?practice\s+(task|exercise|activity)\b"
    ),
    re.compile(r"\bmove(\s+on)?\s+to\s+(the\s+)?practice\s+(task|exercise|activity)\b"),
    re.compile(r"\bbegin\s+the\s+practice\s+(task|exercise|activity)\b"),
)

# First-chunk budget for a streamed tutor turn. The teacher buffers the WHOLE
# LLM response (and may make one validation-retry call) before yielding its
# single chunk, so this must cover a full generate (+ retry), not just first
# token. The old 8s assumed gpt-4o-mini's ~1-2s first token; it was too tight
# and a slow turn silently fell back to the canned "Say 'ready'…" message. 30s
# is defense-in-depth on top of routing the teacher to the fast gpt-4.1-mini.
_TEACHING_STREAM_FIRST_CHUNK_TIMEOUT_S = 30.0
_TEACHING_STREAM_CHUNK_TIMEOUT_S = 20.0
_FOLLOWUP_STREAM_FIRST_CHUNK_TIMEOUT_S = 30.0
_FOLLOWUP_STREAM_CHUNK_TIMEOUT_S = 20.0


def _deterministic_scorecard_counts(
    _archetype_id: str,
    evaluator_notes: str | None,
) -> tuple[int | None, int | None]:
    """Extract correct/total counts from deterministic evaluator notes."""
    notes = evaluator_notes or ""
    match = re.search(r"(\d+)/(\d+) correct", notes)
    if match:
        return int(match.group(1)), int(match.group(2))
    try:
        parsed = json.loads(notes)
    except (json.JSONDecodeError, TypeError):
        return None, None
    if not isinstance(parsed, dict):
        return None, None
    correct = parsed.get("correct_count")
    total = parsed.get("total_blanks") or parsed.get("total")
    if correct is None or total is None:
        return None, None
    return int(correct), int(total)


class LearningSessionTaskUnavailable(Exception):
    """Raised when a chat session cannot be opened against the V2 daily session."""


_DAY_ID_RE = re.compile(r"^day_(?:24|48)_(\d{2})_(\d{2})$")


def _parse_day_id(day_id: str) -> tuple[int, int]:
    """Parse `day_24_WW_DD` (or `day_48_WW_DD`) into `(week_number, day_number)`.

    `day_number` is 1-based (matches the format `file_source` writes).
    Callers convert to 0-based `day_index` by subtracting 1.
    """
    match = _DAY_ID_RE.match(day_id or "")
    if not match:
        raise ValueError(f"unrecognised day_id format: {day_id!r}")
    return int(match.group(1)), int(match.group(2))


def _last_tutor_message(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") in ("ai", "assistant"):
            return str(message.get("content") or "").strip()
    return ""


def _tutor_asked_readiness(text: str) -> bool:
    cleaned = (text or "").strip().lower()
    if not cleaned:
        return False
    return any(pattern.search(cleaned) for pattern in _READINESS_PROMPT_PATTERNS)


def _looks_like_ready_response(text: str) -> bool:
    cleaned = (text or "").strip().lower()
    if not cleaned:
        return False
    if cleaned in _READY_RESPONSE_PHRASES:
        return True
    if any(pattern.search(cleaned) for pattern in _READY_RESPONSE_PATTERNS):
        return True
    # Typo tolerance: only when the whole reply is a single short token
    # (after stripping punctuation/whitespace). Prevents false positives
    # inside longer sentences.
    tokens = re.findall(r"[a-z]+", cleaned)
    if len(tokens) == 1 and _is_typo_of_short_affirmative(tokens[0]):
        return True
    return False


def _looks_like_strict_affirmative(text: str) -> bool:
    """Affirmative match WITHOUT typo fuzzing.

    Used for the affirmative-non-answer gate during teaching, where a genuine
    short content answer ("on", "in", "at") must NOT be mistaken for a bare
    "ok"/"yes": "on" is edit-distance 1 from "ok", so the typo-tolerant
    `_looks_like_ready_response` flags it. Typo tolerance stays reserved for the
    readiness gate, which only fires after the tutor asked a readiness question.
    """
    cleaned = (text or "").strip().lower()
    if not cleaned:
        return False
    if cleaned in _READY_RESPONSE_PHRASES:
        return True
    return any(pattern.search(cleaned) for pattern in _READY_RESPONSE_PATTERNS)


def _looks_like_ready_for_practice(
    text: str,
    *,
    previous_tutor_message: str = "",
) -> bool:
    cleaned = (text or "").strip().lower()
    if not cleaned:
        return False
    if any(pattern.search(cleaned) for pattern in _NON_UNDERSTANDING_PATTERNS):
        return False
    return _tutor_asked_readiness(
        previous_tutor_message
    ) and _looks_like_ready_response(cleaned)


def _looks_like_understanding(
    text: str,
    *,
    previous_tutor_message: str = "",
) -> bool:
    """Backward-compatible name for the practice readiness gate."""
    return _looks_like_ready_for_practice(
        text,
        previous_tutor_message=previous_tutor_message,
    )


_PRACTICE_TASK_MENTION_RE = re.compile(
    r"\bpractice\s+(task|exercise|activity)\b",
    re.IGNORECASE,
)

# Default ceiling used when no authored scripted plan is available.
_DEFAULT_TEACHING_TURN_CEILING = 4


def _count_teacher_chat_turns(messages: list[dict]) -> int:
    """Count teacher chat turns (role ai/assistant, type chat or unset)."""
    count = 0
    for message in messages:
        if message.get("role") not in ("ai", "assistant"):
            continue
        msg_type = str(message.get("type") or "chat")
        if msg_type != "chat":
            continue
        count += 1
    return count


def _any_tutor_mentioned_practice_task(messages: list[dict]) -> bool:
    for message in messages:
        if message.get("role") not in ("ai", "assistant"):
            continue
        content = str(message.get("content") or "")
        if _PRACTICE_TASK_MENTION_RE.search(content):
            return True
    return False


def _is_short_affirmative_or_short_reply(text: str) -> bool:
    """True when `text` is a plausible affirmative reply, not a question/negation.

    Used by the escape-valve to require the learner reply at least looks
    like a "yes/ok/sure/sounds good" and is not, e.g., a long question.
    """
    cleaned = (text or "").strip().lower()
    if not cleaned:
        return False
    if any(pattern.search(cleaned) for pattern in _NON_UNDERSTANDING_PATTERNS):
        return False
    if _looks_like_ready_response(cleaned):
        return True
    # Allow other short, non-negative replies (≤ 3 word tokens) to pass —
    # the strict word lists miss things like "sounds good", "got it".
    word_count = len(re.findall(r"[a-z]+", cleaned))
    if word_count == 0 or word_count > 3:
        return False
    soft_positive = (
        "got it",
        "sounds good",
        "alright",
        "all right",
        "lets do it",
        "let's do it",
        "lets do this",
        "let's do this",
        "i got it",
        "understood",
        "cool",
    )
    return any(phrase in cleaned for phrase in soft_positive)


def _scripted_plan_length(state: LearningSessionState) -> int:
    """Return the length of the authored scripted plan, or 0 if absent."""
    daily_plan = state.get("daily_plan") or {}
    instructions = daily_plan.get("teacher_instructions") if daily_plan else None
    if not isinstance(instructions, dict):
        return 0
    scripted = instructions.get(SCRIPTED_PLAN_KEY)
    if isinstance(scripted, list):
        return sum(1 for item in scripted if str(item).strip())
    return 0


def _should_force_transition_to_practice(
    *,
    user_text: str,
    messages: list[dict],
    state: LearningSessionState,
) -> bool:
    """Escape valve: progress to practice when the strict gate misses it.

    Triggers when:
      - the teacher has produced at least as many turns as the authored plan
        (or `_DEFAULT_TEACHING_TURN_CEILING` if no plan is available),
      - any prior tutor message mentions "practice task/exercise/activity",
      - the learner reply is a plausible affirmative and not a negation.
    """
    if not _is_short_affirmative_or_short_reply(user_text):
        return False
    if not _any_tutor_mentioned_practice_task(messages):
        return False
    teacher_turns = _count_teacher_chat_turns(messages)
    plan_len = _scripted_plan_length(state) or _DEFAULT_TEACHING_TURN_CEILING
    return teacher_turns >= plan_len


# ----------------------------------------------------------------------------
# Learner-message input gate (gibberish / off-topic during teaching)
# ----------------------------------------------------------------------------
#
# Mirror image of the teacher-side `validate_teaching_message()` gate in
# `app/ai/agents/teacher.py`: before the teacher LLM ever sees a learner reply
# during the teaching phase, confront gibberish / off-topic text, restate the
# topic, and re-ask the same step — never advance. A wrong-but-relevant answer
# is fine (the teacher corrects it); only structural junk or clearly unrelated
# text trips this gate.

_VOWELS = frozenset("aeiouy")

# After this many consecutive redirects, escalate to a simpler-version message
# instead of looping the same probe (prevents an infinite redirect loop).
_REDIRECT_ESCALATION_THRESHOLD = 3


def _is_confusion(text: str) -> bool:
    """True when the reply is a recognised confusion / not-ready phrase.

    Confusion is legitimate — the existing teacher flow re-explains — so the
    input gate must let these through rather than treating them as off-topic.
    """
    cleaned = (text or "").strip().lower()
    if not cleaned:
        return False
    return any(pattern.search(cleaned) for pattern in _NON_UNDERSTANDING_PATTERNS)


def _is_structural_gibberish(text: str) -> bool:
    """Deterministic, free check for structurally meaningless input.

    Flags obvious junk: empty/whitespace-only, all-punctuation/symbols, a
    single repeated character ("aaaaaa"), pure non-ASCII runs, or text whose
    word-tokens are all vowel-less consonant runs ("asdkjfh").

    Length alone is NEVER a trigger: short valid answers like "Walk." or
    "I go." must pass. Only the *structure* of the characters matters.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return True

    lowered = cleaned.lower()

    # Pure ASCII letters/digits content — strip everything else to inspect.
    alnum = [c for c in lowered if c.isalnum()]
    if not alnum:
        # No letters or digits at all (all punctuation / symbols / emoji).
        return True

    # No ASCII letters at all (e.g. pure non-Latin script or digits-only).
    ascii_letters = [c for c in alnum if "a" <= c <= "z"]
    if not ascii_letters:
        return True

    # A single character repeated (after removing spaces): "aaaaaa", "!!!".
    compact = lowered.replace(" ", "")
    if len(compact) >= 4 and len(set(compact)) == 1:
        return True

    # Inspect the alphabetic word-tokens for keyboard-mash structure:
    #   - a vowel-less token of length >= 5 ("zxcvb"), or
    #   - a consonant run of length >= 6 ("asdkjfh" -> "sdkjfh") — longer than
    #     any real English cluster, so safe words like "lengths"/"strength"
    #     (max run 5/4) pass.
    for token in re.findall(r"[a-z]+", lowered):
        if len(token) >= 5 and not (set(token) & _VOWELS):
            return True
        run = 0
        for ch in token:
            if ch in _VOWELS:
                run = 0
                continue
            run += 1
            if run >= 6:
                return True

    return False


def _count_trailing_redirects(messages: list[dict]) -> int:
    """Count consecutive trailing AI redirect turns.

    The redirect counter is derived from the persisted `messages` list (each
    redirect AI turn is tagged ``redirect=True``) rather than a DB column —
    same pattern as `_count_teacher_chat_turns`.
    """
    count = 0
    for message in reversed(messages):
        if message.get("role") not in ("ai", "assistant"):
            # A learner turn between redirects doesn't break the streak; keep
            # scanning past it. (Each redirect answers exactly one user turn.)
            continue
        if message.get("redirect") is True:
            count += 1
            continue
        break
    return count


def _count_trailing_stays(messages: list[dict]) -> int:
    """Count consecutive trailing AI re-teach ("stayed") turns.

    Same derivation as `_count_trailing_redirects`: a re-teach turn (emitted
    when the learner is confused and the cursor is held on the current step)
    is tagged ``stayed=True``. Counting from the tail measures how long the
    learner has been stuck on one step. No DB column — derived from the
    persisted `messages` list.
    """
    count = 0
    for message in reversed(messages):
        if message.get("role") not in ("ai", "assistant"):
            continue
        if message.get("stayed") is True:
            count += 1
            continue
        break
    return count


def _count_green_path_turns(messages: list[dict]) -> int:
    """Count teacher chat turns that *advanced* the lesson (the script cursor).

    The adaptive teaching loop decouples the script cursor from the raw
    teacher-turn count: only "green-path" turns (a genuine answer was accepted)
    move the cursor. Redirects (``redirect=True``) and re-teaches
    (``stayed=True``) hold the learner on the current step, so they are
    excluded here. The first green-path turn is the lesson opener (step 1).
    """
    count = 0
    for message in messages:
        if message.get("role") not in ("ai", "assistant"):
            continue
        if str(message.get("type") or "chat") != "chat":
            continue
        if message.get("redirect") is True or message.get("stayed") is True:
            continue
        count += 1
    return count


def _stuck_on_step_count(messages: list[dict]) -> int:
    """Consecutive non-advancing trailing turns since the last accepted answer.

    A single scan counting trailing AI turns that are EITHER a redirect or a
    re-teach (the two break each other when interleaved, so summing the
    separate counters would undercount). This is the dial the safety net uses
    to decide a learner is stuck on one step and must be eased forward.
    """
    count = 0
    for message in reversed(messages):
        if message.get("role") not in ("ai", "assistant"):
            continue
        if message.get("redirect") is True or message.get("stayed") is True:
            count += 1
            continue
        break
    return count


def _build_redirect_message(
    *,
    topic: str,
    previous_tutor_message: str,
    redirect_count: int,
    reason: str,
) -> str:
    """Deterministic confront-and-restate message for the input gate.

    Names what happened, restates the current topic, and re-asks the same step
    by reusing the tutor's previous question. After repeated redirects it
    escalates to a simpler-version message instead of looping the same probe.

    `reason` is one of "gibberish" or "off_topic".
    """
    topic_label = (topic or "today's topic").strip()
    re_ask = (previous_tutor_message or "").strip()

    if redirect_count >= _REDIRECT_ESCALATION_THRESHOLD:
        msg = (
            f"Let's try an easier version. We are still learning {topic_label}. "
            "Don't worry about getting it perfect — just write one short, "
            "simple sentence and I'll help you fix it."
        )
        return msg

    if reason == "gibberish":
        opener = "Hmm, I couldn't follow that."
    else:
        opener = "That looks off-topic."

    parts = [
        f"{opener} We are still on {topic_label}.",
    ]
    if re_ask:
        parts.append(f"Let's stay with this: {re_ask}")
    else:
        parts.append("Try the current step again with one short sentence in English.")
    return " ".join(parts)


class LearningSessionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.session_repo = LearningSessionRepository(db)
        self.daily_repo = DailySessionRepository(db)
        self.attempts_repo = ActivityAttemptRepository(db)
        self.curriculum_day_repo = CurriculumDayRepository(db)
        self.archetype_repo = TaskArchetypeRepository(db)
        self.profile_repo = UserProfileRepository(db)
        self.event_orchestrator = SessionEventOrchestrator()

    # ------------------------------------------------------------------
    # Session creation
    # ------------------------------------------------------------------

    async def create_session(
        self,
        *,
        user_id: int,
        daily_session_id: int | None = None,
    ) -> StartSessionResponse:
        """Create a chat session layered on the user's V2 DailySession.

        If `daily_session_id` is None, find/create today's DailySession via
        `UserCoursePreference`. Resume the existing LearningSession if one
        already exists for that DailySession.
        """
        t0 = time.perf_counter()
        daily = await self._resolve_daily_session(
            user_id=user_id, daily_session_id=daily_session_id
        )
        resolve_daily_ms = (time.perf_counter() - t0) * 1000

        # Resume an existing chat envelope if one exists for this DailySession.
        existing = self.session_repo.get_by_daily_session_id(daily.id)
        if existing is not None:
            # Auto-refresh the whole chat persona for file-authored days.
            # Existing envelopes may have been created before the source
            # day was authored, or before file-mode carried the full persona.
            self._maybe_refresh_file_persona(existing, daily.day_id)
            log.info(
                "session_create_resumed",
                user_id=user_id,
                daily_session_id=daily.id,
                total_ms=round((time.perf_counter() - t0) * 1000),
            )
            return StartSessionResponse(
                session_id=existing.session_id,
                daily_session_id=daily.id,
                topic=existing.topic,
                skill_name=existing.skill_name,
                task_type=existing.task_type,
                message="Session resumed",
            )

        attempts = self.attempts_repo.list_for_session(daily.id)
        if not attempts:
            raise LearningSessionTaskUnavailable(
                f"DailySession {daily.session_id} has no activity attempts"
            )
        first = attempts[0]

        file_persona: tuple[str, str, int, dict | None] | None = None
        try:
            file_persona = self._persona_from_file(daily.day_id)
        except DayNotFound:
            file_persona = None

        planner_ms: float | None = None
        if file_persona is not None:
            topic_label, skill_name, sub_level, teacher_instructions = file_persona
            activity_type = self._activity_type_from_archetype(first.archetype_id)
        else:
            day = self.curriculum_day_repo.get_by_day_id(daily.day_id)
            if day is None:
                raise LookupError(f"CurriculumDay day_id={daily.day_id!r} not found")
            week = day.week
            if week is None:
                raise LookupError(
                    f"CurriculumWeek for day_id={daily.day_id!r} not found"
                )
            archetype = self.archetype_repo.get(first.archetype_id)
            if archetype is None:
                raise LookupError(
                    f"TaskArchetype archetype_id={first.archetype_id!r} not found"
                )
            topic_dict = v2_course_topic(day, week, archetype)
            course_slug = f"{daily.course_length}-course"
            learner_profile = self._profile_context(user_id)
            planner_t0 = time.perf_counter()
            try:
                plan = await PlannerAgent().generate(
                    user_id=user_id,
                    course_slug=course_slug,
                    topic_entry=topic_dict,
                    learner_profile=learner_profile,
                )
            except Exception:
                log.exception(
                    "planner_agent_failed",
                    user_id=user_id,
                    daily_session_id=daily.session_id,
                    note="using neutral persona",
                )
                capture_to_sentry()
                plan = {"teacher_instructions": None}
            planner_ms = (time.perf_counter() - planner_t0) * 1000
            topic_label = day.topic
            skill_name = topic_dict["sub_skill"]
            sub_level = topic_dict["sub_level"]
            activity_type = archetype.core_activity
            teacher_instructions = plan.get("teacher_instructions")

        session_id = uuid.uuid4().hex
        persist_t0 = time.perf_counter()
        self.session_repo.create(
            session_id=session_id,
            user_id=user_id,
            daily_session_id=daily.id,
            topic=topic_label,
            skill_name=skill_name,
            activity_type=activity_type,
            task_type=activity_type,
            user_level=sub_level,
            pre_generated_tasks=dict(first.task_content or {}),
            task_queue=self._queue_from_attempts(attempts),
            teacher_instructions=teacher_instructions,
        )
        self.db.commit()

        log.info(
            "session_create_timing",
            user_id=user_id,
            daily_session_id=daily.id,
            file_authored=file_persona is not None,
            resolve_daily_ms=round(resolve_daily_ms),
            planner_ms=round(planner_ms) if planner_ms is not None else None,
            persist_ms=round((time.perf_counter() - persist_t0) * 1000),
            total_ms=round((time.perf_counter() - t0) * 1000),
        )

        return StartSessionResponse(
            session_id=session_id,
            daily_session_id=daily.id,
            topic=topic_label,
            skill_name=skill_name,
            task_type=activity_type,
            message="Session ready",
        )

    def _persona_from_file(
        self,
        day_id: str,
    ) -> tuple[str, str, int, dict | None]:
        """Build (topic, skill_name, sub_level, teacher_context) from source_24w.py.

        File-authored days intentionally give the teacher only title,
        description, and authored behavior. The description is stored as
        `lesson_description`; the behavior script is stored under the
        reserved `__scripted_plan` key for the streaming side.
        """
        file_day = file_get_day_by_id(day_id)
        teacher_instructions: dict = file_build_teacher_instructions(file_day)
        if file_day.teacher_agent_behaviour:
            # See `SCRIPTED_PLAN_KEY` in `file_source` for the contract.
            teacher_instructions[SCRIPTED_PLAN_KEY] = list(
                file_day.teacher_agent_behaviour
            )
        return (
            file_day.topic,
            file_day.theme_type,
            file_day.sub_level_min,
            teacher_instructions,
        )

    def _maybe_refresh_file_persona(
        self,
        session: LearningSession,
        day_id: str,
        *,
        commit: bool = True,
    ) -> bool:
        """Refresh chat persona fields from source for file-authored days.

        The chat layer stores a runtime copy of the day title/theme/sub-level
        plus teacher instructions. Refreshing all four fields keeps resumed
        sessions aligned with the authored ``DaySource`` without changing
        the daily-session-owned activity queue or task content.
        """
        try:
            topic, skill_name, user_level, teacher_instructions = (
                self._persona_from_file(day_id)
            )
        except DayNotFound:
            return False  # not a file-authored day — leave as-is

        session.topic = topic
        session.skill_name = skill_name
        session.user_level = user_level
        session.teacher_instructions = teacher_instructions
        self.session_repo.save(session)
        if commit:
            self.db.commit()
        return True

    def _activity_type_from_archetype(self, archetype_id: str) -> str:
        """Look up `core_activity` for an archetype without hitting the DB."""
        from app.scoring import get_archetype as scoring_get_archetype

        return scoring_get_archetype(archetype_id).core_activity

    async def _resolve_daily_session(
        self,
        *,
        user_id: int,
        daily_session_id: int | None,
    ) -> DailySession:
        """Return the DailySession the chat will be layered on.

        Explicit id: load and verify ownership.
        No id: find/create today's session via UserCoursePreference.
        """
        if daily_session_id is not None:
            daily = self.db.get(DailySession, int(daily_session_id))
            if daily is None:
                raise LookupError(f"DailySession id={daily_session_id} not found")
            if daily.user_id != user_id:
                raise PermissionError(
                    f"User {user_id} cannot start session for daily {daily_session_id}"
                )
            return daily

        # No id — find or create today's session for the user.
        pref = PreferenceService(self.db).get(user_id=user_id)
        from app.modules.curriculum.repository import CurriculumWeekRepository

        week = CurriculumWeekRepository(self.db).get_by_number(
            course_length=pref.course_length,
            week_number=pref.current_week,
        )
        if week is None:
            raise LookupError(
                f"No curriculum week for course_length={pref.course_length!r} "
                f"week={pref.current_week}"
            )
        day = CurriculumDayRepository(self.db).get_for_week(
            week_pk=week.id,
            day_number=pref.current_day_in_week,
        )
        if day is None:
            raise LookupError(
                f"No curriculum day for week_id={week.week_id!r} "
                f"day={pref.current_day_in_week}"
            )

        allowed = {
            a
            for a, on in {
                "read": pref.allow_read,
                "write": pref.allow_write,
                "listen": pref.allow_listen,
                "speak": pref.allow_speak,
            }.items()
            if on
        }

        # If today's session already exists, return it. A completed session
        # should route to its scorecard, not create a fresh chat attempt.
        existing = self.daily_repo.get_in_progress(user_id=user_id, day_id=day.day_id)
        if existing is not None:
            if not self._abandon_stale_file_session_if_unstarted(
                existing,
                allowed_activities=allowed,
            ):
                return existing
        existing = self.daily_repo.get_latest_for_day(
            user_id=user_id, day_id=day.day_id, status=SessionStatus.COMPLETED
        )
        if existing is not None:
            return existing

        # Otherwise start a fresh V2 session for today.
        v2_service = _make_v2_session_service(self.db)
        try:
            return await v2_service.start_session(
                user_id=user_id,
                day_id=day.day_id,
                course_length=CourseLength(pref.course_length),
                tasks_per_day=pref.tasks_per_day,
                allowed_activities=allowed,
            )
        except SessionAlreadyOpen:
            # Race / retry — fetch the row another process created.
            existing = self.daily_repo.get_in_progress(
                user_id=user_id, day_id=day.day_id
            )
            if existing is None:
                raise
            return existing

    def _abandon_stale_file_session_if_unstarted(
        self,
        daily: DailySession,
        *,
        allowed_activities: set[str],
    ) -> bool:
        try:
            file_day = file_get_day_by_id(daily.day_id)
        except DayNotFound:
            return False
        expected = [
            spec.archetype_id
            for spec in file_resolve_archetypes(file_day)
            if spec.core_activity in allowed_activities
        ]
        attempts = self.attempts_repo.list_for_session(daily.id)
        if any(a.status is not AttemptStatus.PENDING for a in attempts):
            return False
        current = [a.archetype_id for a in attempts]
        if current == expected:
            return False
        daily.status = SessionStatus.ABANDONED
        self.db.add(daily)
        self.db.commit()
        return True

    @staticmethod
    def _queue_from_attempts(attempts: list[ActivityAttempt]) -> list[dict[str, Any]]:
        blueprint = runtime_blueprint_from_attempts(attempts)
        activities_by_sequence = {
            item.get("sequence"): item for item in blueprint.get("activities", [])
        }
        queue: list[dict[str, Any]] = []
        for a in attempts:
            sequence = int(a.sequence)
            contract = dict(
                activities_by_sequence.get(sequence)
                or activity_contract_from_content(
                    dict(a.task_content or {}),
                    sequence=sequence,
                    archetype_id=a.archetype_id,
                    is_mandatory=a.is_mandatory,
                )
            )
            queue.append(
                {
                    "sequence": a.sequence,
                    "archetype_id": a.archetype_id,
                    "is_mandatory": a.is_mandatory,
                    "status": (
                        a.status.value if hasattr(a.status, "value") else str(a.status)
                    ),
                    "activity_id": contract.get("activity_id"),
                    "task_widget": contract.get("task_widget"),
                    "evaluator_type": contract.get("evaluator_type"),
                    "evaluation_widget": contract.get("evaluation_widget"),
                    "feedback_type": contract.get("feedback_type"),
                    "feedback_widget": contract.get("feedback_widget"),
                    "activity_contract": contract,
                }
            )
        return queue

    def _sync_task_queue_from_attempts(self, session: LearningSession) -> None:
        """Rebuild ``session.task_queue`` from the authoritative V2 attempts.

        The chat ``task_queue`` JSON caches each activity's status; it drifts
        whenever the V2 attempts change (submit, reset, restart). Calling this
        after any such mutation keeps the queue consistent with V2 truth. Only
        the field is reassigned here — the caller owns the save/commit.
        """
        attempts = self.attempts_repo.list_for_session(session.daily_session_id)
        session.task_queue = self._queue_from_attempts(attempts)

    async def restart_session(
        self,
        *,
        session_id: str,
        user_id: int,
    ) -> StartSessionResponse:
        """Restart the whole day: full wipe of chat + V2 progress.

        Deletes every attempt's evaluation/feedback, resets all attempts to
        PENDING (clearing user_response/submitted_at), deletes the
        SessionScorecard, reopens the DailySession (IN_PROGRESS,
        completed_at=None), and resets the chat envelope (messages, phase,
        index, understanding_confirmed) with the task_queue rebuilt from the
        now-pending attempts. Also re-runs the PlannerAgent so
        teacher_instructions reflect any curriculum changes since creation.
        """
        session = self._load_session(session_id)
        if session.user_id != user_id:
            raise PermissionError(f"User {user_id} cannot restart session {session_id}")

        # Load the linked daily session up-front so it is always bound, even if
        # the best-effort teacher-instructions refresh below raises.
        daily = self.db.get(DailySession, session.daily_session_id)

        # Refresh teacher instructions against current curriculum data so
        # content edits in source_24w.py or curriculum_days take effect on
        # the next teaching turn.  Try file persona first, fall back to
        # DB-driven planner.
        try:
            if daily is not None:
                teacher_instructions = None
                if self._maybe_refresh_file_persona(
                    session,
                    daily.day_id,
                    commit=False,
                ):
                    teacher_instructions = session.teacher_instructions

                day = self.curriculum_day_repo.get_by_day_id(daily.day_id)
                if (
                    teacher_instructions is None
                    and day is not None
                    and day.week is not None
                ):
                    task_queue = session.task_queue or []
                    archetype_id = task_queue[0]["archetype_id"] if task_queue else None
                    archetype = (
                        self.archetype_repo.get(archetype_id) if archetype_id else None
                    )
                    if archetype is not None:
                        topic_dict = v2_course_topic(day, day.week, archetype)
                        course_slug = f"{daily.course_length}-course"
                        plan = await PlannerAgent().generate(
                            user_id=user_id,
                            course_slug=course_slug,
                            topic_entry=topic_dict,
                            learner_profile=self._profile_context(user_id),
                        )
                        session.teacher_instructions = plan.get("teacher_instructions")
        except Exception:
            log.warning(
                "teacher_instructions_refresh_failed",
                session_id=session_id,
                note="keeping existing instructions",
            )

        session.messages = []
        session.user_submission = None
        session.evaluation = None
        session.feedback = None
        session.understanding_confirmed = False
        session.phase = "teaching"
        session.current_task_index = 0
        session.pre_generated_tasks = {}

        # Reset all activity attempts for this daily session so the full
        # activity queue becomes available again from the beginning. Delegate to
        # SessionService so the chat layer no longer writes V2 scoring tables
        # directly; it resets every attempt to PENDING, drops the scorecard,
        # reopens the day (committing immediately), and schedules best-effort
        # background RAG vector cleanup.
        if daily is not None:
            await _make_v2_session_service(self.db).reset_session_full(
                session_id=daily.session_id,
                user_id=user_id,
            )

        # Rebuild the chat task_queue so every entry reflects PENDING again.
        self._sync_task_queue_from_attempts(session)
        self.session_repo.save(session)
        self.db.commit()

        return StartSessionResponse(
            session_id=session.session_id,
            daily_session_id=session.daily_session_id,
            topic=session.topic,
            skill_name=session.skill_name,
            task_type=session.task_type,
            message="Session restarted",
        )

    async def reset_activity(
        self,
        *,
        session_id: str,
        user_id: int,
        sequence: int,
    ) -> StartSessionResponse:
        """Reset a single activity so the learner can retry it.

        Delegates the authoritative reset (clear evaluation/feedback, flip the
        attempt back to PENDING, reopen the day + drop the stale scorecard) to
        the V2 ``SessionService``, then points the chat envelope back at that
        activity and rebuilds the task_queue from the refreshed attempts.
        """
        session = self._load_session(session_id)
        if session.user_id != user_id:
            raise PermissionError(
                f"User {user_id} cannot reset activity on session {session_id}"
            )
        daily = self.db.get(DailySession, session.daily_session_id)
        if daily is None:
            raise LookupError(f"DailySession id={session.daily_session_id} not found")

        await _make_v2_session_service(self.db).reset_activity(
            session_id=daily.session_id,
            user_id=user_id,
            sequence=int(sequence),
        )

        session.phase = "practice_task"
        session.current_task_index = max(int(sequence) - 1, 0)
        session.user_submission = None
        session.evaluation = None
        session.feedback = None
        # Clear the cached task content; resume/state re-read it from the live
        # attempt. Empty dict (not None) honours the non-nullable column.
        session.pre_generated_tasks = {}
        self._sync_task_queue_from_attempts(session)
        self.session_repo.save(session)
        self.db.commit()

        return StartSessionResponse(
            session_id=session.session_id,
            daily_session_id=session.daily_session_id,
            topic=session.topic,
            skill_name=session.skill_name,
            task_type=session.task_type,
            message="Activity reset",
        )

    async def regenerate_activity(
        self,
        *,
        session_id: str,
        user_id: int,
        sequence: int,
    ) -> StartSessionResponse:
        """Reset one activity **and re-roll a brand-new task**, bypassing the cache.

        Unlike ``reset_activity`` (which replays the same cached task), this
        delegates to the V2 ``SessionService.regenerate_activity`` — which
        re-arms the lazy-taskgen placeholder and generates fresh content — then
        points the chat envelope back at that activity and rebuilds the
        task_queue from the refreshed attempts. Powers the chat menu's "Restart
        current activity"; the feedback "Retry" button keeps ``reset_activity``.
        """
        session = self._load_session(session_id)
        if session.user_id != user_id:
            raise PermissionError(
                f"User {user_id} cannot regenerate activity on session {session_id}"
            )
        daily = self.db.get(DailySession, session.daily_session_id)
        if daily is None:
            raise LookupError(f"DailySession id={session.daily_session_id} not found")

        await _make_v2_session_service(self.db).regenerate_activity(
            session_id=daily.session_id,
            user_id=user_id,
            sequence=int(sequence),
        )

        session.phase = "practice_task"
        session.current_task_index = max(int(sequence) - 1, 0)
        session.user_submission = None
        session.evaluation = None
        session.feedback = None
        # Clear the cached task content; resume/state re-read it from the live
        # attempt (now carrying freshly generated content). Empty dict (not
        # None) honours the non-nullable column.
        session.pre_generated_tasks = {}
        self._sync_task_queue_from_attempts(session)
        self.session_repo.save(session)
        self.db.commit()

        return StartSessionResponse(
            session_id=session.session_id,
            daily_session_id=session.daily_session_id,
            topic=session.topic,
            skill_name=session.skill_name,
            task_type=session.task_type,
            message="Activity regenerated",
        )

    async def regenerate_feedback(
        self,
        *,
        session_id: str,
        user_id: int,
        sequence: int,
    ) -> dict[str, Any]:
        """Re-run feedback for one already-graded activity and return the card.

        Delegates to the V2 ``SessionService.regenerate_feedback`` (which reuses
        the stored evaluation — the score and graded response are NOT touched),
        then projects the refreshed row into the same ``feedback_card`` shape the
        WebSocket emits so the chat UI can swap it in place. Also refreshes the
        chat envelope's cached feedback so a reload shows the regenerated card.
        """
        session = self._load_session(session_id)
        if session.user_id != user_id:
            raise PermissionError(
                f"User {user_id} cannot regenerate feedback on session {session_id}"
            )
        daily = self.db.get(DailySession, session.daily_session_id)
        if daily is None:
            raise LookupError(f"DailySession id={session.daily_session_id} not found")

        feedback, is_fallback = await _make_v2_session_service(
            self.db
        ).regenerate_feedback(
            session_id=daily.session_id,
            user_id=user_id,
            sequence=int(sequence),
        )
        attempt = feedback.attempt

        feedback_dict: dict[str, Any] = {
            "feedback_id": feedback.id,
            "score": feedback.score,
            "summary": feedback.summary,
            "did_well": list(feedback.did_well or []),
            "mistakes": list(feedback.mistakes or []),
            "next_tip": feedback.next_tip,
            "sub_skill_breakdown": dict(feedback.sub_skill_breakdown or {}),
            # Stays True if the regenerate itself fell back — keeps the
            # "Regenerate feedback" affordance available for another try.
            "feedback_fallback": is_fallback,
        }
        try:
            feedback_dict.update(
                project_feedback(
                    attempt.archetype_id,
                    activity_id=str(attempt.id),
                    feedback=FeedbackResult(
                        score=int(feedback.score),
                        summary=feedback.summary or "",
                        did_well=tuple(feedback.did_well or ()),
                        mistakes=tuple(
                            MistakeOut(
                                issue=str(m.get("issue") or ""),
                                user_wrote=m.get("user_wrote"),
                                correction=m.get("correction"),
                                rule=m.get("rule"),
                                sub_skills_affected=tuple(
                                    m.get("sub_skills_affected") or ()
                                ),
                            )
                            for m in (feedback.mistakes or [])
                            if isinstance(m, dict)
                        ),
                        next_tip=feedback.next_tip,
                        sub_skill_breakdown=dict(feedback.sub_skill_breakdown or {}),
                    ),
                )
            )
        except ContractValidationError as exc:
            if settings.strict_contracts:
                raise
            log.warning(
                "contract_projection_failed_regenerate_feedback",
                attempt_id=attempt.id,
                archetype=attempt.archetype_id,
                detail=exc.detail,
                note="returning legacy feedback payload",
            )

        # Keep the chat envelope's cached feedback in step so a reload/hydrate
        # renders the regenerated card, but only when this is the activity the
        # envelope is currently parked on (don't clobber a later activity).
        if int(session.current_task_index or 0) == max(int(sequence) - 1, 0):
            session.feedback = feedback_dict
            self.session_repo.save(session)
            self.db.commit()

        return feedback_dict

    # ------------------------------------------------------------------
    # WebSocket message handling
    # ------------------------------------------------------------------

    async def initial_messages_stream(
        self, session_id: str
    ) -> AsyncIterator[WSOutgoingMessage]:
        """Stream the first teaching turn when the WebSocket connects.

        The blueprint is yielded immediately so the learner sees the lesson
        frame, then the real teaching opener streams straight in under the
        chat skeleton — no "give me a moment" wait message. Teaching is fast
        now (task generation runs lazily off the critical path), so the opener
        itself is the first thing the learner reads.
        """
        t0 = time.perf_counter()
        first_yield_ms: float | None = None
        teaching_first_chunk_ms: float | None = None
        try:
            session = self._load_session(session_id)
            daily = await self._auto_complete_daily_if_ready(session)
            if daily is not None and daily.status is SessionStatus.COMPLETED:
                async for msg in self._stream_completed_daily_message():
                    if first_yield_ms is None:
                        first_yield_ms = (time.perf_counter() - t0) * 1000
                    yield msg
                return
            state = self._state_from_row(session)
            self._enrich_state_with_profile(state, session.user_id)
            yield self._session_blueprint_message(session, state)
            first_yield_ms = (time.perf_counter() - t0) * 1000

            async for msg in self._stream_teaching_turn(session, state):
                if teaching_first_chunk_ms is None and msg.type == "chat_stream_delta":
                    teaching_first_chunk_ms = (time.perf_counter() - t0) * 1000
                yield msg
        finally:
            # Logged in `finally` so a mid-stream disconnect still records
            # how far the learner got.
            log.info(
                "ws_initial_stream_timing",
                session_id=session_id,
                first_yield_ms=(
                    round(first_yield_ms) if first_yield_ms is not None else None
                ),
                teaching_first_chunk_ms=(
                    round(teaching_first_chunk_ms)
                    if teaching_first_chunk_ms is not None
                    else None
                ),
                total_ms=round((time.perf_counter() - t0) * 1000),
            )

    async def resume_messages_stream(
        self, session_id: str
    ) -> AsyncIterator[WSOutgoingMessage]:
        """Replay enough state for a previously-started chat to continue.

        Resume keys off V2 attempt truth, not just the stored ``phase``:
        if teaching is confirmed and an activity is still pending we resume
        at that activity even when ``phase`` is stale. Evaluation/feedback
        widgets for already-completed activities are never re-emitted here;
        the ``/state`` snapshot carries their summaries for the UI.
        """
        session = self._load_session(session_id)
        # Reconcile the cached queue with the V2 attempts first — every resume
        # decision below depends on attempt status.
        self._sync_task_queue_from_attempts(session)
        self.db.commit()
        state = self._state_from_row(session)
        self._enrich_state_with_profile(state, session.user_id)

        # If the V2 DailySession is already complete, end the chat.
        daily = await self._auto_complete_daily_if_ready(session)
        if daily is not None and daily.status is SessionStatus.COMPLETED:
            async for msg in self._stream_completed_daily_message():
                yield msg
            return

        yield self._session_blueprint_message(session, state)

        # Teaching not yet confirmed → replay the last tutor turn (or welcome).
        if session.phase == "teaching" and not session.understanding_confirmed:
            previous = _last_tutor_message(session.messages or [])
            message = previous or (
                f"Welcome back. We are learning {session.topic}. "
                "Tell me when you feel ready for the first activity."
            )
            async for msg in self._stream_chat_text(message):
                yield msg
            return

        # Teaching confirmed with a pending activity (whatever the stale stored
        # phase is — "practice_task" OR a just-finished "feedback") → resume
        # directly at the next pending activity. The chat UI shows the completed
        # activities in its retry list alongside it; finished activities'
        # eval/feedback are a live-submit-only view and are NOT replayed here.
        if session.understanding_confirmed and (
            self._next_pending_attempt(session) is not None
        ):
            async for msg in self._resume_practice_task(session):
                yield msg
            return

        # Pass-mark gate: an EVALUATED-but-failed attempt left the day open with
        # no pending activity (the learner dropped before clicking Retry, or
        # left via the dashboard). Reset that attempt back to PENDING and
        # re-deliver it so the reconnect lands on the retry — never on a bogus
        # "day complete" message.
        gate_required, gate_threshold = self._gate_settings(session.user_id)
        if (
            session.understanding_confirmed
            and daily is not None
            and daily.status is SessionStatus.IN_PROGRESS
            and gate_required
            and self._has_unpassed_gated_attempt(daily, gate_threshold)
        ):
            failed = next(
                (
                    a
                    for a in self.attempts_repo.list_for_session(daily.id)
                    if a.status is AttemptStatus.EVALUATED
                    and not self._attempt_passes_gate(a, gate_threshold)
                ),
                None,
            )
            if failed is not None:
                await _make_v2_session_service(self.db).reset_activity(
                    session_id=daily.session_id,
                    user_id=session.user_id,
                    sequence=int(failed.sequence),
                )
                self._sync_task_queue_from_attempts(session)
                self.db.commit()
                async for msg in self._resume_practice_task(session):
                    yield msg
                return

        if session.phase == "ended":
            message = (
                "This chat is finished. Go back to the dashboard when you're ready."
            )
            async for msg in self._stream_chat_text(
                message,
                actions=["Go to dashboard"],
            ):
                yield msg
            return

        # Teaching confirmed and no activity left to do → the day is finished;
        # announce completion so the UI shows the final day result.
        async for msg in self._stream_completed_daily_message():
            yield msg

    async def _resume_practice_task(
        self, session: LearningSession
    ) -> AsyncIterator[WSOutgoingMessage]:
        """Emit the chat + task event needed to resume the pending activity."""
        attempt = self._next_pending_attempt(session)
        if attempt is None:
            return
        total = len(session.task_queue or []) or 1
        current = max(int(attempt.sequence) - 1, 0)
        message = f"Welcome back. Continue with activity {current + 1} of {total}."
        yield WSOutgoingMessage(
            type="chat_message",
            role="assistant",
            content=message,
        )
        # Self-heal stale snapshots: a `pre_generated_tasks` cached by an older
        # code path may be missing listening fields. Pull the live attempt,
        # repair its content, and write it back so the widget renders.
        attempt = await self._prepare_attempt_for_delivery(attempt)
        task_content_payload = dict(attempt.task_content or {})
        session.pre_generated_tasks = task_content_payload
        session.current_task_index = current
        # Normalise a stale "feedback" phase: the learner is back on a task now,
        # so persist practice_task to keep the stored phase coherent.
        session.phase = "practice_task"
        self.session_repo.save(session)
        self.db.commit()

        payload = {
            **task_content_payload,
            "_session": {
                "current_task_index": current,
                "total_tasks": total,
                "daily_session_id": session.daily_session_id,
            },
        }
        widget = normalize_widget_key(
            str(payload.get("widget") or payload.get("ui_widget") or session.task_type)
        )
        yield self._event_orchestrator().task_event(
            widget=widget,
            task_payload={**payload, "widget": widget},
            session_meta=payload.get("_session"),
        )

    def _resume_checkpoint(self, session: LearningSession) -> dict[str, Any]:
        """Derive the resume checkpoint from V2 attempts + chat envelope state.

        No persisted checkpoint column — V2 attempts are the source of truth.
        """
        attempts = self.attempts_repo.list_for_session(session.daily_session_id)
        completed = [
            int(a.sequence) for a in attempts if a.status is AttemptStatus.EVALUATED
        ]
        pending = next((a for a in attempts if a.status is AttemptStatus.PENDING), None)
        teaching_completed = bool(session.understanding_confirmed)
        if not teaching_completed:
            last_phase = "teaching"
        elif pending is not None:
            # A pending activity always wins — resume lands the learner on the
            # next activity (completed ones live in the retry list), never on a
            # replayed feedback view for an already-finished activity.
            last_phase = "practice_task"
        else:
            last_phase = "ended"
        return {
            "teaching_completed": teaching_completed,
            "current_sequence": int(pending.sequence) if pending is not None else None,
            "completed_sequences": completed,
            "last_resumable_phase": last_phase,
        }

    def _completed_activity_summaries(
        self, session: LearningSession
    ) -> list[dict[str, Any]]:
        """Compact per-completed-activity summaries from V2 attempt evaluations.

        One row per EVALUATED attempt with a stored evaluation:
        ``{sequence, archetype_id, label, archetype_label, widget, raw_score}``.
        The chat UI renders these as read-only rows on resume (with a Retry
        button) instead of replaying the full evaluation/feedback widgets.
        """
        summaries: list[dict[str, Any]] = []
        for attempt in self.attempts_repo.list_for_session(session.daily_session_id):
            if attempt.status is not AttemptStatus.EVALUATED:
                continue
            evaluation = attempt.evaluation
            if evaluation is None:
                continue
            spec = get_archetype(attempt.archetype_id)
            content = dict(attempt.task_content or {})
            widget = normalize_widget_key(
                str(
                    content.get("widget")
                    or content.get("ui_widget")
                    or spec.ui_widget
                    or ""
                )
            )
            summaries.append(
                {
                    "sequence": int(attempt.sequence),
                    "archetype_id": attempt.archetype_id,
                    "label": _CORE_ACTIVITY_LABELS.get(
                        spec.core_activity, spec.core_activity.title()
                    ),
                    "archetype_label": spec.name,
                    "widget": widget,
                    "raw_score": float(evaluation.raw_score),
                }
            )
        return summaries

    async def get_state_snapshot(self, session_id: str, user_id: int) -> dict[str, Any]:
        """Build the REST hydrate payload the chat UI renders before/without WS.

        Returns phase, messages, task_queue, the current actionable task, the
        last evaluation/feedback for the current sequence, the blueprint meta,
        and the derived resume checkpoint (completed_sequences, etc).
        """
        session = self._load_session(session_id)
        if session.user_id != user_id:
            raise PermissionError(
                f"User {user_id} cannot read state for session {session_id}"
            )
        self._sync_task_queue_from_attempts(session)
        self.db.commit()

        daily = await self._auto_complete_daily_if_ready(session)
        daily_completed = daily is not None and daily.status is SessionStatus.COMPLETED
        checkpoint = self._resume_checkpoint(session)

        current_task: dict[str, Any] | None = None
        pending = self._next_pending_attempt(session)
        if pending is not None and not daily_completed:
            pending = await self._prepare_attempt_for_delivery(pending)
            current_task = dict(pending.task_content or {})

        state = self._state_from_row(session)
        self._enrich_state_with_profile(state, session.user_id)
        blueprint = self._session_blueprint_message(session, state)

        # Re-attach the viewer's reaction to the most recent feedback so a
        # persisted 👍/👎 re-renders on reload (the stored feedback dict carries
        # `feedback_id`, set at submit time).
        last_feedback = dict(session.feedback) if session.feedback else None
        if last_feedback and last_feedback.get("feedback_id") is not None:
            from app.modules.feedback.service import lookup_reaction
            from app.modules.sessions.models import FeedbackType

            last_feedback["user_reaction"] = lookup_reaction(
                self.db,
                user_id=user_id,
                feedback_id=int(last_feedback["feedback_id"]),
                feedback_type=FeedbackType.ACTIVITY_FEEDBACK.value,
            )

        return {
            "session_id": session.session_id,
            "daily_session_id": session.daily_session_id,
            "topic": session.topic,
            "skill_name": session.skill_name,
            "task_type": session.task_type,
            "phase": session.phase,
            "messages": list(session.messages or []),
            "task_queue": list(session.task_queue or []),
            "current_task": current_task,
            "current_sequence": checkpoint["current_sequence"],
            "last_evaluation": session.evaluation,
            "last_feedback": last_feedback,
            "completed_sequences": checkpoint["completed_sequences"],
            "completed_activities": self._completed_activity_summaries(session),
            "teaching_completed": checkpoint["teaching_completed"],
            "last_resumable_phase": checkpoint["last_resumable_phase"],
            "daily_completed": daily_completed,
            "blueprint": blueprint.payload,
        }

    async def _auto_complete_daily_if_ready(
        self, session: LearningSession
    ) -> DailySession | None:
        daily = self.db.get(DailySession, session.daily_session_id)
        if daily is None or daily.status is not SessionStatus.IN_PROGRESS:
            return daily

        if daily.session_id in _completing_daily_uuids:
            return daily

        if ScorecardRepository(self.db).get_for_session(daily.id) is not None:
            self.db.refresh(daily)
            return daily

        attempts = self.attempts_repo.list_for_session(daily.id)
        if not attempts or any(
            attempt.status is not AttemptStatus.EVALUATED for attempt in attempts
        ):
            return daily

        # Pass-mark gate: a failed-but-EVALUATED attempt must not auto-complete
        # the day (which would bypass the gate). Leave it IN_PROGRESS so resume
        # re-presents the retry prompt instead of marking the day done.
        gate_required, gate_threshold = self._gate_settings(session.user_id)
        if gate_required and self._has_unpassed_gated_attempt(daily, gate_threshold):
            return daily

        # Take the same completion lock the WS path uses so a concurrent
        # complete_session can't double-award points or skip the scorecard.
        _completing_daily_uuids.add(daily.session_id)
        try:
            await _make_v2_session_service(self.db).complete_session(
                session_id=daily.session_id,
                user_id=session.user_id,
            )
        except (SessionNotFound, SessionAbandoned, SessionAlreadyCompleted):
            pass
        except Exception:
            log.warning(
                "auto_complete_failed",
                daily_session_id=daily.session_id,
                note="leaving open",
                exc_info=True,
            )
        finally:
            _completing_daily_uuids.discard(daily.session_id)
        return self.db.get(DailySession, session.daily_session_id)

    def _stream_completed_daily_message(self) -> AsyncIterator[WSOutgoingMessage]:
        return self._stream_chat_text(
            _DAILY_COMPLETE_MESSAGE,
            actions=["Go to dashboard"],
        )

    def _session_blueprint_message(
        self,
        session: LearningSession,
        state: LearningSessionState | None = None,
    ) -> WSOutgoingMessage:
        daily = self.db.get(DailySession, session.daily_session_id)
        final_review = self._final_review_widgets(daily) if daily is not None else None
        task_queue = (
            list(state.get("task_queue") or [])
            if isinstance(state, dict)
            else list(session.task_queue or [])
        )
        blueprint = runtime_blueprint_from_session(
            session=session,
            task_queue=task_queue,
            final_review=final_review,
        )
        session_meta = {
            "daily_session_id": session.daily_session_id,
            "daily_session_uuid": daily.session_id if daily is not None else None,
            "current_phase": session.phase,
            "current_task_index": int(session.current_task_index or 0),
            "total_tasks": len(task_queue),
            **self._session_display_meta(daily),
        }
        return self._event_orchestrator().session_blueprint_event(
            blueprint=blueprint,
            session_meta=session_meta,
        )

    def _session_display_meta(self, daily: DailySession | None) -> dict[str, Any]:
        """Return small labels the chat header can show to learners."""
        if daily is None:
            return {}

        meta: dict[str, Any] = {
            "course_length": daily.course_length,
        }
        day_id = getattr(daily, "day_id", None)
        if not isinstance(day_id, str) or not day_id:
            return meta

        try:
            week_number, day_number = _parse_day_id(day_id)
            meta["week_number"] = week_number
            meta["day_number"] = day_number
        except ValueError:
            pass

        try:
            file_day = file_get_day_by_id(day_id)
        except DayNotFound:
            file_day = None

        if file_day is not None:
            meta.update(
                {
                    "theme_type": file_day.theme_type,
                    "cefr_level": file_day.cefr_level,
                    "day_number": file_day.day_number,
                    "week_number": file_day.week_number,
                }
            )
            return meta

        day = self.curriculum_day_repo.get_by_day_id(day_id)
        week = day.week if day is not None else None
        if day is not None:
            meta.setdefault("day_number", day.day_number)
        if week is not None:
            theme = getattr(week.theme_type, "value", week.theme_type)
            meta.update(
                {
                    "theme_type": theme,
                    "cefr_level": week.cefr_level,
                    "week_number": week.week_number,
                }
            )
        return meta

    async def process_message_stream(
        self, session_id: str, message: WSIncomingMessage
    ) -> AsyncIterator[WSOutgoingMessage]:
        session = self._load_session(session_id)
        # WS turns run outside HTTP middleware: stamp one trace_id per message so
        # every log/LLM call this turn triggers shares a correlation id.
        trace_id = uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(trace_id=trace_id)
        token = set_eval_context(trace_id=trace_id, user_id=session.user_id)
        try:
            state = self._state_from_row(session)
            self._enrich_state_with_profile(state, session.user_id)

            if message.type == "user_message":
                async for msg in self._handle_user_message_stream(
                    session, state, message
                ):
                    yield msg
                return
            if message.type == "task_submission":
                async for msg in self._handle_task_submission_stream(
                    session, state, message
                ):
                    yield msg
                return
            if message.type == "follow_up_action":
                async for msg in self._handle_follow_up_stream(session, state, message):
                    yield msg
                return
            yield WSOutgoingMessage(
                type="error",
                content=f"Unknown message type: {message.type!r}",
            )
        finally:
            reset_eval_context(token)
            structlog.contextvars.unbind_contextvars("trace_id")

    # ------------------------------------------------------------------
    # Per-message handlers
    # ------------------------------------------------------------------

    async def _handle_user_message_stream(
        self,
        session: LearningSession,
        state: LearningSessionState,
        message: WSIncomingMessage,
    ) -> AsyncIterator[WSOutgoingMessage]:
        text = message.content or ""
        messages = list(state.get("messages", []))
        messages.append({"role": "user", "content": text, "type": "chat"})
        state["messages"] = messages
        session.messages = messages

        if state.get("phase") in ("teaching", None):
            previous_tutor_message = _last_tutor_message(messages[:-1])

            # Input gate: confront gibberish / off-topic replies BEFORE any
            # advance or teaching-turn logic. Wrong-but-relevant answers and
            # genuine confusion fall through to the normal teaching flow.
            #
            # A bare affirmative ("yes"/"ok"/"ready") only means "advance" when
            # the tutor actually invited one — it asked a readiness question, or
            # it has already mentioned the practice task (so the forced-transition
            # escape valve below can still fire). An affirmative to a *content*
            # question ("complete this sentence") is a non-answer, so gate it like
            # an off-topic reply instead of silently skipping the lesson step.
            affirmative = _looks_like_ready_response(text)
            tutor_invited_affirmative = _tutor_asked_readiness(
                previous_tutor_message
            ) or _any_tutor_mentioned_practice_task(messages)
            # Use a STRICT affirmative check here so a genuine short answer
            # ("on", which is a 1-edit typo of "ok") is never mistaken for a
            # bare "yes" non-answer and redirected. The typo-tolerant
            # `affirmative` still drives the gate-skip below so typo readiness
            # replies ("yys") keep working.
            affirmative_non_answer = (
                _looks_like_strict_affirmative(text) and not tutor_invited_affirmative
            )

            # Adaptive teaching loop: classify the reply, then route.
            #   off-topic / gibberish / bare-yes  -> REDIRECT (hold the step)
            #   confused                          -> RETEACH  (hold the step)
            #   genuine answer (relevant)         -> ACCEPT   (advance the step)
            # `stay_on_step` re-teaches the current step instead of advancing;
            # it is set by the deterministic confusion check or a CONFUSED
            # classifier verdict. A genuine answer (right or wrong) advances —
            # the teacher acknowledges it inline before moving on.
            stay_on_step: bool = _is_confusion(text)

            if (not affirmative or affirmative_non_answer) and not stay_on_step:
                gate_reason: str | None = None
                if affirmative_non_answer:
                    # Deterministic — don't burn an LLM call to learn that a bare
                    # "yes" isn't an attempt at the tutor's question.
                    gate_reason = "off_topic"
                elif _is_structural_gibberish(text):
                    gate_reason = "gibberish"
                else:
                    verdict = await classify_reply_relevance(
                        topic=state.get("topic") or "today's topic",
                        current_step=previous_tutor_message,
                        learner_reply=text,
                    )
                    if verdict is not None:
                        if verdict.verdict == "OFF_TOPIC":
                            gate_reason = "off_topic"
                        elif verdict.verdict == "CONFUSED":
                            # The learner is asking for help, not answering —
                            # re-teach this step rather than redirecting.
                            stay_on_step = True

                if gate_reason is not None:
                    redirect = _build_redirect_message(
                        topic=state.get("topic") or "today's topic",
                        previous_tutor_message=previous_tutor_message,
                        redirect_count=_count_trailing_redirects(messages),
                        reason=gate_reason,
                    )
                    new_messages = list(messages)
                    new_messages.append(
                        {
                            "role": "ai",
                            "content": redirect,
                            "type": "chat",
                            "redirect": True,
                        }
                    )
                    self._apply_update(
                        session,
                        {"phase": "teaching", "messages": new_messages},
                    )
                    self.db.commit()
                    async for msg in self._stream_chat_text(redirect):
                        yield msg
                    return

            ready_for_practice = _looks_like_ready_for_practice(
                text,
                previous_tutor_message=previous_tutor_message,
            )
            # Secondary escape valve: when the teacher has finished the
            # authored plan and has already mentioned the practice task,
            # any plausible affirmative reply should advance — even if the
            # exact tutor phrasing wasn't a recognized readiness prompt
            # (e.g. "Let's begin the practice task. Good luck!").
            forced_transition = (
                not ready_for_practice
                and _should_force_transition_to_practice(
                    user_text=text,
                    messages=messages,
                    state=state,
                )
            )
            advance_to_practice = ready_for_practice or forced_transition
            session.understanding_confirmed = (
                session.understanding_confirmed or advance_to_practice
            )
            state["understanding_confirmed"] = session.understanding_confirmed

            if advance_to_practice:
                if forced_transition and not ready_for_practice:
                    log.info(
                        "forcing_transition_to_practice",
                        session_id=session.session_id,
                        teacher_turns=_count_teacher_chat_turns(messages),
                        note="escape valve",
                    )
                # Pull the next pending V2 attempt and deliver it.
                attempt = self._next_pending_attempt(session)
                if attempt is None:
                    # No activities left — gently nudge to complete.
                    async for msg in self._complete_and_announce(session, state):
                        yield msg
                    return
                attempt = await self._prepare_attempt_for_delivery(attempt)
                state["task_content"] = dict(attempt.task_content or {})
                state["task_type"] = self._task_type_for_attempt(attempt)
                state["current_sequence"] = attempt.sequence
                state["current_task_index"] = attempt.sequence - 1
                session.pre_generated_tasks = state["task_content"] or {}
                session.task_type = state["task_type"] or ""
                session.current_task_index = state["current_task_index"]

                update = await task_delivery_node(state)
                self._apply_update(session, update)
                self.db.commit()
                async for msg in self._stream_outgoing_events(
                    update.get("outgoing_events", []),
                    state=state,
                ):
                    yield msg
            else:
                async for msg in self._stream_teaching_turn(
                    session, state, stay_on_step=stay_on_step
                ):
                    yield msg
            return

        if state.get("phase") in ("feedback", "follow_up", "scorecard"):
            async for msg in self._stream_followup_response(session, state, text):
                yield msg
            return

        # practice_task / ended — nudge.
        nudge = (
            "Submit your answers using the task above when you're ready."
            if state.get("phase") == "practice_task"
            else "This session has ended. Start a new one from the dashboard."
        )
        messages.append({"role": "ai", "content": nudge, "type": "chat"})
        session.messages = messages
        self.session_repo.save(session)
        self.db.commit()
        async for msg in self._stream_chat_text(nudge):
            yield msg

    async def _handle_task_submission_stream(
        self,
        session: LearningSession,
        state: LearningSessionState,
        message: WSIncomingMessage,
    ) -> AsyncIterator[WSOutgoingMessage]:
        answers = message.answers or {}
        session.user_submission = answers
        state["user_submission"] = answers

        sequence = state.get("current_sequence")
        if sequence is None:
            attempt = self._next_pending_attempt(session)
            if attempt is None:
                async for msg in self._complete_and_announce(session, state):
                    yield msg
                return
            sequence = attempt.sequence
            state["current_sequence"] = sequence

        v2_service = _make_v2_session_service(self.db)
        daily = self.db.get(DailySession, session.daily_session_id)
        if daily is None:
            yield WSOutgoingMessage(
                type="error",
                content="Linked daily session is missing.",
            )
            return

        # Progressive reveal: drive the phased submit so the SCORE is emitted the
        # instant grading finishes, then FEEDBACK once it is generated. Both
        # phases share one DB transaction + one commit inside the generator (the
        # commit lands in the feedback phase, exactly like the legacy submit).
        phased = v2_service.submit_activity_phased(
            session_id=daily.session_id,
            user_id=session.user_id,
            sequence=int(sequence),
            user_response=answers,
        )

        # Built in phase 1, reused in phase 2 and in the persistence below.
        evaluation_dict: dict[str, Any] = {}
        feedback_dict: dict[str, Any] = {}
        pronunciation_data: dict[str, Any] | None = None
        session_meta: dict[str, Any] = {}
        eval_projected = False
        gate_threshold = 0
        gate_score_pct = 0
        gated_fail = False

        try:
            # ── Phase 1: grading is done → emit the score immediately ──
            eval_phase = await anext(phased)
            assert isinstance(eval_phase, EvaluationPhase)
            attempt = eval_phase.attempt
            evaluation = eval_phase.evaluation

            evaluation_dict = {
                "raw_score": float(evaluation.raw_score),
                "rubric_scores": dict(evaluation.rubric_scores or {}),
                "base_reward": evaluation.base_reward,
                "weighted_points": dict(evaluation.weighted_points or {}),
                "evaluator_notes": evaluation.evaluator_notes,
            }
            # Schema boundary: project the evaluation onto its strict contract so
            # the scorecard carries tier/percentage. `sub_skill_breakdown` is a
            # feedback concern (unused on the scorecard payload + reload
            # hydration), so it is empty here and merged back in phase 2 for
            # `session.evaluation` parity. Bad output is logged and the legacy
            # dict is emitted as-is (unless STRICT_CONTRACTS is set).
            try:
                evaluation_dict.update(
                    project_evaluation(
                        attempt.archetype_id,
                        activity_id=str(attempt.id),
                        evaluation=EvaluationResult(
                            raw_score=float(evaluation.raw_score),
                            rubric_scores=dict(evaluation.rubric_scores or {}),
                            evaluator_notes=evaluation.evaluator_notes,
                        ),
                        sub_skill_breakdown={},
                    )
                )
                eval_projected = True
            except ContractValidationError as exc:
                if settings.strict_contracts:
                    raise
                log.warning(
                    "contract_projection_failed_evaluation",
                    attempt_id=attempt.id,
                    archetype=attempt.archetype_id,
                    detail=exc.detail,
                    note="emitting legacy evaluation payload",
                )

            # Detect a pronunciation (read-aloud) submission — its card bundles
            # feedback, so we buffer the score and emit one combined event below.
            if evaluation.evaluator_notes:
                try:
                    parsed_notes = json.loads(evaluation.evaluator_notes)
                    if (
                        isinstance(parsed_notes, dict)
                        and parsed_notes.get("task_type") == "speak_read_aloud"
                        and isinstance(parsed_notes.get("pronunciation"), dict)
                    ):
                        pronunciation_data = parsed_notes["pronunciation"]
                except (json.JSONDecodeError, TypeError):
                    pass

            session_meta = {
                "current_task_index": int(state.get("current_task_index") or 0),
                "total_tasks": len(session.task_queue or []) or 1,
                "sequence": int(sequence),
                "daily_session_id": session.daily_session_id,
            }
            task_content = dict(attempt.task_content or {})
            activity_contract = dict(task_content.get("activity_contract") or {})
            task_widget = normalize_widget_key(
                str(
                    task_content.get("widget")
                    or task_content.get("ui_widget")
                    or activity_contract.get("task_widget")
                    or session.task_type
                    or ""
                )
            )
            evaluation_widget = str(
                activity_contract.get("evaluation_widget")
                or task_content.get("evaluation_widget")
                or "activity_score"
            )
            feedback_widget_key = str(
                activity_contract.get("feedback_widget")
                or task_content.get("feedback_widget")
                or "feedback_card"
            )

            if pronunciation_data is None:
                # Normal path: emit the generic scorecard now (feedback follows).
                correct_count, total = _deterministic_scorecard_counts(
                    attempt.archetype_id,
                    evaluation.evaluator_notes,
                )
                scorecard_payload = {
                    "overall_score": float(evaluation.raw_score),
                    "skill_name": session.skill_name,
                    "topic": session.topic,
                    "rubric_scores": evaluation_dict["rubric_scores"],
                    "weighted_points": evaluation_dict["weighted_points"],
                    "activity_contract": activity_contract,
                    "task_widget": task_widget,
                    "evaluation_widget": evaluation_widget,
                    "feedback_widget": feedback_widget_key,
                    "_session": session_meta,
                }
                if correct_count is not None and total is not None:
                    scorecard_payload["correct_count"] = correct_count
                    scorecard_payload["total"] = total
                    scorecard_payload["answered_count"] = total
                yield self._event_orchestrator().evaluation_event(
                    widget="scorecard",
                    evaluation_payload=scorecard_payload,
                    evaluation=evaluation_dict,
                    session_meta=session_meta,
                )

            # ── Phase 2: feedback ready (transaction committed) → emit it ──
            fb_phase = await anext(phased)
            assert isinstance(fb_phase, FeedbackPhase)
            feedback = fb_phase.feedback

            feedback_dict = {
                # The ActivityFeedback row id — lets the chat UI attach a 👍/👎
                # reaction (feedback_type=ACTIVITY_FEEDBACK) keyed to this feedback.
                "feedback_id": feedback.id,
                "score": feedback.score,
                "summary": feedback.summary,
                "did_well": list(feedback.did_well or []),
                "mistakes": list(feedback.mistakes or []),
                "next_tip": feedback.next_tip,
                "sub_skill_breakdown": dict(feedback.sub_skill_breakdown or {}),
                # True only for a degraded placeholder card (LLM error/timeout) —
                # the UI shows "Regenerate feedback" solely in this case.
                "feedback_fallback": fb_phase.fallback,
            }
            try:
                feedback_dict.update(
                    project_feedback(
                        attempt.archetype_id,
                        activity_id=str(attempt.id),
                        feedback=FeedbackResult(
                            score=int(feedback.score),
                            summary=feedback.summary or "",
                            did_well=tuple(feedback.did_well or ()),
                            mistakes=tuple(
                                MistakeOut(
                                    issue=str(m.get("issue") or ""),
                                    user_wrote=m.get("user_wrote"),
                                    correction=m.get("correction"),
                                    rule=m.get("rule"),
                                    sub_skills_affected=tuple(
                                        m.get("sub_skills_affected") or ()
                                    ),
                                )
                                for m in (feedback.mistakes or [])
                                if isinstance(m, dict)
                            ),
                            next_tip=feedback.next_tip,
                            sub_skill_breakdown=dict(
                                feedback.sub_skill_breakdown or {}
                            ),
                        ),
                    )
                )
                # Keep persisted `session.evaluation` byte-identical to the legacy
                # path: re-attach the (real) feedback breakdown to the projected
                # evaluation dict that we score-emitted with an empty one.
                if eval_projected:
                    evaluation_dict["sub_skill_breakdown"] = dict(
                        feedback.sub_skill_breakdown or {}
                    )
            except ContractValidationError as exc:
                if settings.strict_contracts:
                    raise
                log.warning(
                    "contract_projection_failed_feedback",
                    attempt_id=attempt.id,
                    archetype=attempt.archetype_id,
                    detail=exc.detail,
                    note="emitting legacy feedback payload",
                )

            # Pass-mark gating: decide (once) whether this attempt clears the
            # learner's threshold. The V2 feedback phase already committed +
            # refreshed the attempt, so `attempt.evaluation` is populated here.
            # When gating is on we stamp a `gate` block onto the feedback so the
            # card can render a "Not passed" banner, and a `gated_fail`
            # short-circuits advancement/completion further down.
            gate_required, gate_threshold = self._gate_settings(session.user_id)
            gate_score_pct = round(float(evaluation.raw_score) * 10)
            gated_fail = gate_required and not self._attempt_passes_gate(
                attempt, gate_threshold
            )
            if gate_required:
                feedback_dict["gate"] = {
                    "passed": not gated_fail,
                    "score_pct": gate_score_pct,
                    "threshold_pct": gate_threshold,
                }

            if pronunciation_data is not None:
                # ── Read-aloud: emit the combined pronunciation_result widget ──
                reference_text = (
                    task_content.get("text_to_read_aloud")
                    or task_content.get("passage")
                    or ""
                )
                pronunciation_payload = {
                    "pronunciation": pronunciation_data,
                    "raw_score": float(evaluation.raw_score),
                    "reference_text": reference_text,
                    "feedback": feedback_dict,
                    "activity_contract": activity_contract,
                    "task_widget": task_widget,
                    "evaluation_widget": evaluation_widget,
                    "feedback_widget": feedback_widget_key,
                    "_session": session_meta,
                }
                yield self._event_orchestrator().evaluation_event(
                    widget="pronunciation_result",
                    evaluation_payload=pronunciation_payload,
                    evaluation={
                        **evaluation_dict,
                        "pronunciation": pronunciation_data,
                        "reference_text": reference_text,
                    },
                    session_meta=session_meta,
                )
            else:
                feedback_payload = {
                    **feedback_dict,
                    "score": float(evaluation.raw_score),
                    "widget": task_widget,
                    "activity_contract": activity_contract,
                    "task_widget": task_widget,
                    "evaluation_widget": evaluation_widget,
                    "feedback_widget": feedback_widget_key,
                    "_session": session_meta,
                }
                yield self._event_orchestrator().feedback_event(
                    widget="feedback_card",
                    feedback_payload=feedback_payload,
                    feedback=feedback_dict,
                    session_meta=session_meta,
                )
        except AttemptAlreadySubmitted:
            yield WSOutgoingMessage(
                type="error",
                content="This activity was already submitted.",
            )
            return
        except (AttemptNotFound, SessionNotFound) as exc:
            yield WSOutgoingMessage(type="error", content=str(exc))
            return
        except Exception:
            # Any other failure (DB, LLM, unexpected RAG/contract error) must not
            # kill the WS handler. Roll back so a feedback-phase failure (after
            # the score was already emitted) leaves nothing committed and the
            # attempt stays re-deliverable, then surface a recoverable error.
            self.db.rollback()
            log.warning(
                "submit_activity_failed",
                session_id=session.session_id,
                sequence=sequence,
                exc_info=True,
            )
            yield WSOutgoingMessage(
                type="error",
                content="Something went wrong while submitting your answer. Please try again.",
            )
            return
        finally:
            # Promptly finalise the generator (idempotent if already exhausted).
            await phased.aclose()

        session.evaluation = evaluation_dict
        session.feedback = feedback_dict
        session.phase = "feedback"
        messages = list(session.messages or [])
        messages.append(
            {
                "role": "ai",
                "content": "[pronunciation result delivered]"
                if pronunciation_data
                else "[scorecard delivered]",
                "type": "ui_event",
            }
        )
        if pronunciation_data is None:
            messages.append(
                {
                    "role": "ai",
                    "content": "[feedback card delivered]",
                    "type": "ui_event",
                }
            )
        session.messages = messages
        # Keep the cached task_queue statuses in step with the V2 attempt we
        # just evaluated.
        self._sync_task_queue_from_attempts(session)
        self.session_repo.save(session)
        self.db.commit()

        state["evaluation"] = evaluation_dict
        state["feedback"] = feedback_dict
        state["phase"] = "feedback"
        state["messages"] = messages

        if gated_fail:
            # Pass-mark gate: the learner scored below their threshold. Do not
            # advance and do not complete the day — offer a retry of the same
            # activity (or an exit to the dashboard, which leaves the day open
            # to resume later).
            summary_text = (
                f"You scored {gate_score_pct}% — you need {gate_threshold}% "
                "to move on. Want to try again?"
            )
            actions = ["Retry activity", "Go to dashboard"]
            messages.append({"role": "ai", "content": summary_text, "type": "chat"})
            session.messages = messages
            state["messages"] = messages
            self.session_repo.save(session)
            self.db.commit()
            async for msg in self._stream_chat_text(summary_text, actions=actions):
                yield msg
            return

        if self._next_pending_attempt(session) is None:
            # Last activity — skip the per-activity summary chat (scorecard +
            # feedback widgets are enough) and wrap up with the day scorecard.
            async for msg in self._complete_and_announce(session, state):
                yield msg
            return

        summary_text = _ACTIVITY_COMPLETE_MESSAGE
        actions = self._next_actions_for_session(session)
        messages.append({"role": "ai", "content": summary_text, "type": "chat"})
        session.messages = messages
        state["messages"] = messages
        self.session_repo.save(session)
        self.db.commit()
        async for msg in self._stream_chat_text(summary_text, actions=actions):
            yield msg

    async def _handle_follow_up_stream(
        self,
        session: LearningSession,
        state: LearningSessionState,
        message: WSIncomingMessage,
    ) -> AsyncIterator[WSOutgoingMessage]:
        action_text = message.action or message.content or ""
        messages = list(state.get("messages", []))
        messages.append({"role": "user", "content": action_text, "type": "chat"})
        state["messages"] = messages
        session.messages = messages

        async for msg in self._stream_followup_response(session, state, action_text):
            yield msg

    async def _stream_followup_response(
        self,
        session: LearningSession,
        state: LearningSessionState,
        raw_action: str,
    ) -> AsyncIterator[WSOutgoingMessage]:
        messages = list(state.get("messages", []))
        action = raw_action.strip().lower()

        end_signals = (
            "go to dashboard",
            "end session",
            "end",
            "stop",
            "bye",
            "goodbye",
        )
        another_signals = (
            "next activity",
            "try another task",
            "another task",
            "next task",
            "more",
        )
        question_signals = ("ask a question", "question", "doubt", "clarif")

        if any(sig in action for sig in end_signals):
            async for msg in self._complete_and_announce(session, state):
                yield msg
            return

        if action == REGENERATE_TASK_ACTION.lower() or "regenerate task" in action:
            # The learner tapped "retry" on a failed task-generation error. Force
            # a brand-new generation through the task agent, ignoring the broken
            # content cached on the pending attempt, then re-deliver. Not
            # idempotent on `practice_task` (the prior failed delivery left the
            # phase there) — the whole point is to re-run generation.
            attempt = self._next_pending_attempt(session)
            if attempt is None:
                async for msg in self._complete_and_announce(session, state):
                    yield msg
                return
            session.phase = "practice_task"
            state["phase"] = "practice_task"
            self.session_repo.save(session)
            self.db.commit()
            v2_service = _make_v2_session_service(self.db)
            # Force regeneration first (bypasses cache), then run the normal
            # delivery prep so TTS/contract handling stays in one place. May raise
            # ContractValidationError again → router re-emits the retryable error.
            await v2_service.force_regenerate_attempt(attempt)
            attempt = await self._prepare_attempt_for_delivery(attempt)
            state["task_content"] = dict(attempt.task_content or {})
            state["task_type"] = self._task_type_for_attempt(attempt)
            state["current_sequence"] = attempt.sequence
            state["current_task_index"] = attempt.sequence - 1
            state["phase"] = "practice_task"
            session.pre_generated_tasks = state["task_content"] or {}
            session.task_type = state["task_type"] or ""
            session.current_task_index = state["current_task_index"]
            session.user_submission = None
            session.evaluation = None
            session.feedback = None
            session.phase = "practice_task"

            update = await task_delivery_node(state)
            self._apply_update(session, update)
            self.db.commit()
            async for msg in self._stream_outgoing_events(
                update.get("outgoing_events", []),
                state=state,
            ):
                yield msg
            return

        if any(sig in action for sig in another_signals):
            # Idempotent: learner already has the pending task on screen.
            if session.phase == "practice_task":
                return
            attempt = self._next_pending_attempt(session)
            if attempt is None:
                async for msg in self._complete_and_announce(session, state):
                    yield msg
                return
            current_seq = state.get("current_sequence")
            if current_seq is not None and int(current_seq) == int(attempt.sequence):
                return
            # Claim the transition before prepare/delivery so a double-click
            # while still in feedback cannot deliver the same task twice.
            session.phase = "practice_task"
            state["phase"] = "practice_task"
            self.session_repo.save(session)
            self.db.commit()
            attempt = await self._prepare_attempt_for_delivery(attempt)
            state["task_content"] = dict(attempt.task_content or {})
            state["task_type"] = self._task_type_for_attempt(attempt)
            state["current_sequence"] = attempt.sequence
            state["current_task_index"] = attempt.sequence - 1
            state["phase"] = "practice_task"
            session.pre_generated_tasks = state["task_content"] or {}
            session.task_type = state["task_type"] or ""
            session.current_task_index = state["current_task_index"]
            session.user_submission = None
            session.evaluation = None
            session.feedback = None
            session.phase = "practice_task"

            update = await task_delivery_node(state)
            self._apply_update(session, update)
            self.db.commit()
            async for msg in self._stream_outgoing_events(
                update.get("outgoing_events", []),
                state=state,
            ):
                yield msg
            return

        if action in question_signals or action == "ask a question":
            prompt_msg = "Sure — what would you like to know?"
            messages.append({"role": "ai", "content": prompt_msg, "type": "chat"})
            self._apply_update(
                session,
                {"phase": "follow_up", "messages": messages},
            )
            self.db.commit()
            async for msg in self._stream_chat_text(prompt_msg):
                yield msg
            return

        async for msg in self._stream_followup_answer(session, state, raw_action):
            yield msg

    async def _await_scorecard_while_completing(
        self,
        daily: DailySession,
        *,
        max_wait_s: float | None = None,
        interval_s: float = 0.1,
    ) -> SessionScorecard | None:
        """Wait for an in-flight ``complete_session`` to commit.

        The wait window covers the inline mentor-note budget plus a buffer so an
        in-flight completion's scorecard (and the RAG widget that follows it) is
        observed rather than skipped.
        """
        if max_wait_s is None:
            max_wait_s = settings.RAG_MENTOR_NOTE_TIMEOUT_S + 7.0
        elapsed = 0.0
        while elapsed < max_wait_s:
            self.db.expire(daily)
            self.db.refresh(daily)
            scorecard = ScorecardRepository(self.db).get_for_session(daily.id)
            if scorecard is not None:
                return scorecard
            if daily.session_id not in _completing_daily_uuids:
                return ScorecardRepository(self.db).get_for_session(daily.id)
            await asyncio.sleep(interval_s)
            elapsed += interval_s
        return ScorecardRepository(self.db).get_for_session(daily.id)

    async def _complete_and_announce(
        self,
        session: LearningSession,
        state: LearningSessionState,
    ) -> AsyncIterator[WSOutgoingMessage]:
        """End the chat and complete the V2 DailySession if not yet completed."""
        daily = self.db.get(DailySession, session.daily_session_id)
        scorecard = None
        # Pass-mark gate: if any EVALUATED attempt is still below threshold, the
        # day is not "done" — leaving (Go to dashboard) keeps it IN_PROGRESS so
        # the learner can resume and retry, rather than completing on a fail.
        gate_required, gate_threshold = self._gate_settings(session.user_id)
        gate_block = (
            daily is not None
            and daily.status is SessionStatus.IN_PROGRESS
            and gate_required
            and self._has_unpassed_gated_attempt(daily, gate_threshold)
        )
        if (
            daily is not None
            and daily.status is SessionStatus.IN_PROGRESS
            and not gate_block
        ):
            # Only complete when all activities have been attempted (no pending remain)
            # AND at least one has been evaluated. Calling complete_session while
            # activities are still PENDING would produce a partial scorecard.
            attempts = self.attempts_repo.list_for_session(daily.id)
            evaluated = [a for a in attempts if a.status is AttemptStatus.EVALUATED]
            has_pending = self._next_pending_attempt(session) is not None
            if evaluated and not has_pending:
                existing_scorecard = ScorecardRepository(self.db).get_for_session(
                    daily.id
                )
                if existing_scorecard is not None:
                    scorecard = existing_scorecard
                    self.db.refresh(daily)
                elif daily.session_id in _completing_daily_uuids:
                    scorecard = await self._await_scorecard_while_completing(daily)
                elif daily.session_id not in _completing_daily_uuids:
                    _completing_daily_uuids.add(daily.session_id)
                    try:
                        v2_service = _make_v2_session_service(self.db)
                        scorecard, _report = await v2_service.complete_session(
                            session_id=daily.session_id,
                            user_id=session.user_id,
                        )
                        self.db.refresh(daily)
                    except (SessionNotFound, SessionAbandoned, SessionAlreadyCompleted):
                        pass
                    except Exception:
                        # Any other failure (DB/LLM/RAG) must not kill the WS
                        # handler — the farewell still streams below so the chat
                        # degrades gracefully instead of hanging.
                        log.warning(
                            "complete_session_failed",
                            daily_session_id=daily.session_id,
                            exc_info=True,
                        )
                    finally:
                        _completing_daily_uuids.discard(daily.session_id)
        elif daily is not None and daily.status is SessionStatus.COMPLETED:
            try:
                scorecard = _make_v2_session_service(self.db).get_scorecard(
                    session_id=daily.session_id,
                    user_id=session.user_id,
                )
            except (SessionNotFound, SessionAbandoned):
                scorecard = None

        if daily is not None and scorecard is not None:
            session_meta = {
                "daily_session_id": session.daily_session_id,
                "daily_session_uuid": daily.session_id,
                "total_tasks": len(session.task_queue or []),
            }
            final_widgets = self._final_review_widgets(daily)
            scorecard_payload = self._final_scorecard_payload(
                session=session,
                daily=daily,
                scorecard=scorecard,
            )
            yield self._event_orchestrator().final_scorecard_event(
                widget=final_widgets["scorecard_widget"],
                scorecard_payload=scorecard_payload,
                session_meta=session_meta,
            )

            # Coach's Note: stream the scorecard instantly, then resolve the note
            # in-band over the still-open WS. If it was already persisted (re-open
            # / earlier generation), use it; otherwise generate it now under a
            # ceiling. A "pending" placeholder is shown while we wait, then the
            # terminal event carries the real note or an explicit unavailability.
            mentor_note = scorecard_payload.get("mentor_note")
            if not mentor_note:
                rag_widget = final_widgets["rag_feedback_widget"]
                yield self._event_orchestrator().rag_feedback_event(
                    widget=rag_widget,
                    feedback_payload={
                        "mentor_note": None,
                        "available": False,
                        "pending": True,
                        "source": "feedback_memory",
                        "scorecard_id": scorecard.id,
                        "_session": session_meta,
                    },
                    session_meta=session_meta,
                )
                mentor_note = await self._resolve_mentor_note(
                    daily_uuid=daily.session_id,
                    user_id=session.user_id,
                )
            yield self._event_orchestrator().rag_feedback_event(
                widget=final_widgets["rag_feedback_widget"],
                feedback_payload={
                    "mentor_note": mentor_note,
                    "available": bool(mentor_note),
                    "pending": False,
                    "source": "feedback_memory",
                    "scorecard_id": scorecard.id,
                    "_session": session_meta,
                },
                session_meta=session_meta,
            )
            yield self._event_orchestrator().completed_event(
                payload={
                    "status": "completed",
                    "daily_session_id": session.daily_session_id,
                    "daily_session_uuid": daily.session_id,
                    "_session": session_meta,
                },
                session_meta=session_meta,
            )

        farewell = (
            _DAILY_GATE_INCOMPLETE_MESSAGE if gate_block else _DAILY_COMPLETE_MESSAGE
        )
        messages = list(session.messages or [])
        messages.append({"role": "ai", "content": farewell, "type": "chat"})
        session.messages = messages
        session.phase = "ended"
        self.session_repo.save(session)
        self.db.commit()

        async for msg in self._stream_chat_text(
            farewell,
            actions=["Go to dashboard"],
        ):
            yield msg

    async def _resolve_mentor_note(
        self,
        *,
        daily_uuid: str,
        user_id: int,
    ) -> str | None:
        """Generate the Coach's Note in-band, under a ceiling. Never raises.

        Runs on a dedicated DB session (off the request session) and is
        ``asyncio.shield``-ed so a timeout shows the user a fallback while the
        worker keeps running and persists the note for later scorecard/dashboard
        reads.
        """
        task: asyncio.Task[str | None] = asyncio.ensure_future(
            generate_mentor_note_async(session_id=daily_uuid, user_id=user_id)
        )
        _pending_note_tasks.add(task)
        task.add_done_callback(_pending_note_tasks.discard)
        try:
            return await asyncio.wait_for(
                asyncio.shield(task),
                timeout=settings.RAG_MENTOR_NOTE_TIMEOUT_S,
            )
        except Exception:
            log.warning(
                "coach_note_not_ready_in_band",
                session_id=daily_uuid,
                note="background worker will persist it",
            )
            return None

    def _final_review_widgets(self, daily: DailySession) -> dict[str, str]:
        try:
            file_day = file_get_day_by_id(daily.day_id)
            final_review = dict(file_day.final_review or {})
        except (DayNotFound, TypeError):
            final_review = {}
        return {
            "scorecard_widget": str(
                final_review.get("scorecard_widget") or "final_scorecard"
            ),
            "rag_feedback_widget": str(
                final_review.get("rag_feedback_widget") or "rag_feedback"
            ),
        }

    def _final_scorecard_payload(
        self,
        *,
        session: LearningSession,
        daily: DailySession,
        scorecard: Any,
    ) -> dict[str, Any]:
        return {
            "session_id": daily.session_id,
            "chat_session_id": session.session_id,
            "daily_session_id": session.daily_session_id,
            "points_earned": dict(scorecard.points_earned or {}),
            "subskill_totals_after": dict(scorecard.subskill_totals_after or {}),
            "dashboard_after": dict(scorecard.dashboard_after or {}),
            "skill_labels": SkillRepository(self.db).display_label_map(),
            "completed_at": scorecard.completed_at,
            "points_applied": bool(scorecard.points_applied),
            "activities": list(scorecard.activities or []),
            "mentor_note": scorecard.mentor_note,
        }

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _profile_context(self, user_id: int) -> dict[str, Any]:
        user = self.db.get(User, user_id)
        learner_name = user.name.split()[0] if user and user.name else ""
        profile = self.profile_repo.get_by_user_id(user_id)
        if profile is None:
            return {
                "learner_name": learner_name,
                "interests": "",
                "primary_goals": "",
                "personalisation_context": "",
                "self_assessed_level": "beginner",
                "native_language": "",
                "structured_personalisation": None,
            }
        return {
            "learner_name": learner_name,
            "interests": profile.interests.strip() if profile.interests else "",
            "primary_goals": (
                profile.primary_goals.strip() if profile.primary_goals else ""
            ),
            "personalisation_context": (
                profile.personalisation_context.strip()
                if profile.personalisation_context
                else ""
            ),
            "self_assessed_level": (
                profile.self_assessed_level.value
                if profile.self_assessed_level
                else "beginner"
            ),
            "native_language": (
                profile.native_language.strip() if profile.native_language else ""
            ),
            "structured_personalisation": profile.structured_personalisation,
        }

    def _enrich_state_with_profile(
        self,
        state: LearningSessionState,
        user_id: int,
    ) -> None:
        state["learner_profile"] = self._profile_context(user_id)

    def _event_orchestrator(self) -> SessionEventOrchestrator:
        # Some unit tests construct the service with ``__new__`` and then
        # attach only the repositories they need. Lazily creating this bridge
        # keeps those focused tests small.
        orchestrator = getattr(self, "event_orchestrator", None)
        if orchestrator is None:
            orchestrator = SessionEventOrchestrator()
            self.event_orchestrator = orchestrator
        return orchestrator

    def _load_session(self, session_id: str) -> LearningSession:
        session = self.session_repo.get_by_session_id(session_id)
        if session is None:
            raise LookupError(f"No learning_session with id={session_id!r}")
        return session

    def _state_from_row(self, session: LearningSession) -> LearningSessionState:
        daily = self.db.get(DailySession, session.daily_session_id)
        return {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "daily_session_id": session.daily_session_id,
            "daily_session_uuid": daily.session_id if daily is not None else None,
            "task_queue": list(session.task_queue or []),
            "current_task_index": session.current_task_index,
            "phase": cast(PhaseType, session.phase),
            "messages": list(session.messages or []),
            "topic": session.topic,
            "skill_name": session.skill_name,
            "activity_type": session.activity_type,
            "user_level": session.user_level,
            "task_content": session.pre_generated_tasks,
            "task_type": session.task_type,
            "user_submission": session.user_submission,
            "evaluation": session.evaluation,
            "feedback": session.feedback,
            "understanding_confirmed": session.understanding_confirmed,
            "current_activity_order": int(
                getattr(session, "current_activity_order", None) or 1
            ),
            "outgoing_events": [],
            "daily_plan": (
                {"teacher_instructions": session.teacher_instructions}
                if session.teacher_instructions
                else None
            ),
        }

    def _apply_update(
        self,
        session: LearningSession,
        update: dict[str, Any],
    ) -> None:
        if "phase" in update:
            session.phase = update["phase"]
        if "messages" in update:
            session.messages = update["messages"]
        if "evaluation" in update:
            session.evaluation = update["evaluation"]
        if "feedback" in update:
            session.feedback = update["feedback"]
        if "task_content" in update:
            session.pre_generated_tasks = update["task_content"] or {}
        if "task_queue" in update:
            session.task_queue = update["task_queue"] or []
        if "task_type" in update:
            session.task_type = str(update["task_type"] or session.task_type)
        if "current_task_index" in update:
            session.current_task_index = int(update["current_task_index"] or 0)
        if "user_submission" in update:
            session.user_submission = update["user_submission"]
        if "understanding_confirmed" in update:
            session.understanding_confirmed = bool(update["understanding_confirmed"])
        if "current_activity_order" in update:
            value = update["current_activity_order"]
            if value is not None:
                session.current_activity_order = int(value)
        self.session_repo.save(session)

    def _next_pending_attempt(
        self,
        session: LearningSession,
    ) -> ActivityAttempt | None:
        return self.attempts_repo.first_pending(session.daily_session_id)

    async def _prepare_attempt_for_delivery(
        self,
        attempt: ActivityAttempt,
    ) -> ActivityAttempt:
        """Self-heal `attempt.task_content` before relaying it to the UI.

        Listening attempts persisted by an older code path can lack
        `audio_script`, `items` and `inner_widget`, which would render as
        "Audio could not be prepared for this listening task." in the
        widget. Delegating to V2 SessionService keeps the regeneration
        logic in one place (it reuses the LLMTaskGenerator + TTS pipeline).
        """
        try:
            v2_service = _make_v2_session_service(self.db)
            attempt = await v2_service.prepare_attempt_for_delivery(attempt)
        except Exception:
            log.exception(
                "repair_task_content_failed",
                attempt_id=attempt.id,
                note="delivering as-is",
            )
        self._apply_task_contract(attempt)
        return attempt

    def _apply_task_contract(self, attempt: ActivityAttempt) -> None:
        """Validate + stamp the contract for every archetype.

        Projects the loose ``task_content`` onto its strict task contract, merges
        the validated fields back, and stamps ``activity_contract`` with the rich
        widget keys so the task/evaluation/feedback events all route through the
        contracted widgets. A validation failure is logged and the content is
        delivered unchanged (the legacy renderer still handles it), unless
        ``settings.strict_contracts`` is set, in which case it raises.

        This is the deliberate projection boundary: it runs at *delivery*, called
        right after ``prepare_attempt_for_delivery`` attaches TTS audio. Projecting
        earlier (e.g. in ``SessionService._generate_attempt_content``) would run before
        audio exists, so listening payloads (``DictationPayload``, ``LISTEN_CLOZE``)
        would fail their ``AudioMixin`` requirement. Keep projection here.
        """
        content = dict(attempt.task_content or {})
        try:
            projected = project_task_payload(
                attempt.archetype_id,
                content,
                activity_id=str(attempt.id),
                sequence=int(attempt.sequence),
            )
        except ContractValidationError as exc:
            if settings.strict_contracts:
                raise
            log.warning(
                "contract_projection_failed",
                attempt_id=attempt.id,
                archetype=attempt.archetype_id,
                detail=exc.detail,
                note="delivering legacy content",
            )
            return
        widgets = contract_widgets(attempt.archetype_id)
        # Keep the legacy `widget`/`ui_widget` keys so the live interactive
        # renderer still routes correctly; the rich widget key travels on
        # `task_widget` + `activity_contract` (frontend convergence is WS4/M4).
        merged = {**content, **projected, "activity_contract": widgets}
        if merged != content:
            attempt.task_content = merged
            self.db.commit()

    @staticmethod
    def _task_type_for_attempt(attempt: ActivityAttempt) -> str:
        content = attempt.task_content or {}
        return normalize_widget_key(
            str(content.get("widget") or content.get("ui_widget") or "")
        )

    def _next_actions_for_session(self, session: LearningSession) -> list[str]:
        next_attempt = self._next_pending_attempt(session)
        if next_attempt is None:
            return ["Go to dashboard"]
        return ["Next activity", "Go to dashboard"]

    # ------------------------------------------------------------------
    # Pass-mark gating
    # ------------------------------------------------------------------

    def _gate_settings(self, user_id: int) -> tuple[bool, int]:
        """Return (require_pass_to_advance, pass_threshold_pct) for the user."""
        pref = PreferenceService(self.db).get(user_id=user_id)
        return bool(pref.require_pass_to_advance), int(pref.pass_threshold_pct)

    def _attempt_passes_gate(
        self, attempt: ActivityAttempt, threshold_pct: int
    ) -> bool:
        """True if the attempt clears the threshold or is an error fallback.

        raw_score is 0–10, the threshold is a 0–100 percentage, so the pass
        line is ``raw_score * 10 >= threshold_pct``. Infra/structural fallback
        scores (detected via evaluator_notes) bypass the gate entirely.
        """
        evaluation = attempt.evaluation
        if evaluation is None:
            return False
        if _is_gate_bypass(evaluation.evaluator_notes):
            return True
        return float(evaluation.raw_score) * 10 >= threshold_pct

    def _has_unpassed_gated_attempt(
        self, daily: DailySession, threshold_pct: int
    ) -> bool:
        """True if any EVALUATED attempt is a genuine sub-threshold fail."""
        for attempt in self.attempts_repo.list_for_session(daily.id):
            if attempt.status is AttemptStatus.EVALUATED and not (
                self._attempt_passes_gate(attempt, threshold_pct)
            ):
                return True
        return False

    # ------------------------------------------------------------------
    # Streaming primitives
    # ------------------------------------------------------------------

    @staticmethod
    def _split_text_chunks(text: str) -> list[str]:
        return re.findall(r"\S+\s*", text) or ([text] if text else [])

    async def _stream_chat_text(
        self,
        text: str,
        *,
        actions: list[str] | None = None,
        role: str = "assistant",
        stream_id: str | None = None,
    ) -> AsyncIterator[WSOutgoingMessage]:
        sid = stream_id or uuid.uuid4().hex
        yield WSOutgoingMessage(
            type="chat_stream_start",
            role=role,
            stream_id=sid,
        )
        for chunk in self._split_text_chunks(text):
            yield WSOutgoingMessage(
                type="chat_stream_delta",
                role=role,
                stream_id=sid,
                content=chunk,
            )
        yield WSOutgoingMessage(
            type="chat_stream_end",
            role=role,
            stream_id=sid,
            content=text,
            actions=actions,
        )

    async def _stream_outgoing_events(
        self,
        events: list[dict],
        *,
        state: LearningSessionState | None = None,
    ) -> AsyncIterator[WSOutgoingMessage]:
        for event in events:
            if event.get("type") == "chat_message":
                async for msg in self._stream_chat_text(
                    str(event.get("content") or ""),
                    actions=event.get("actions"),
                    role=str(event.get("role") or "assistant"),
                ):
                    yield msg
            elif event.get("type") == "ui_event":
                payload = dict(event.get("payload") or {})
                widget = normalize_widget_key(
                    str(
                        event.get("widget")
                        or payload.get("widget")
                        or payload.get("ui_widget")
                        or (state or {}).get("task_type")
                        or ""
                    )
                )
                yield self._event_orchestrator().task_event(
                    widget=widget,
                    task_payload=payload,
                    session_meta=payload.get("_session"),
                )
            else:
                yield WSOutgoingMessage(**event)

    @staticmethod
    async def _timed_chunks(
        source: AsyncIterator[str],
        *,
        first_chunk_timeout_s: float,
        chunk_timeout_s: float,
        timeout_message: str,
    ) -> AsyncIterator[str]:
        timeout = first_chunk_timeout_s
        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(anext(source), timeout=timeout)
                except StopAsyncIteration:
                    break
                except TimeoutError:
                    log.warning("stream_chunk_timeout", detail=timeout_message)
                    break
                timeout = chunk_timeout_s
                yield chunk
        finally:
            aclose = getattr(source, "aclose", None)
            if aclose is not None:
                await aclose()

    async def _stream_teaching_turn(
        self,
        session: LearningSession,
        state: LearningSessionState,
        *,
        stay_on_step: bool = False,
    ) -> AsyncIterator[WSOutgoingMessage]:
        # `stay_on_step` is True when the learner was confused: re-teach the
        # CURRENT step instead of advancing. The turn is tagged ``stayed=True``
        # so it does not move the script cursor (see `_count_green_path_turns`).
        #
        # Boundary guard (before the broad except below, so strict mode surfaces
        # loudly rather than being swallowed by the fallback handler).
        raw_pre_instructions = (state.get("daily_plan") or {}).get(
            "teacher_instructions"
        )
        pre_instructions, pre_scripted = split_scripted_plan(
            raw_pre_instructions if isinstance(raw_pre_instructions, dict) else None,
        )
        pre_description = (
            pre_instructions.get("lesson_description")
            if isinstance(pre_instructions, dict)
            else None
        )
        _validate_teacher_input(
            topic=state.get("topic") or "today's English topic",
            lesson_description=(
                pre_description if isinstance(pre_description, str) else ""
            ),
            scripted_plan=tuple(str(s) for s in (pre_scripted or ())),
        )

        stream_id = uuid.uuid4().hex
        yield WSOutgoingMessage(
            type="chat_stream_start",
            role="assistant",
            stream_id=stream_id,
        )

        chunks: list[str] = []
        try:
            daily_plan = state.get("daily_plan") or {}
            raw_instructions = (
                daily_plan.get("teacher_instructions") if daily_plan else None
            )
            # Separate the scripted plan from the planner-style dict so
            # the LLM prompt builder doesn't see the reserved key as a
            # normal instruction field. Helper lives in `file_source` so
            # the contract has one home.
            teacher_instructions, scripted_plan = split_scripted_plan(
                raw_instructions if isinstance(raw_instructions, dict) else None,
            )
            lesson_description = None
            if isinstance(teacher_instructions, dict):
                raw_description = teacher_instructions.pop("lesson_description", None)
                if isinstance(raw_description, str) and raw_description.strip():
                    lesson_description = raw_description.strip()
            # Tell the LLM exactly where we are in the authored plan so it
            # cannot accidentally reopen the lesson once early messages
            # roll out of the conversation context window.
            conversation_messages = list(state.get("messages", []))
            # The script cursor is driven by *accepted* answers, not the raw
            # teacher-turn count: only green-path turns advance it. Redirects and
            # re-teaches hold the learner on the current step. `prior_plain` is
            # the number of green-path turns already produced (the opener is the
            # first). On a re-teach (`stay_on_step`) we hold the cursor at the
            # current step instead of advancing.
            prior_plain = _count_green_path_turns(conversation_messages)
            plan_length = len(scripted_plan) if scripted_plan else 0
            if plan_length:
                if stay_on_step:
                    current_step_index = min(max(prior_plain, 1), plan_length)
                else:
                    current_step_index = min(prior_plain + 1, plan_length)
            else:
                current_step_index = None
            stuck_count = _stuck_on_step_count(conversation_messages)
            if prior_plain > 0 or stay_on_step:
                if plan_length:
                    next_step = current_step_index or plan_length
                    if stay_on_step:
                        progress_line = (
                            f"The learner is confused — re-teach step "
                            f"{next_step} of {plan_length} in simpler words with "
                            f"a fresh example, then ask one easier question. Do "
                            f"NOT advance and do NOT ask the readiness question."
                        )
                    else:
                        progress_line = (
                            f"The next turn is step {next_step} of {plan_length}. "
                            f"Advance only because the learner gave a genuine "
                            f"answer: acknowledge it (right or wrong) first, then "
                            f"teach this step. If the learner is confused or "
                            f"off-topic instead, re-teach and stay — never jump "
                            f"to the readiness question while they are stuck."
                        )
                    status_hint = (
                        f"Conversation cursor: you have produced {prior_plain} "
                        f"lesson step(s). Never restart the lesson from step 1. "
                        f"{progress_line}"
                    )
                    if stuck_count >= _REDIRECT_ESCALATION_THRESHOLD:
                        status_hint += (
                            " The learner has been stuck on this step several "
                            "times — give the simplest possible explanation and a "
                            "tiny hint so they are never trapped."
                        )
                else:
                    status_hint = (
                        f"Conversation cursor: you have produced {prior_plain} "
                        f"lesson step(s). Continue from where the conversation "
                        f"left off — never restart the lesson from the beginning."
                    )
                    if stay_on_step:
                        status_hint += (
                            " The learner is confused — re-explain the current "
                            "point in simpler words and ask one easier question; "
                            "do not advance."
                        )
                if isinstance(teacher_instructions, dict):
                    teacher_instructions["authored_plan_status"] = status_hint
                else:
                    teacher_instructions = {"authored_plan_status": status_hint}
            teaching_chunks = stream_teaching_turn(
                topic=state.get("topic") or "today's English topic",
                sub_skill=state.get("skill_name") or "grammar",
                task_type=state.get("task_type") or "fill_in_blanks",
                user_level=int(state.get("user_level", 5)),
                learner_profile=state.get("learner_profile") or {},
                conversation=list(state.get("messages", [])),
                teacher_instructions=teacher_instructions,
                scripted_plan=scripted_plan,
                lesson_description=lesson_description,
                current_step_index=current_step_index,
            )
            async for chunk in self._timed_chunks(
                teaching_chunks,
                first_chunk_timeout_s=_TEACHING_STREAM_FIRST_CHUNK_TIMEOUT_S,
                chunk_timeout_s=_TEACHING_STREAM_CHUNK_TIMEOUT_S,
                timeout_message="teaching turn streaming timed out",
            ):
                if not chunk:
                    continue
                chunks.append(chunk)
                yield WSOutgoingMessage(
                    type="chat_stream_delta",
                    role="assistant",
                    stream_id=stream_id,
                    content=chunk,
                )
        except Exception:
            log.exception("teaching_turn_streaming_failed", note="using fallback")

        content = "".join(chunks).strip()
        if not content:
            topic = state.get("topic") or "this topic"
            fallback = (
                f"Let's start today's lesson on {topic}. We'll learn the key "
                "idea together with a few quick examples. To begin, can you "
                "give me one short sentence about today's topic?"
            )
            for chunk in self._split_text_chunks(fallback):
                yield WSOutgoingMessage(
                    type="chat_stream_delta",
                    role="assistant",
                    stream_id=stream_id,
                    content=chunk,
                )
            content = fallback

        new_messages = list(state.get("messages", []))
        teaching_turn: dict = {"role": "ai", "content": content, "type": "chat"}
        if stay_on_step:
            # Tag re-teaches so the script cursor does not count them as
            # progress (see `_count_green_path_turns` / `_count_trailing_stays`).
            teaching_turn["stayed"] = True
        new_messages.append(teaching_turn)
        self._apply_update(
            session,
            {"phase": "teaching", "messages": new_messages},
        )
        self.db.commit()

        yield WSOutgoingMessage(
            type="chat_stream_end",
            role="assistant",
            stream_id=stream_id,
            content=content,
        )

    async def _stream_followup_answer(
        self,
        session: LearningSession,
        state: LearningSessionState,
        question: str,
    ) -> AsyncIterator[WSOutgoingMessage]:
        stream_id = uuid.uuid4().hex
        yield WSOutgoingMessage(
            type="chat_stream_start",
            role="assistant",
            stream_id=stream_id,
        )

        chunks: list[str] = []
        answer_chunks = stream_answer_question(state, question)
        async for chunk in self._timed_chunks(
            answer_chunks,
            first_chunk_timeout_s=_FOLLOWUP_STREAM_FIRST_CHUNK_TIMEOUT_S,
            chunk_timeout_s=_FOLLOWUP_STREAM_CHUNK_TIMEOUT_S,
            timeout_message="follow-up answer streaming timed out",
        ):
            if chunk:
                chunks.append(chunk)
                yield WSOutgoingMessage(
                    type="chat_stream_delta",
                    role="assistant",
                    stream_id=stream_id,
                    content=chunk,
                )

        content = "".join(chunks).strip()
        if not content:
            content = "Sure — what would you like to know?"
            for chunk in self._split_text_chunks(content):
                yield WSOutgoingMessage(
                    type="chat_stream_delta",
                    role="assistant",
                    stream_id=stream_id,
                    content=chunk,
                )

        messages = list(state.get("messages", []))
        messages.append({"role": "ai", "content": content, "type": "chat"})
        self._apply_update(
            session,
            {"phase": "follow_up", "messages": messages},
        )
        self.db.commit()

        yield WSOutgoingMessage(
            type="chat_stream_end",
            role="assistant",
            stream_id=stream_id,
            content=content,
        )


def _make_v2_session_service(db: Session) -> SessionService:
    """Construct the production-wired V2 SessionService.

    Mirrors `app.modules.sessions.routes._make_session_service` so the
    chat layer talks to the same LLM-wired evaluator/feedback/task
    generator the REST shell uses.
    """
    from app.ai.sessions import build_default_agents

    evaluator, feedback_generator, task_generator = build_default_agents()
    service = SessionService(
        db,
        evaluator=evaluator,
        feedback_generator=feedback_generator,
        task_generator=task_generator,
    )
    try:
        from app.ai.sessions.factory import build_rag_services
        from app.modules.feedback_memory.rag_service import FeedbackRAGService

        embedding_gen, mentor_gen = build_rag_services()
        service._rag_service = FeedbackRAGService(
            db,
            embedding_generator=embedding_gen,
        )
        service._mentor_generator = mentor_gen
    except Exception:
        log.warning(
            "rag_services_unavailable",
            note="mentor notes disabled",
            exc_info=True,
        )
    return service
