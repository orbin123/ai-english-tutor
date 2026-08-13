from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.storage import BlobVisibility
from app.core.database import Base, get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import Role, User, UserRole
from app.modules.challenges.ielts_sprint import service as challenges_service
from app.modules.challenges.models import (
    Challenge,
    ChallengeAttempt,
    ChallengeAttemptStatus,
    ChallengeLevel,
)
from app.modules.challenges.ielts_sprint.evaluation_schemas import (
    IELTSFeedbackReport,
    SectionFeedback,
    SpeakingCriteriaEvaluation,
    SpeakingCriterionEvaluation,
    SpeakingEvaluationReport,
    SpeakingPromptEvaluation,
    SpeakingPronunciationEvaluation,
    WritingCriteriaEvaluation,
    WritingCriterionEvaluation,
    WritingEvaluationReport,
    WritingPromptEvaluation,
)
from app.modules.challenges.routes import router as challenges_router
from scripts.seed_ielts_challenge import seed_ielts_challenge


def _generated_task_payload(
    *,
    challenge_slug: str = "ielts",
    challenge_name: str = "IELTS Sprint",
    level_number: int = 1,
    level_name: str = "Level 1 - Quick Sprint",
) -> dict:
    return {
        "meta": {
            "challenge_slug": challenge_slug,
            "challenge_name": challenge_name,
            "level_number": level_number,
            "level_name": level_name,
            "phase": 3,
        },
        "sections": {
            "listening": {
                "widget": "listen_and_respond",
                "task_intro": "Listen to the short talk and answer the questions.",
                "instructions": "Audio arrives in Phase 5.",
                "audio_url": None,
                "audio_script": "A tutor explains how city gardens can improve neighborhoods.",
                "audio_duration_seconds": 45,
                "inner_widget": "mcq",
                "items": [
                    {
                        "item_id": "l1",
                        "prompt": "What is the speaker mainly discussing?",
                        "options": [
                            "Urban gardens",
                            "Train schedules",
                            "Exam registration",
                            "Museum rules",
                        ],
                        "correct_index": 0,
                        "explanation": "The transcript focuses on urban gardens.",
                    }
                ],
            },
            "reading": {
                "widget": "mcq",
                "task_intro": "Read the passage and choose the best answers.",
                "instructions": "Select one option for each question.",
                "passage_title": "Generated Passage on Urban Gardens",
                "passage": (
                    "Urban gardens are increasingly used to turn unused city spaces "
                    "into places for learning, social connection, and local food."
                ),
                "items": [
                    {
                        "item_id": "r1",
                        "prompt": "What is the passage mainly about?",
                        "options": [
                            "The benefits of urban gardens",
                            "The cost of international flights",
                            "The history of private cars",
                            "The design of mobile phones",
                        ],
                        "correct_index": 0,
                        "explanation": "The passage describes benefits of urban gardens.",
                    }
                ],
            },
            "writing": {
                "widget": "timed_text",
                "task_intro": "Write an IELTS-style response.",
                "instructions": "Use the global challenge timer.",
                "items": [
                    {
                        "item_id": "w1",
                        "prompt": (
                            "Some people think cities should convert unused land into "
                            "community gardens. To what extent do you agree?"
                        ),
                        "target_word_count": 80,
                    }
                ],
                "target_word_count": 80,
                "time_limit_seconds": 1200,
                "minimum_word_count": 40,
                "no_editing_allowed": False,
                "sample_response": "",
            },
            "speaking": {
                "widget": "speak_and_record",
                "task_intro": "Record a short spoken answer.",
                "instructions": "Speaking upload arrives in Phase 6.",
                "speaking_duration_seconds": 30,
                "speaking_prompts": ["Describe a green space in your city."],
                "sample_responses": [],
            },
        },
    }


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            Role.__table__,
            UserRole.__table__,
            Challenge.__table__,
            ChallengeLevel.__table__,
            ChallengeAttempt.__table__,
        ],
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def learner(db_session: Session) -> User:
    user = User(
        email="learner@example.com",
        password_hash="x",
        name="Learner",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def client(
    db_session: Session,
    learner: User,
    monkeypatch: pytest.MonkeyPatch,
):
    app = FastAPI()
    app.include_router(challenges_router, prefix="/api")

    class FakeGenerator:
        async def generate(self, *, context: dict) -> dict:
            return deepcopy(
                _generated_task_payload(
                    challenge_slug=context["challenge_slug"],
                    challenge_name=context["challenge_name"],
                    level_number=context["level_number"],
                    level_name=context["level_name"],
                )
            )

    class FakeWritingEvaluator:
        async def evaluate(self, *, context: dict) -> WritingEvaluationReport:
            criteria = WritingCriteriaEvaluation(
                task_response=WritingCriterionEvaluation(
                    band=6.0,
                    rationale="The response addresses the task with a relevant position.",
                ),
                coherence_and_cohesion=WritingCriterionEvaluation(
                    band=6.0,
                    rationale="Ideas are mostly organised with basic cohesion.",
                ),
                lexical_resource=WritingCriterionEvaluation(
                    band=6.0,
                    rationale="Vocabulary is adequate for the prompt.",
                ),
                grammatical_range_and_accuracy=WritingCriterionEvaluation(
                    band=6.0,
                    rationale="Grammar is understandable with some errors.",
                ),
            )
            writing_task = context["writing_task"]
            prompt = writing_task["items"][0]
            response = context["writing_responses"].get("w1", "")
            return WritingEvaluationReport(
                mode="ai_writing_phase_4",
                items=[
                    WritingPromptEvaluation(
                        item_id="w1",
                        prompt=prompt["prompt"],
                        response_excerpt=response,
                        response_word_count=len(response.split()),
                        criteria=criteria,
                        issues=[],
                        band=6.0,
                        summary="Route test writing evaluation.",
                    )
                ],
                section_band=6.0,
                summary="Route test writing evaluation.",
            )

    class FakeSpeakingEvaluator:
        async def evaluate(self, *, context: dict) -> SpeakingEvaluationReport:
            criteria = SpeakingCriteriaEvaluation(
                fluency_and_coherence=SpeakingCriterionEvaluation(
                    band=6.0,
                    rationale="The transcript gives a connected answer.",
                ),
                lexical_resource=SpeakingCriterionEvaluation(
                    band=6.0,
                    rationale="Vocabulary is relevant to the prompt.",
                ),
                grammatical_range_and_accuracy=SpeakingCriterionEvaluation(
                    band=6.0,
                    rationale="Grammar is understandable.",
                ),
                pronunciation=SpeakingPronunciationEvaluation(
                    available=False,
                    band=None,
                    rationale=(
                        "Pronunciation requires audio-level scoring and is not "
                        "evaluated in Phase 6."
                    ),
                ),
            )
            return SpeakingEvaluationReport(
                mode="ai_speaking_phase_6",
                items=[
                    SpeakingPromptEvaluation(
                        item_id="s1",
                        prompt="Describe a green space in your city.",
                        transcript_excerpt=context["speaking_responses"]["s1"][
                            "transcript"
                        ],
                        transcript_word_count=8,
                        criteria=criteria,
                        band=6.0,
                        summary="Route test speaking evaluation.",
                    )
                ],
                section_band=6.0,
                pronunciation_available=False,
                summary="Route test speaking evaluation.",
            )

    class FakeFeedbackAgent:
        async def generate(self, *, context: dict) -> IELTSFeedbackReport:
            section_feedback = SectionFeedback(
                went_well=["Specific work was recorded."],
                needs_work=["Keep building accuracy."],
                next_tip="Review one missed item before retrying.",
            )
            return IELTSFeedbackReport(
                mode="phase_4_feedback",
                overall_summary="Fake Phase 4 feedback.",
                sections={
                    "listening": section_feedback,
                    "reading": section_feedback,
                    "writing": section_feedback,
                    "speaking": section_feedback,
                },
            )

    class FakeTTSService:
        async def synthesize(
            self,
            *,
            text: str,
            voice: str | None = None,
            speed: float = 1.0,
            style_instructions: str | None = None,
        ) -> dict:
            return {
                "audio_url": "/audio/ab/abcdef1234567890.mp3",
                "duration_seconds": 11.8,
                "cache_hit": False,
            }

    class FakeBlobStorage:
        async def get(self, *, key: str) -> bytes | None:
            if key == "abcdef1234567890.mp3":
                return b"route fake mp3"
            return None

    class FakeSTTService:
        async def transcribe(
            self,
            *,
            audio_bytes: bytes,
            filename: str,
            language: str = "en",
            with_timestamps: bool = False,
        ) -> dict:
            return {
                "text": "I visit a small park because it is calm and useful.",
                "language": language,
                "duration_seconds": 3.6,
                "words": None,
            }

    class FakeSpeakingAudioStorage:
        store: dict[str, bytes] = {}

        def __init__(
            self,
            *,
            cache_dir,
            public_url_prefix,
            visibility: BlobVisibility,
        ) -> None:
            self.cache_dir = cache_dir
            self.public_url_prefix = public_url_prefix
            assert visibility is BlobVisibility.PRIVATE
            self.visibility = visibility

        async def put(self, *, key: str, data: bytes, content_type: str) -> dict:
            self.store[key] = data
            return {
                "public_url": f"/internal/{key}",
                "storage_key": key,
                "content_type": content_type,
                "size_bytes": len(data),
            }

        async def get(self, *, key: str) -> bytes | None:
            return self.store.get(key)

        async def exists(self, *, key: str) -> bool:
            return key in self.store

        async def delete(self, *, key: str) -> None:
            self.store.pop(key, None)

        def url_for(self, *, key: str) -> str:
            return f"/internal/{key}"

    FakeSpeakingAudioStorage.store = {}

    monkeypatch.setattr(challenges_service, "IELTSChallengeGenerator", FakeGenerator)
    monkeypatch.setattr(
        challenges_service,
        "IELTSChallengeWritingEvaluator",
        FakeWritingEvaluator,
    )
    monkeypatch.setattr(
        challenges_service,
        "IELTSChallengeSpeakingEvaluator",
        FakeSpeakingEvaluator,
    )
    monkeypatch.setattr(
        challenges_service,
        "IELTSChallengeFeedbackAgent",
        FakeFeedbackAgent,
    )
    monkeypatch.setattr(
        challenges_service,
        "get_default_tts_service",
        lambda: FakeTTSService(),
    )
    monkeypatch.setattr(
        challenges_service,
        "get_default_blob_storage",
        lambda: FakeBlobStorage(),
    )
    monkeypatch.setattr(
        challenges_service,
        "get_default_stt_service",
        lambda: FakeSTTService(),
    )
    monkeypatch.setattr(
        challenges_service,
        "build_blob_storage",
        FakeSpeakingAudioStorage,
    )

    def override_get_db():
        yield db_session

    def override_get_current_user():
        return learner

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _make_attempt(db: Session, *, user_id: int) -> ChallengeAttempt:
    seed_ielts_challenge(db)
    challenge = db.query(Challenge).filter_by(slug="ielts").one()
    level = (
        db.query(ChallengeLevel)
        .filter_by(challenge_id=challenge.id, level_number=1)
        .one()
    )
    now = datetime.now(timezone.utc)
    attempt = ChallengeAttempt(
        user_id=user_id,
        challenge_level_id=level.id,
        status=ChallengeAttemptStatus.COMPLETED,
        started_at=now,
        completed_at=now + timedelta(minutes=4),
        expires_at=now + timedelta(minutes=20),
        task_payload={"reading": {"questions": []}},
        response_payload={"reading": {}},
        overall_score=6.5,
        section_scores={"reading": 6.5},
        passed=True,
        evaluation_report={"overall": "stub"},
        feedback_report={"summary": "stub"},
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


def test_all_challenge_read_routes_are_mounted() -> None:
    app = FastAPI()
    app.include_router(challenges_router, prefix="/api")
    paths = [route.path for route in app.router.routes]

    assert "/api/v1/challenges" in paths
    assert "/api/v1/challenges/{slug}" in paths
    assert "/api/v1/challenges/{slug}/history" in paths
    assert "/api/v1/challenge-attempts/{attempt_id}" in paths
    assert "/api/v1/challenge-attempts/{attempt_id}/audio/{audio_key}" in paths
    assert (
        "/api/v1/challenge-attempts/{attempt_id}/speaking/{prompt_id}/audio/{audio_key}"
        in paths
    )
    assert (
        "/api/v1/challenge-attempts/{attempt_id}/speaking/{prompt_id}/upload" in paths
    )
    assert "/api/v1/challenges/{slug}/levels/{level_number}/attempts" in paths
    assert "/api/v1/challenge-attempts/{attempt_id}/begin" in paths
    assert "/api/v1/challenge-attempts/{attempt_id}/responses" in paths
    assert "/api/v1/challenge-attempts/{attempt_id}/submit" in paths


def test_list_challenges(client: TestClient, db_session: Session) -> None:
    seed_ielts_challenge(db_session)
    db_session.commit()

    response = client.get("/api/v1/challenges")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["slug"] == "ielts"
    assert body[0]["level_count"] == 3


def test_challenge_detail_includes_progress(
    client: TestClient,
    db_session: Session,
    learner: User,
) -> None:
    _make_attempt(db_session, user_id=learner.id)

    response = client.get("/api/v1/challenges/ielts")

    assert response.status_code == 200
    body = response.json()
    assert body["slug"] == "ielts"
    assert body["levels"][0]["best_score"] == 6.5
    assert body["levels"][0]["attempt_count"] == 1
    assert body["levels"][0]["in_progress_attempt_id"] is None
    assert body["levels"][1]["unlocked"] is True


def test_challenge_history_is_personal_and_marks_best(
    client: TestClient,
    db_session: Session,
    learner: User,
) -> None:
    attempt = _make_attempt(db_session, user_id=learner.id)

    response = client.get("/api/v1/challenges/ielts/history")

    assert response.status_code == 200
    body = response.json()
    assert body["challenge_slug"] == "ielts"
    assert body["attempts"][0]["id"] == attempt.id
    assert body["attempts"][0]["is_best_for_level"] is True


def test_get_attempt_requires_current_user(
    client: TestClient,
    db_session: Session,
    learner: User,
) -> None:
    attempt = _make_attempt(db_session, user_id=learner.id)
    other = User(email="other@example.com", password_hash="x", name="Other")
    db_session.add(other)
    db_session.commit()
    foreign_attempt = _make_attempt(db_session, user_id=other.id)

    own_response = client.get(f"/api/v1/challenge-attempts/{attempt.id}")
    foreign_response = client.get(f"/api/v1/challenge-attempts/{foreign_attempt.id}")

    assert own_response.status_code == 200
    assert own_response.json()["id"] == attempt.id
    assert foreign_response.status_code == 404


def test_start_attempt_stores_generated_text_task(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_ielts_challenge(db_session)
    db_session.commit()

    response = client.post("/api/v1/challenges/ielts/levels/1/attempts")

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "in_progress"
    assert body["timer_started_at"] is None
    assert body["expires_at"] is None
    assert body["task_payload"]["meta"]["phase"] == 3
    assert (
        body["task_payload"]["sections"]["reading"]["passage_title"]
        == "Generated Passage on Urban Gardens"
    )
    assert (
        "community gardens"
        in body["task_payload"]["sections"]["writing"]["items"][0]["prompt"]
    )
    listening = body["task_payload"]["sections"]["listening"]
    assert listening["audio_storage_key"] == "abcdef1234567890.mp3"
    assert listening["audio_url"] == (
        f"/api/v1/challenge-attempts/{body['id']}/audio/abcdef1234567890.mp3"
    )
    assert listening["audio_duration_seconds"] == 11.8
    assert body["response_payload"] is None

    audio_response = client.get(listening["audio_url"])
    assert audio_response.status_code == 200
    assert audio_response.content == b"route fake mp3"
    assert audio_response.headers["content-type"].startswith("audio/mpeg")


def test_start_attempt_rejects_locked_level(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_ielts_challenge(db_session)
    db_session.commit()

    response = client.post("/api/v1/challenges/ielts/levels/2/attempts")

    assert response.status_code == 403


def test_begin_attempt_starts_timer(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_ielts_challenge(db_session)
    db_session.commit()
    start_response = client.post("/api/v1/challenges/ielts/levels/1/attempts")
    attempt_id = start_response.json()["id"]

    begin_response = client.post(f"/api/v1/challenge-attempts/{attempt_id}/begin")

    assert begin_response.status_code == 200
    body = begin_response.json()
    assert body["timer_started_at"] is not None
    assert body["expires_at"] is not None


def test_patch_responses_autosaves_draft(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_ielts_challenge(db_session)
    db_session.commit()
    start_response = client.post("/api/v1/challenges/ielts/levels/1/attempts")
    attempt_id = start_response.json()["id"]
    payload = {"response_payload": {"reading": {"r1": "A"}, "writing": {"w1": "Draft"}}}

    response = client.patch(
        f"/api/v1/challenge-attempts/{attempt_id}/responses",
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["response_payload"] == payload["response_payload"]


def test_start_attempt_rejects_when_level_already_in_progress(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_ielts_challenge(db_session)
    db_session.commit()
    first = client.post("/api/v1/challenges/ielts/levels/1/attempts")
    assert first.status_code == 201

    second = client.post("/api/v1/challenges/ielts/levels/1/attempts")

    assert second.status_code == 409
    assert second.json()["detail"]["attempt_id"] == first.json()["id"]


def test_submit_attempt_persists_payload_and_scores(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_ielts_challenge(db_session)
    db_session.commit()
    start_response = client.post("/api/v1/challenges/ielts/levels/1/attempts")
    attempt_id = start_response.json()["id"]
    client.post(f"/api/v1/challenge-attempts/{attempt_id}/begin")
    payload = {
        "response_payload": {
            "reading": {"r1": "A", "r2": "B"},
            "writing": {"w1": "Short response"},
            "listening": {"l1": "A"},
            "speaking": {},
        }
    }

    response = client.post(
        f"/api/v1/challenge-attempts/{attempt_id}/submit",
        json=payload,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["response_payload"] == payload["response_payload"]
    assert body["overall_score"] == 6.0
    assert body["passed"] is True
    assert body["section_scores"]["listening"] == 9.0
    assert body["section_scores"]["reading"] == 9.0
    assert body["section_scores"]["writing"] == 6.0
    assert body["section_scores"]["speaking"] == 0.0
    assert body["evaluation_report"]["mode"] == "phase_6_speaking"
    assert body["evaluation_report"]["listening"]["total_correct"] == 1
    assert body["feedback_report"]["overall_summary"] == "Fake Phase 4 feedback."


def test_route_start_upload_speaking_submit_scores_transcript(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_ielts_challenge(db_session)
    db_session.commit()
    start_response = client.post("/api/v1/challenges/ielts/levels/1/attempts")
    attempt_id = start_response.json()["id"]
    client.post(f"/api/v1/challenge-attempts/{attempt_id}/begin")

    upload_response = client.post(
        f"/api/v1/challenge-attempts/{attempt_id}/speaking/s1/upload",
        files={"audio": ("speaking.webm", b"route webm bytes", "audio/webm")},
    )

    assert upload_response.status_code == 201
    upload = upload_response.json()
    assert upload["prompt_id"] == "s1"
    assert upload["audio_url"].endswith(upload["audio_storage_key"])

    replay_response = client.get(upload["audio_url"])
    assert replay_response.status_code == 200
    assert replay_response.content == b"route webm bytes"
    assert replay_response.headers["content-type"].startswith("audio/webm")

    submit_response = client.post(
        f"/api/v1/challenge-attempts/{attempt_id}/submit",
        json={
            "response_payload": {
                "reading": {"r1": "A"},
                "writing": {"w1": "Short response"},
                "listening": {"l1": "A"},
                "speaking": {"s1": upload},
            }
        },
    )

    assert submit_response.status_code == 200
    body = submit_response.json()
    speaking_response = body["response_payload"]["speaking"]["s1"]
    assert speaking_response["transcript"].startswith("I visit a small park")
    assert body["evaluation_report"]["mode"] == "phase_6_speaking"
    assert body["evaluation_report"]["speaking"]["pronunciation_available"] is False
    assert body["section_scores"]["speaking"] == 6.0
    assert body["feedback_report"]["overall_summary"] == "Fake Phase 4 feedback."


def test_submit_attempt_after_grace_marks_timed_out(
    client: TestClient,
    db_session: Session,
    learner: User,
) -> None:
    attempt = _make_attempt(db_session, user_id=learner.id)
    attempt.status = ChallengeAttemptStatus.IN_PROGRESS
    attempt.completed_at = None
    attempt.overall_score = None
    attempt.section_scores = None
    attempt.passed = None
    attempt.timer_started_at = datetime.now(timezone.utc) - timedelta(minutes=25)
    attempt.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    db_session.commit()

    response = client.post(
        f"/api/v1/challenge-attempts/{attempt.id}/submit",
        json={"response_payload": {"reading": {"r1": "A"}}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "timed_out"
    db_session.refresh(attempt)
    assert attempt.status == ChallengeAttemptStatus.TIMED_OUT
    assert attempt.overall_score is not None


def test_start_attempt_rejects_daily_attempt_cap(
    client: TestClient,
    db_session: Session,
    learner: User,
) -> None:
    seed_ielts_challenge(db_session)
    challenge = db_session.query(Challenge).filter_by(slug="ielts").one()
    level = (
        db_session.query(ChallengeLevel)
        .filter_by(challenge_id=challenge.id, level_number=1)
        .one()
    )
    now = datetime.now(timezone.utc)
    for index in range(10):
        db_session.add(
            ChallengeAttempt(
                user_id=learner.id,
                challenge_level_id=level.id,
                status=ChallengeAttemptStatus.COMPLETED,
                started_at=now - timedelta(minutes=index),
                completed_at=now - timedelta(minutes=index) + timedelta(minutes=3),
                expires_at=now + timedelta(minutes=20),
                task_payload={"sections": {}},
                response_payload={},
                overall_score=6.0,
                section_scores={"reading": 6.0},
                passed=True,
                evaluation_report={"overall": "stub"},
                feedback_report={"summary": "stub"},
            )
        )
    db_session.commit()

    response = client.post("/api/v1/challenges/ielts/levels/1/attempts")

    assert response.status_code == 429
