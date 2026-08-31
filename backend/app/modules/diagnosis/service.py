"""Business logic for the diagnosis flow."""

from sqlalchemy.orm import Session

from app.modules.auth.repository import UserProfileRepository
from app.modules.diagnosis.diagnosis_agents.diagnosis_feedback import (
    DiagnosisFeedbackOutput,
    generate_diagnosis_feedback,
)
from app.modules.diagnosis.diagnosis_agents.evaluators import RuleBasedEvaluator
from app.modules.diagnosis.diagnosis_agents.writing_evaluator import (
    evaluate_writing,
)
from app.modules.diagnosis.exceptions import (
    DiagnosisAlreadyCompleted,
    DiagnosisInvalidPayload,
)
from app.modules.diagnosis.schemas import (
    DiagnosisSubmitRequest,
    ReadAloudAnalysisOut,
    ReadAloudIn,
)
from app.modules.diagnosis.scoring import compute_skill_scores
from app.modules.personalization.service import PersonalizationService
from app.modules.progress.repository import SkillPointsRepository
from app.modules.skills.repository import SkillRepository

# Azure word-accuracy below this (0–100) flags a word as "to improve".
_WORD_IMPROVE_ACCURACY_THRESHOLD = 60.0
_MAX_WORDS_TO_IMPROVE = 6


def _build_read_aloud_analysis(read_aloud: ReadAloudIn) -> ReadAloudAnalysisOut:
    """Turn the submitted Azure pronunciation result into the result-page view.

    ``words_to_improve`` collects words Azure flagged with an error type or
    scored below the accuracy threshold, deduped (case-insensitive) and capped.
    """
    seen: set[str] = set()
    words_to_improve: list[str] = []
    for word in read_aloud.words:
        token = word.word.strip()
        if not token:
            continue
        flagged = bool(word.error_type) or (
            word.accuracy_score < _WORD_IMPROVE_ACCURACY_THRESHOLD
        )
        key = token.lower()
        if flagged and key not in seen:
            seen.add(key)
            words_to_improve.append(token)
        if len(words_to_improve) >= _MAX_WORDS_TO_IMPROVE:
            break

    return ReadAloudAnalysisOut(
        overall=read_aloud.overall_score,
        accuracy=read_aloud.accuracy_score,
        fluency=read_aloud.fluency_score,
        completeness=read_aloud.completeness_score,
        prosody=read_aloud.prosody_score,
        words_to_improve=words_to_improve,
    )


class DiagnosisService:
    """Orchestrates the diagnosis flow: evaluators → scoring → DB writes → AI feedback."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.profiles = UserProfileRepository(db)
        self.skills = SkillRepository(db)
        self.points = SkillPointsRepository(db)
        self.rule_eval = RuleBasedEvaluator()

    async def run_diagnosis(
        self, *, user_id: int, payload: DiagnosisSubmitRequest
    ) -> tuple[dict[str, float], DiagnosisFeedbackOutput, ReadAloudAnalysisOut]:
        """Process a complete diagnosis submission.

        Steps:
          1. Verify user has not already completed diagnosis
          2. Grade fill-blank (rule-based) + writing (LLM); read read-aloud
             scores straight from the submitted Azure assessment
          3. Apply master scoring formula → 7 skill scores
          4. Seed `skill_points` with `round(score * 1000)` per skill
          5. Update user_profile (self-assessment fields + diagnosis_completed)
          6. Single DB commit
          7. Call AI feedback agent with scores → get human-friendly feedback

        Returns:
            Tuple of (skill_scores dict, DiagnosisFeedbackOutput,
            ReadAloudAnalysisOut).

        Raises:
            DiagnosisInvalidPayload: submitted answers reference an unknown set
            DiagnosisAlreadyCompleted: user already diagnosed
        """
        # 1. Load profile, backfilling it for the rare account that never got
        # one at signup (e.g. the fresh-admin bootstrap). The row is committed
        # with the rest of the diagnosis writes in step 6.
        profile = self.profiles.ensure_default(user_id)
        if profile.diagnosis_completed:
            raise DiagnosisAlreadyCompleted(
                f"User {user_id} has already completed diagnosis"
            )

        # 2. Run evaluators
        try:
            fill_correct = self.rule_eval.evaluate_fill_blank(
                question_set_id=payload.fill_blank.question_set_id,
                user_answers=payload.fill_blank.answers,
            )
        except ValueError as exc:
            raise DiagnosisInvalidPayload(str(exc)) from exc
        writing = await evaluate_writing(
            prompt_id=payload.writing.prompt_id,
            response_text=payload.writing.response_text,
        )
        # Read-aloud was already scored by Azure on the frontend; just project
        # the submitted scores into the result-page view model.
        read_aloud_analysis = _build_read_aloud_analysis(payload.read_aloud)

        # 3. Compute 7 scores. Azure scores are 0–100; the formula wants 0–1.
        sa = payload.self_assessment
        skill_scores = compute_skill_scores(
            level=sa.self_assessed_level,
            exposure=sa.content_exposure,
            fill_blank_correct_count=fill_correct,
            writing_expression=writing.expression_score,
            writing_vocabulary=writing.vocabulary_score,
            writing_tone=writing.tone_score,
            speech_fluency=payload.read_aloud.fluency_score / 100.0,
            speech_clarity=payload.read_aloud.accuracy_score / 100.0,
        )

        # 4. Seed SkillPoints from diagnosis values (1.0 score = 1000 points).
        # The legacy `user_skill_scores` (WMA cache) was retired in the
        # Phase 8 cutover — diagnosis writes only the points-based store.
        name_to_id = self.skills.name_to_id_map()
        for skill_name, score in skill_scores.items():
            self.points.upsert_points(
                user_id=user_id,
                skill_id=name_to_id[skill_name],
                points=round(score * 1000),
            )

        # 5. Update profile
        profile.self_assessed_level = sa.self_assessed_level
        profile.goal = sa.goal
        profile.daily_time_minutes = sa.daily_time_minutes
        profile.content_exposure = sa.content_exposure
        profile.interests = ",".join(sa.interests)
        profile.diagnosis_completed = True

        # 6. Commit transaction
        self.db.commit()

        # 6b. Refresh structured personalisation so the planner has a
        # populated profile by the first lesson. Best-effort — a failure
        # here must not surface to the user.
        try:
            await PersonalizationService(self.db).refresh_for_user(user_id)
            self.db.commit()
        except Exception:
            self.db.rollback()

        # 7. Call AI feedback agent. Weakest/strongest are picked here so the
        # prose can never disagree with the numbers on screen.
        ranked = sorted(skill_scores.items(), key=lambda kv: kv[1])
        weakest_skill = ranked[0][0]
        strongest_skill = ranked[-1][0]

        feedback = await generate_diagnosis_feedback(
            self_assessed_level=sa.self_assessed_level.value,
            goal=sa.goal.value,
            skill_scores=skill_scores,
            weakest_skill=weakest_skill,
            strongest_skill=strongest_skill,
        )

        return skill_scores, feedback, read_aloud_analysis
