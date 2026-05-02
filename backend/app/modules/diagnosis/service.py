"""Business logic for the diagnosis flow."""

from sqlalchemy.orm import Session

from app.ai.agents.diagnosis_feedback import (
    DiagnosisFeedbackOutput,
    generate_diagnosis_feedback,
)
from app.modules.auth.repository import UserProfileRepository
from app.modules.diagnosis.evaluators import (
    RuleBasedEvaluator,
    SpeechEvaluator,
    TextEvaluator,
)
from app.modules.diagnosis.exceptions import (
    DiagnosisAlreadyCompleted,
    DiagnosisInvalidPayload,
)
from app.modules.diagnosis.schemas import DiagnosisSubmitRequest
from app.modules.diagnosis.scoring import compute_skill_scores
from app.modules.skills.repository import (
    SkillRepository,
    UserSkillScoreRepository,
)


class DiagnosisService:
    """Orchestrates the diagnosis flow: evaluators → scoring → DB writes → AI feedback."""

    ESTIMATED_SKILLS: set[str] = {"pronunciation", "tone"}

    def __init__(self, db: Session) -> None:
        self.db = db
        self.profiles = UserProfileRepository(db)
        self.skills = SkillRepository(db)
        self.scores = UserSkillScoreRepository(db)
        self.rule_eval = RuleBasedEvaluator()
        self.text_eval = TextEvaluator()
        self.speech_eval = SpeechEvaluator()

    async def run_diagnosis(
        self, *, user_id: int, payload: DiagnosisSubmitRequest
    ) -> tuple[dict[str, float], DiagnosisFeedbackOutput]:
        """Process a complete diagnosis submission.

        Steps:
          1. Verify user has not already completed diagnosis
          2. Run 3 evaluators on the submission
          3. Apply master scoring formula → 7 skill scores
          4. Upsert each score into user_skill_scores
          5. Update user_profile (self-assessment fields + diagnosis_completed)
          6. Single DB commit
          7. Call AI feedback agent with scores → get human-friendly feedback

        Returns:
            Tuple of (skill_scores dict, DiagnosisFeedbackOutput)

        Raises:
            DiagnosisInvalidPayload: profile missing
            DiagnosisAlreadyCompleted: user already diagnosed
        """
        # 1. Load + guard profile
        profile = self.profiles.get_by_user_id(user_id)
        if profile is None:
            raise DiagnosisInvalidPayload(
                f"No profile found for user {user_id}"
            )
        if profile.diagnosis_completed:
            raise DiagnosisAlreadyCompleted(
                f"User {user_id} has already completed diagnosis"
            )

        # 2. Run evaluators
        fill_correct = self.rule_eval.evaluate_fill_blank(
            question_set_id=payload.fill_blank.question_set_id,
            user_answers=payload.fill_blank.answers,
        )
        writing = self.text_eval.evaluate_writing(
            prompt_id=payload.writing.prompt_id,
            response_text=payload.writing.response_text,
        )
        # Speech evaluator now uses the Whisper transcript (not a stub audio_url)
        speech = self.speech_eval.evaluate_read_aloud(
            passage_id=payload.read_aloud.passage_id,
            transcript=payload.read_aloud.transcript,
            duration_seconds=payload.read_aloud.duration_seconds,
        )

        # 3. Compute 7 scores
        sa = payload.self_assessment
        skill_scores = compute_skill_scores(
            level=sa.self_assessed_level,
            exposure=sa.content_exposure,
            fill_blank_correct_count=fill_correct,
            writing_expression=writing["expression_score"],
            writing_vocabulary=writing["vocabulary_score"],
            writing_tone=writing["tone_score"],
            speech_fluency=speech["fluency_score"],
            speech_clarity=speech["clarity_score"],
        )

        # 4. Upsert each score
        name_to_id = self.skills.name_to_id_map()
        for skill_name, score in skill_scores.items():
            self.scores.upsert_score(
                user_id=user_id,
                skill_id=name_to_id[skill_name],
                score=score,
                is_estimated=skill_name in self.ESTIMATED_SKILLS,
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

        # 7. Call AI feedback agent
        weakest = sorted(skill_scores.items(), key=lambda kv: kv[1])[:2]
        weakest_skill_names = [name for name, _ in weakest]

        feedback = await generate_diagnosis_feedback(
            self_assessed_level=sa.self_assessed_level.value,
            goal=sa.goal.value,
            skill_scores=skill_scores,
            weakest_skills=weakest_skill_names,
        )

        return skill_scores, feedback
