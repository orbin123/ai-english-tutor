"""Diagnosis writes only `SkillPoints` — the legacy `user_skill_scores`
WMA cache is gone in the Phase 8 cutover.

Two layers of evidence:

1. **DB**: a real `run_diagnosis` against an in-memory SQLite produces 7
   `SkillPoints` rows with `points = round(score * 1000)` per skill, and
   the `user_skill_scores` table is never touched (we don't even map it
   in the test schema).
2. **Module shape**: `DiagnosisService.__init__` does not hold any
   reference named `scores`, and `diagnosis/service.py` no longer
   imports `UserSkillScoreRepository`. Guards against accidental
   re-introduction.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect as sa_inspect
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401 — populate Base.metadata
from app.core.database import Base
from app.modules.auth.models import (
    ContentExposure,
    SelfAssessedLevel,
    User,
    UserGoal,
    UserProfile,
)
from app.modules.diagnosis import service as diagnosis_service_module
from app.modules.diagnosis.diagnosis_agents.diagnosis_feedback import (
    FocusCallout,
    SkillCallout,
)
from app.modules.diagnosis.diagnosis_agents.writing_evaluator import (
    DiagnosisWritingScores,
)
from app.modules.diagnosis.schemas import (
    DiagnosisSubmitRequest,
    FillBlankIn,
    PronunciationWordIn,
    ReadAloudIn,
    SelfAssessmentIn,
    WritingIn,
)
from app.modules.diagnosis.service import DiagnosisService
from app.modules.progress.models import SkillPoints
from app.modules.skills.models import Skill
from app.scoring import SUB_SKILLS


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    # Deliberately omit UserSkillScore from the schema — the test asserts
    # diagnosis works without that table existing.
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            UserProfile.__table__,
            Skill.__table__,
            SkillPoints.__table__,
        ],
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = SessionLocal()
    try:
        _seed_world(db)
        yield db
    finally:
        db.close()
        engine.dispose()


def _seed_world(db) -> User:
    user = User(email="diag@example.com", password_hash="x", name="L")
    db.add(user)
    db.flush()
    db.add(UserProfile(user_id=user.id))
    for sub_skill in SUB_SKILLS:
        db.add(Skill(name=sub_skill, description=sub_skill, display_label=sub_skill))
    db.commit()
    return user


def _sample_payload() -> DiagnosisSubmitRequest:
    return DiagnosisSubmitRequest(
        self_assessment=SelfAssessmentIn(
            self_assessed_level=SelfAssessedLevel.BEGINNER,
            goal=UserGoal.CASUAL,
            daily_time_minutes=15,
            content_exposure=ContentExposure.LOW,
            interests=["movies"],
        ),
        fill_blank=FillBlankIn(
            question_set_id="diag_fillblank_v1",
            # Canonical answers from FILL_BLANK_ANSWERS_V1.
            answers=["goes", "ate", "rains", "lived", "was written"],
        ),
        writing=WritingIn(
            prompt_id="diag_writing_v1",
            response_text=(
                "Last weekend I visited a small village near my city. "
                "We hiked a short trail and stopped for lunch by the river."
            ),
        ),
        read_aloud=ReadAloudIn(
            passage_id="diag_passage_v1",
            overall_score=82.0,
            accuracy_score=86.0,
            fluency_score=78.0,
            completeness_score=92.0,
            prosody_score=75.0,
            words=[
                PronunciationWordIn(word="every", accuracy_score=95.0, error_type=None),
                PronunciationWordIn(
                    word="neighbours",
                    accuracy_score=40.0,
                    error_type="Mispronunciation",
                ),
                PronunciationWordIn(
                    word="clearly", accuracy_score=55.0, error_type=None
                ),
            ],
        ),
    )


@pytest.fixture()
def _stub_diagnosis_llms(monkeypatch):
    """Stub the LLM writing evaluator, the LLM feedback agent, and the
    personalization refresh so diagnosis runs offline."""

    async def _fake_writing(**_kwargs):
        return DiagnosisWritingScores(
            writing_score=7.0,
            expression_score=0.6,
            vocabulary_score=0.5,
            tone_score=0.5,
        )

    async def _fake_feedback(**_kwargs):
        return diagnosis_service_module.DiagnosisFeedbackOutput(
            estimated_level_label="B1 · Intermediate",
            level_description="ok",
            summary="ok",
            biggest_weakness=SkillCallout(skill_name="tone", description="ok"),
            strongest_skill=SkillCallout(skill_name="grammar", description="ok"),
            first_focus=FocusCallout(title="Speaking", description="ok"),
        )

    async def _noop_refresh(self, user_id: int):  # noqa: ARG001
        return None

    monkeypatch.setattr(diagnosis_service_module, "evaluate_writing", _fake_writing)
    monkeypatch.setattr(
        diagnosis_service_module, "generate_diagnosis_feedback", _fake_feedback
    )
    monkeypatch.setattr(
        diagnosis_service_module.PersonalizationService,
        "refresh_for_user",
        _noop_refresh,
    )


class TestDiagnosisWritesPointsOnly:
    @pytest.mark.asyncio
    async def test_seeds_seven_skill_points_rows(
        self, db_session, _stub_diagnosis_llms
    ):
        user = db_session.query(User).one()
        svc = DiagnosisService(db_session)
        skill_scores, _feedback, read_aloud = await svc.run_diagnosis(
            user_id=user.id, payload=_sample_payload()
        )

        # Read-aloud analysis carries the 5 Azure metrics straight through,
        # and words_to_improve is derived from the flagged words (error_type
        # set OR accuracy below the threshold), deduped.
        assert read_aloud.overall == 82.0
        assert read_aloud.accuracy == 86.0
        assert read_aloud.fluency == 78.0
        assert read_aloud.completeness == 92.0
        assert read_aloud.prosody == 75.0
        assert read_aloud.words_to_improve == ["neighbours", "clearly"]

        # 7 skill points rows, one per sub-skill.
        rows = (
            db_session.query(SkillPoints).filter(SkillPoints.user_id == user.id).all()
        )
        assert len(rows) == 7

        # Each row's `points` is the round(score * 1000) of the matching
        # skill, capped at 10000 by SkillPointsRepository.upsert_points.
        skills_by_id = {s.id: s.name for s in db_session.query(Skill).all()}
        points_by_name = {skills_by_id[r.skill_id]: r.points for r in rows}
        for name, score in skill_scores.items():
            assert points_by_name[name] == min(round(score * 1000), 10000)

        # The legacy WMA table was deliberately omitted from the test
        # schema. The diagnosis run completing without errors proves the
        # service no longer touches `user_skill_scores`.
        bind_tables = sa_inspect(db_session.get_bind()).get_table_names()
        assert "user_skill_scores" not in bind_tables

    @pytest.mark.asyncio
    async def test_backfills_a_missing_profile_instead_of_failing(
        self, db_session, _stub_diagnosis_llms
    ):
        # An account created without a profile (e.g. the fresh-admin
        # bootstrap) used to hit "No profile found for user N" on submit.
        user = User(email="no-profile@example.com", password_hash="x", name="NP")
        db_session.add(user)
        db_session.commit()
        assert user.profile is None

        svc = DiagnosisService(db_session)
        skill_scores, _feedback, _read_aloud = await svc.run_diagnosis(
            user_id=user.id, payload=_sample_payload()
        )

        db_session.refresh(user)
        assert user.profile is not None
        assert user.profile.diagnosis_completed is True
        rows = (
            db_session.query(SkillPoints).filter(SkillPoints.user_id == user.id).all()
        )
        assert len(rows) == len(skill_scores) == 7


class TestModuleShape:
    """Belt-and-suspenders: the service file should not re-import the
    legacy WMA repository or expose a `scores` attribute, even if a
    future refactor reorders things.
    """

    def test_no_userskillscore_import(self):
        source = Path(inspect.getsourcefile(diagnosis_service_module)).read_text()
        # Drop the module docstring before scanning — a comment that
        # mentions the legacy table by name (for context) is fine.
        code = source.split('"""', 2)[-1] if source.startswith('"""') else source
        assert "UserSkillScoreRepository" not in code
        assert "self.scores" not in code
        assert "ESTIMATED_SKILLS" not in code

    def test_service_has_no_scores_attribute(self):
        # Construct without a DB session — only checks the class shape.
        # We instantiate with a dummy because __init__ touches repos that
        # don't require a real DB until methods are called.
        class _NullDB:
            def query(self, *_a, **_kw):
                raise AssertionError("DB should not be touched in __init__")

        svc = DiagnosisService(_NullDB())  # type: ignore[arg-type]
        assert not hasattr(svc, "scores")
        assert hasattr(svc, "points")
