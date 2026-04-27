"""Diagnosis scoring constants and formulas.

Change values here to tune the scoring policy without touching service logic.
"""

from app.modules.auth.models import ContentExposure, SelfAssessedLevel

LEVEL_BONUS: dict[SelfAssessedLevel, float] = {
    SelfAssessedLevel.BEGINNER: 1.0,
    SelfAssessedLevel.INTERMEDIATE: 1.5,
    SelfAssessedLevel.ADVANCED: 2.0,
}

EXPOSURE_BONUS: dict[ContentExposure, float] = {
    ContentExposure.NONE: 0.00,
    ContentExposure.LOW: 0.25,
    ContentExposure.MEDIUM: 0.50,
    ContentExposure.HIGH: 0.75,
}

FILL_BLANK_PER_CORRECT_GRAMMAR = 0.25
FILL_BLANK_PER_CORRECT_VOCAB = 0.10

HARD_CAP = 4.0

# Formula Function
def compute_skill_scores(
    *,
    level: SelfAssessedLevel,
    exposure: ContentExposure,
    fill_blank_correct_count: int,
    writing_expression: float,
    writing_vocabulary: float,
    writing_tone: float,
    speech_fluency: float,
    speech_clarity: float,
) -> dict[str, float]:
    """Apply the master scoring formula from design doc Section 8.

    All output scores are in [1.0, 4.0]. Returns a dict keyed by skill name
    (matches the master Skill table seeded names).
    """
    base = LEVEL_BONUS[level] + EXPOSURE_BONUS[exposure]

    grammar = base + (fill_blank_correct_count * FILL_BLANK_PER_CORRECT_GRAMMAR)
    vocabulary = (
        base
        + (fill_blank_correct_count * FILL_BLANK_PER_CORRECT_VOCAB)
        + writing_vocabulary
    )
    pronunciation = base + speech_clarity
    fluency = base + speech_fluency
    expression = base + writing_expression
    tone = base + writing_tone
    comprehension = (grammar + vocabulary) / 2

    raw = {
        "grammar": grammar,
        "vocabulary": vocabulary,
        "pronunciation": pronunciation,
        "fluency": fluency,
        "expression": expression,
        "tone": tone,
        "comprehension": comprehension,
    }

    # Apply hard cap, round to 2 decimals for clean DB storage
    return {name: round(min(score, HARD_CAP), 2) for name, score in raw.items()}