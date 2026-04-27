"""Evaluators for the diagnosis mini-tasks.

Each evaluator has ONE responsibility: turn a raw user submission
into normalized scores. They know nothing about the database, the
formula, or each other.

For MVP, TextEvaluator and SpeechEvaluator are STUBS — they return
plausible hardcoded values. Real LLM/Whisper integration is a future ticket.
"""


# 1. Rule-based evaluator (real, deterministic) 

# Correct answers for diag_fillblank_v1 (matches design doc Section 4)
FILL_BLANK_ANSWERS_V1: list[str] = [
    "goes",
    "ate",
    "rains",
    "lived",
    "was written",
]


class RuleBasedEvaluator:
    """Compares user fill-blank answers against the canonical answer key.
    
    Match logic: case-insensitive, whitespace-trimmed, exact string.
    No fuzzy matching — answers are short and the key is curated.
    """

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
    
# 2. Text evaluator (STUB — replaced by LLM later)

class TextEvaluator:
    """Evaluates the writing response across 3 dimensions.
    
    STUB: Returns hardcoded plausible scores that vary slightly with text length.
    Real implementation will call an LLM with a structured rubric prompt.
    Contract matches design doc Section 5.
    """

    def evaluate_writing(
        self, *, prompt_id: str, response_text: str
    ) -> dict[str, float]:
        """Return dict with expression_score, vocabulary_score, tone_score.
        
        Ranges (clamped):
          expression_score: 0.0 – 1.0
          vocabulary_score: 0.0 – 0.5
          tone_score:       0.0 – 0.5
        """
        # Toy heuristic so we get *some* variation between users in dev:
        # longer writing → slightly higher scores. Capped well below max
        # so we don't fake high scores.
        word_count = len(response_text.split())
        length_factor = min(word_count / 60, 1.0)  # 60 words = "full credit"

        return {
            "expression_score": round(0.3 + 0.4 * length_factor, 2),
            "vocabulary_score": round(0.15 + 0.2 * length_factor, 2),
            "tone_score": round(0.15 + 0.2 * length_factor, 2),
        }
    
# 3. Speech evaluator (STUB — replaced by Whisper later)

class SpeechEvaluator:
    """Evaluates read-aloud audio for fluency and clarity.
    
    STUB: Ignores the audio_url and returns plausible hardcoded scores.
    Real implementation will:
      1. Download audio from audio_url
      2. Transcribe with Whisper
      3. Compute WPM, pause_count, accuracy_pct
      4. Map to fluency_score, clarity_score per design doc Section 6
    """

    def evaluate_read_aloud(
        self, *, passage_id: str, audio_url: str, duration_seconds: float
    ) -> dict[str, float]:
        """Return dict with fluency_score, clarity_score.
        
        Ranges (both): 0.0 – 1.0
        """
        # Toy heuristic: assume the canonical passage is ~50 words.
        # Reasonable read time: 20–30 seconds → high score.
        # Too fast (<15s) or too slow (>40s) → lower score.
        if 20 <= duration_seconds <= 30:
            fluency = 0.85
        elif 15 <= duration_seconds < 20 or 30 < duration_seconds <= 40:
            fluency = 0.65
        else:
            fluency = 0.40

        return {
            "fluency_score": fluency,
            "clarity_score": 0.70,  # Always plausible — real impl computes from accuracy_pct
        }