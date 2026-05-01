"""Pydantic schemas for the progress module."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SkillScoreSnapshot(BaseModel):
    """One row in GET /progress/scores — current score for one skill.

    Used by the spider chart on the dashboard. Returns all 7 skills
    for the current user.
    """

    model_config = ConfigDict(from_attributes=True)

    skill_id: int
    skill_name: str
    score: float


class ProgressLogPoint(BaseModel):
    """One row in GET /progress/history — a single point on the line chart."""

    model_config = ConfigDict(from_attributes=True)

    score: float
    created_at: datetime