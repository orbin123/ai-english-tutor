"""Evaluators for the diagnosis mini-tasks.

Each evaluator has ONE responsibility: turn a raw user submission
into normalized scores. They know nothing about the database, the
formula, or each other.

TextEvaluator is still a stub — real LLM integration is a future ticket.
SpeechEvaluator is now REAL — it scores against a Whisper transcript.
"""

import re


# ── 1. Rule-based evaluator (fill-blank) ──────────────────────────────────

FILL_BLANK_ANSWERS_V1: list[str] = [
    "goes",
    "ate",
    "rains",
    "lived",
    "was written",
]


class RuleBasedEvaluator:
    """Compares user fill-blank answers against the canonical answer key."""

    def evaluate_fill_blank(
        self, *, question_set_id: str, user_answers: list[str]
    ) -> int:
        """Return the count of correct answers (0..5)."""
        if question_set_id != "diag_fillblank_v1":
            raise ValueError(f"Unknown question_set_id: {question_set_id}")

        if len(user_answers) != len(FILL_BLANK_ANSWERS_V1):
            raise ValueError(
                f"Expected {len(FILL_BLANK_ANSWERS_V1)} answers, "
                f"got {len(user_answers)}"
            )

        correct = 0
        for given, expected in zip(user_answers, FILL_BLANK_ANSWERS_V1):
            if given.strip().lower() == expected.strip().lower():
                correct += 1
        return correct


# ── 2. Text evaluator (STUB — replaced by LLM later) ──────────────────────

class TextEvaluator:
    """Evaluates the writing response across 3 dimensions.

    STUB: Returns scores based on word count only.
    Real implementation will call an LLM with a structured rubric prompt.
    """

    def evaluate_writing(
        self, *, prompt_id: str, response_text: str
    ) -> dict[str, float]:
        """Return expression_score, vocabulary_score, tone_score."""
        word_count = len(response_text.split())
        length_factor = min(word_count / 60, 1.0)

        return {
            "expression_score": round(0.3 + 0.4 * length_factor, 2),
            "vocabulary_score": round(0.15 + 0.2 * length_factor, 2),
            "tone_score": round(0.15 + 0.2 * length_factor, 2),
        }


# ── 3. Speech evaluator (REAL — Whisper transcript scoring) ───────────────

# The canonical passages, keyed by passage_id.
# Must match what the frontend shows the user.
PASSAGES: dict[str, str] = {
    "diag_passage_v1": (
        "Every morning I wake up early and walk in the park. "
        "The fresh air helps me think clearly. "
        "I greet a few neighbours, finish a short jog, "
        "and return home feeling ready for the day."
    ),
}

# Ideal reading speed range for a clear, measured read (words per minute)
WPM_MIN = 100
WPM_MAX = 160


def _tokenize(text: str) -> list[str]:
    """Lowercase and split into word tokens, stripping punctuation.

    Example: "I'm fine." → ["i'm", "fine"]
    We keep contractions intact because Whisper preserves them.
    """
    return re.findall(r"[a-z']+", text.lower())


def _accuracy_pct(reference_words: list[str], transcript_words: list[str]) -> float:
    """Word-level accuracy: fraction of reference words present in transcript.

    Uses a sliding-window match so small insertions/deletions don't kill
    the entire score. Returns 0.0 – 1.0.

    Algorithm:
      For each reference word, check if it appears in the transcript within
      a window of ±5 positions around the expected position. This tolerates
      skipped words and minor disfluencies without being too generous.
    """
    if not reference_words:
        return 0.0

    n_ref = len(reference_words)
    n_tra = len(transcript_words)
    matched = 0

    for i, ref_word in enumerate(reference_words):
        # Expected position in transcript scaled by length ratio
        expected_pos = int(i * (n_tra / n_ref)) if n_tra else 0
        window_start = max(0, expected_pos - 5)
        window_end = min(n_tra, expected_pos + 6)
        window = transcript_words[window_start:window_end]
        if ref_word in window:
            matched += 1

    return matched / n_ref


class SpeechEvaluator:
    """Scores a read-aloud submission using a Whisper transcript.

    Inputs  : passage_id, transcript (from Whisper), duration_seconds
    Outputs : fluency_score (0.0–1.0), clarity_score (0.0–1.0)

    fluency_score  — based on reading speed (WPM). Penalises too slow or
                     too fast. Ideal range: 100–160 WPM → score 1.0.
    clarity_score  — based on word accuracy vs the reference passage.
                     1.0 means every reference word was said correctly.

    If the passage_id is unknown or the transcript is empty, both scores
    fall back to 0.4 (below average but not zero — avoids punishing
    technical failures too harshly).
    """

    FALLBACK_SCORE = 0.4

    def evaluate_read_aloud(
        self,
        *,
        passage_id: str,
        transcript: str,
        duration_seconds: float,
    ) -> dict[str, float]:
        """Return fluency_score and clarity_score."""

        reference_text = PASSAGES.get(passage_id)
        if not reference_text or not transcript.strip():
            return {
                "fluency_score": self.FALLBACK_SCORE,
                "clarity_score": self.FALLBACK_SCORE,
            }

        reference_words = _tokenize(reference_text)
        transcript_words = _tokenize(transcript)

        # ── Clarity: word-level accuracy ──────────────────────────────────
        accuracy = _accuracy_pct(reference_words, transcript_words)
        clarity_score = round(accuracy, 2)

        # ── Fluency: reading speed (WPM) ──────────────────────────────────
        # Use transcript word count (what was actually said) for WPM.
        # Guard against near-zero duration to avoid division by zero.
        safe_duration = max(duration_seconds, 1.0)
        wpm = (len(transcript_words) / safe_duration) * 60

        if WPM_MIN <= wpm <= WPM_MAX:
            fluency_score = 1.0
        elif wpm < WPM_MIN:
            # Too slow — linear scale from 0.3 (at 0 WPM) to 1.0 (at WPM_MIN)
            fluency_score = round(0.3 + 0.7 * (wpm / WPM_MIN), 2)
        else:
            # Too fast — linear penalty above WPM_MAX, floor at 0.5
            over = wpm - WPM_MAX
            fluency_score = round(max(0.5, 1.0 - (over / WPM_MAX) * 0.5), 2)

        return {
            "fluency_score": min(fluency_score, 1.0),
            "clarity_score": min(clarity_score, 1.0),
        }
