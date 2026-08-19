"""
Central model registry.

Importing every model here ensures SQLAlchemy's class registry is fully
populated before any mapper is configured. This:
  1. Resolves string-based relationship() references across modules
  2. Lets Alembic discover all tables via Base.metadata
  3. Gives one canonical import line for app startup and tooling

Add every new model to this file as you create it.
"""

from app.modules.auth.models import (  # noqa: F401
    AuthSession,
    EmailOtp,
    OAuthAccount,
    Permission,
    Role,
    RolePermission,
    User,
    UserProfile,
    UserRole,
)
from app.modules.admin.models import (  # noqa: F401
    AdminAuditLog,
    AIEvaluation,
    AIRequestLog,
)
from app.modules.skills.models import Skill  # noqa: F401
from app.modules.curriculum.models import (  # noqa: F401
    Course,
    CurriculumDay,
    CurriculumWeek,
    TaskArchetype,
    UserEnrollment,
)
from app.modules.challenges.models import (  # noqa: F401
    Challenge,
    ChallengeAttempt,
    ChallengeLevel,
)
from app.modules.challenges.a2z_game.models import A2ZUserProgress  # noqa: F401
from app.modules.progress.models import ProgressLog, SkillPoints, SkillPointsLog  # noqa: F401
from app.modules.subscriptions.models import (  # noqa: F401
    Payment,
    PaymentEvent,
    Purchase,
    Subscription,
)
from app.modules.sessions.models import (  # noqa: F401
    ActivityAttempt,
    ActivityEvaluation,
    ActivityFeedback,
    DailySession,
    FeedbackReaction,
    SessionScorecard,
)
from app.modules.streaks.models import DailyActivity, StreakFreezeUsage  # noqa: F401
from app.modules.preferences.models import UserCoursePreference  # noqa: F401
from app.modules.learning_session.models import LearningSession  # noqa: F401
from app.modules.feedback_memory.models import FeedbackMemoryLog  # noqa: F401
from app.modules.reviews.models import AppReview  # noqa: F401
from app.modules.feedback.models import FeedbackPromptLog  # noqa: F401
from app.modules.blog.models import BlogPost  # noqa: F401
from app.modules.quotas.models import UsageQuotaCounter  # noqa: F401
