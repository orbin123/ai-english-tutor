"""
Central model registry.

Importing every model here ensures SQLAlchemy's class registry is fully
populated before any mapper is configured. This:
  1. Resolves string-based relationship() references across modules
  2. Lets Alembic discover all tables via Base.metadata
  3. Gives one canonical import line for app startup and tooling

Add every new model to this file as you create it.
"""

from app.modules.auth.models import User, UserProfile  # noqa: F401
from app.modules.skills.models import Skill, UserSkillScore  # noqa: F401
from app.modules.tasks.models import Task, TaskSkill, UserTask  # noqa: F401
from app.modules.responses.models import (  # noqa: F401
    UserResponse, Evaluation, Feedback,
)
from app.modules.progress.models import ProgressLog  # noqa: F401