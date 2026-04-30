"""Score updater — applies WMA to user skill scores and logs history.

Triggered AFTER feedback is generated. Given an evaluation_id:
  1. Walk back: Evaluation → UserResponse → UserTask → Task → TaskSkill[]
  2. For each targeted skill, compute new score (weighted moving average)
  3. Upsert UserSkillScore (current cached value)
  4. Insert ProgressLog (append-only history)
  5. Commit once

Skills NOT in the task's TaskSkill list are NEVER touched.
"""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.modules.progress.exceptions import (
    EvaluationNotFound,
    TaskHasNoTargetSkills,
)
from app.modules.progress.repository import ProgressLogRepository
from app.modules.responses.repository import EvaluationRepository
from app.modules.skills.models import UserSkillScore
from app.modules.skills.repository import UserSkillScoreRepository
from app.modules.tasks.models import UserTask


# Learning rate — how strongly ONE task can shift a score.
# 0.2 = 20% new task, 80% old score → smooth, noise-resistant drift.
ALPHA = Decimal("0.2")

# Default starting score for a brand-new (user, skill) pair.
# Should rarely be hit — diagnosis seeds these — but we're defensive.
DEFAULT_SCORE = Decimal("3.0")


class ScoreUpdaterService:
    """Applies a single evaluation's outcome to the user's skill scores."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.evaluation_repo = EvaluationRepository(db)
        self.skill_score_repo = UserSkillScoreRepository(db)
        self.progress_log_repo = ProgressLogRepository(db)

    @staticmethod
    def _compute_new_score(
        *,
        old_score: Decimal,
        task_score: Decimal,
        skill_weight: Decimal,
    ) -> Decimal:
        """Weighted moving average for ONE skill.

        Formula:
            effective_alpha = ALPHA * skill_weight
            new = effective_alpha * task_score + (1 - effective_alpha) * old_score

        Result is clamped to [0.0, 10.0] and rounded to 1 decimal place
        to match Numeric(3, 1).
        """
        effective_alpha = ALPHA * skill_weight
        new_score = (
            effective_alpha * task_score
            + (Decimal("1") - effective_alpha) * old_score
        )
        new_score = max(Decimal("0.0"), min(Decimal("10.0"), new_score))
        return new_score.quantize(Decimal("0.1"))

    def apply(self, evaluation_id: int) -> list[UserSkillScore]:
        """Apply one evaluation's outcome to all targeted skills.

        Returns the list of updated UserSkillScore rows.
        Skills NOT targeted by this task are NEVER touched.
        """
        # 1. Load the evaluation
        evaluation = self.evaluation_repo.get_by_id(evaluation_id)
        if evaluation is None:
            raise EvaluationNotFound(
                f"Evaluation {evaluation_id} does not exist"
            )

        # 2. Walk back: Evaluation → UserResponse → UserTask → Task → TaskSkill[]
        response = evaluation.response
        user_task = self.db.get(UserTask, response.user_task_id)
        task = user_task.task
        target_skills = task.task_skills

        if not target_skills:
            raise TaskHasNoTargetSkills(
                f"Task {task.id} has no TaskSkill rows — cannot update scores"
            )

        # 3. Convert evaluation percentage (0–100) → 0–10 scale.
        task_score = Decimal(evaluation.percentage) / Decimal("10")

        # 4. For each targeted skill: WMA → upsert → log.
        updated_rows: list[UserSkillScore] = []

        for ts in target_skills:
            existing = self.skill_score_repo.get_one(
                user_id=user_task.user_id,
                skill_id=ts.skill_id,
            )
            old_score = (
                Decimal(existing.score) if existing is not None else DEFAULT_SCORE
            )

            new_score = self._compute_new_score(
                old_score=old_score,
                task_score=task_score,
                skill_weight=Decimal(ts.weight),
            )

            # 4a. Upsert the cached current score.
            updated = self.skill_score_repo.upsert_score(
                user_id=user_task.user_id,
                skill_id=ts.skill_id,
                score=float(new_score),
                is_estimated=False,
            )
            updated_rows.append(updated)

            # 4b. Append-only history row.
            self.progress_log_repo.create(
                user_id=user_task.user_id,
                skill_id=ts.skill_id,
                score=float(new_score),
                user_task_id=user_task.id,
            )

        # 5. One commit — atomic across all skills.
        self.db.commit()
        for row in updated_rows:
            self.db.refresh(row)

        return updated_rows