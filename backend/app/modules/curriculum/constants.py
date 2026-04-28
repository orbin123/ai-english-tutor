"""Curriculum constants — the pedagogy contract.

These tables encode WHAT the system teaches and HOW activities rotate.
They are NOT in the database because:
  - They never change at runtime
  - They're the source of truth for both seeding AND runtime decisions
  - Code review is the right gate for pedagogy changes (not a SQL UPDATE)

If you change anything here, also update the rotation engine tests.
"""

from app.modules.tasks.models import TaskType


# Day-of-week → which sub-skill the user practices that day.
# Day 1 = first day of the user's week (NOT calendar Monday).
# Days 6 & 7 are revision of the most-practiced skills.
#
# Pronunciation and fluency are excluded from MVP because they require
# audio infrastructure (Whisper STT, ElevenLabs TTS) that does not exist yet.
# When audio lands, we'll re-balance this schedule.
WEEK_SCHEDULE: dict[int, str] = {
    1: "grammar",
    2: "vocabulary",
    3: "expression",
    4: "comprehension",
    5: "tone",
    6: "grammar",       # revision day
    7: "vocabulary",    # revision day
}


# For each sub-skill, the activity types it can be practiced through.
# Source of truth: the project's Activity Matrix.
# The rotation engine cycles through this list (round-robin) when picking
# today's activity, so the order here defines the rotation order.
SKILL_ACTIVITIES: dict[str, list[TaskType]] = {
    "grammar":       [TaskType.READING, TaskType.WRITING, TaskType.SPEAKING],
    "vocabulary":    [TaskType.READING, TaskType.WRITING, TaskType.SPEAKING],
    "pronunciation": [TaskType.SPEAKING, TaskType.LISTENING],   # MVP: not used
    "fluency":       [TaskType.SPEAKING, TaskType.LISTENING],   # MVP: not used
    "expression":    [TaskType.READING, TaskType.WRITING, TaskType.SPEAKING],
    "comprehension": [TaskType.READING, TaskType.LISTENING],
    "tone":          [TaskType.READING, TaskType.WRITING, TaskType.SPEAKING],
}


# Difficulty curve — week number → target task difficulty (1..10).
# Simple step function. Tune after seeing real user data.
def difficulty_for_week(week_number: int) -> int:
    """Return target difficulty (1..10) for a given course week."""
    if week_number <= 4:
        return 1
    if week_number <= 10:
        return 2
    if week_number <= 16:
        return 3
    if week_number <= 24:
        return 4
    if week_number <= 36:
        return 5
    return 6   # 48-week courses peak here