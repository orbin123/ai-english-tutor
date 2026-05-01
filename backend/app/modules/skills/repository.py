"""Data access for Skill master table and per-user skill scores."""

from sqlalchemy.orm import Session

from app.modules.skills.models import Skill, UserSkillScore

class SkillRepository:
    """Read-only access to the Skill master table.
    
    Skills are seeded once and rarely change — so no create/update/delete here.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_all(self) -> list[Skill]:
        """Return all 7 skills, ordered by id (insertion order)."""
        return self.db.query(Skill).order_by(Skill.id).all()

    def get_by_name(self, name: str) -> Skill | None:
        """Look up a skill by its canonical name (e.g. 'grammar')."""
        return self.db.query(Skill).filter(Skill.name == name).first()

    def name_to_id_map(self) -> dict[str, int]:
        """Convenience: {'grammar': 1, 'vocabulary': 2, ...}.
        
        Used by services that get skill names from LLM/rules and need ids.
        """
        return {s.name: s.id for s in self.get_all()}

class UserSkillScoreRepository:
    """All DB access for UserSkillScore (per-user current score cache)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # Reads
    def get_for_user(self, user_id: int) -> list[UserSkillScore]:
        """Return all skill scores for one user. Empty list if not diagnosed yet."""
        return (
            self.db.query(UserSkillScore)
            .filter(UserSkillScore.user_id == user_id)
            .order_by(UserSkillScore.skill_id.asc())
            .all()
        )

    def get_one(self, *, user_id: int, skill_id: int) -> UserSkillScore | None:
        """Get a single (user, skill) row, or None if it doesn't exist."""
        return (
            self.db.query(UserSkillScore)
            .filter(
                UserSkillScore.user_id == user_id,
                UserSkillScore.skill_id == skill_id,
            )
            .first()
        )

    # Writes
    def upsert_score(
        self,
        *,
        user_id: int,
        skill_id: int,
        score: float,
        is_estimated: bool = False,
    ) -> UserSkillScore:
        """Insert a new score, or update if (user_id, skill_id) already exists.
        
        Service decides when to commit — this method only flushes.
        """
        existing = self.get_one(user_id=user_id, skill_id=skill_id)

        if existing is not None:
            existing.score = score
            existing.is_estimated = is_estimated
            self.db.flush()
            return existing

        new_row = UserSkillScore(
            user_id=user_id,
            skill_id=skill_id,
            score=score,
            is_estimated=is_estimated,
        )
        self.db.add(new_row)
        self.db.flush()
        return new_row
