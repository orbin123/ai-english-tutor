"""Rotation engine — decides which (skill, activity, difficulty) the user
should practice today.

This module is INTENTIONALLY DB-FREE. It takes plain data in, returns plain
data out. No SQLAlchemy. No commits. The service layer fetches the data,
calls into here, and writes the results.

Why? Pure logic is easy to test. Pedagogy rules will evolve — keeping them
out of DB code means we can change them without DB risk.

Inputs:
  - week_number          : 1..duration_weeks
  - day_in_week          : 1..7
  - skill_name_to_id     : {'grammar': 1, 'vocabulary': 2, ...}
  - history_by_skill_id  : {skill_id: last_activity_type or None}

Output:
  - Plan(skill_id, activity_type, target_difficulty)
"""

from dataclasses import dataclass

from app.modules.curriculum.constants import (
    SKILL_ACTIVITIES,
    WEEK_SCHEDULE,
    difficulty_for_week,
)
from app.modules.tasks.models import TaskType


@dataclass(frozen=True)
class Plan:
    """The rotation engine's recommendation for today."""

    skill_id: int
    skill_name: str          # convenience for logging / future LLM prompts
    activity_type: TaskType
    target_difficulty: int

    def __repr__(self) -> str:
        return (
            f"Plan(skill={self.skill_name}, activity={self.activity_type.value}, "
            f"difficulty={self.target_difficulty})"
        )
    
class RotationEngine:
    """Decides today's plan based on enrollment state and skill history.

    Stateless: same inputs always produce the same output.

    Decision flow:
      1. Pick the skill — fixed by day_in_week (WEEK_SCHEDULE).
      2. Pick the activity — round-robin from SKILL_ACTIVITIES[skill].
         Look at history.last_activity_type and pick the NEXT one in the list.
         If no history yet → start with the first allowed activity.
      3. Pick the difficulty — from the week-number curve.
    """

    def decide(
        self,
        *,
        week_number: int,
        day_in_week: int,
        skill_name_to_id: dict[str, int],
        history_by_skill_id: dict[int, TaskType | None],
    ) -> Plan:
        """Return today's plan.

        Args:
            week_number: 1-based, 1..duration_weeks of the course.
            day_in_week: 1..7. Day 1 is the first day of the week.
            skill_name_to_id: maps skill names ('grammar') to DB ids.
            history_by_skill_id: per-skill last activity. Missing skill = no
                history yet for that skill.

        Raises:
            ValueError: invalid day_in_week, missing skill in name_to_id, or
                an empty allowed-activities list (config error).
        """
        # ---- 1. Pick the skill ----
        if day_in_week not in WEEK_SCHEDULE:
            raise ValueError(
                f"day_in_week must be 1..7, got {day_in_week}"
            )
        skill_name = WEEK_SCHEDULE[day_in_week]

        if skill_name not in skill_name_to_id:
            raise ValueError(
                f"Skill {skill_name!r} not in DB. Did you run seed_skills?"
            )
        skill_id = skill_name_to_id[skill_name]

        # ---- 2. Pick the activity (round-robin) ----
        allowed = SKILL_ACTIVITIES.get(skill_name, [])
        if not allowed:
            raise ValueError(
                f"No activities configured for skill {skill_name!r}"
            )

        last_activity = history_by_skill_id.get(skill_id)
        activity_type = self._next_activity(allowed, last_activity)

        # ---- 3. Pick the difficulty ----
        target_difficulty = difficulty_for_week(week_number)

        return Plan(
            skill_id=skill_id,
            skill_name=skill_name,
            activity_type=activity_type,
            target_difficulty=target_difficulty,
        )

    @staticmethod
    def _next_activity(
        allowed: list[TaskType],
        last: TaskType | None,
    ) -> TaskType:
        """Round-robin: return the activity AFTER `last` in `allowed`.

        - No history (last is None) → first activity
        - last not in allowed (e.g. config changed) → first activity
        - last is the final element → wrap around to first
        """
        if last is None or last not in allowed:
            return allowed[0]
        idx = allowed.index(last)
        next_idx = (idx + 1) % len(allowed)
        return allowed[next_idx]
    
