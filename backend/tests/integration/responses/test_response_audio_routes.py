"""Route tests for learner audio transcription uploads."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.responses import routes as response_routes
from app.modules.subscriptions.dependencies import require_active_access


class FakeSTTService:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.duration_seconds = 2.0

    async def transcribe(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "text": "I usually wake up at seven.",
            "duration_seconds": self.duration_seconds,
        }


@pytest.fixture()
def response_client(tmp_path, monkeypatch):
    fake_stt = FakeSTTService()
    user = User(id=42, email="learner@example.com", name="Learner")

    monkeypatch.setattr(
        response_routes.settings,
        "LEARNER_AUDIO_DIR",
        str(tmp_path / "learner_audio"),
    )
    response_routes._reset_learner_audio_storage()
    monkeypatch.setattr(response_routes, "get_default_stt_service", lambda: fake_stt)

    app = FastAPI()
    app.include_router(response_routes.router)
    app.dependency_overrides[get_current_user] = lambda: user
    # Entitlement is covered by test_premium_guard; stub it out here.
    app.dependency_overrides[require_active_access] = lambda: user
    with TestClient(app) as client:
        yield client, fake_stt

    app.dependency_overrides.clear()
    response_routes._reset_learner_audio_storage()


def test_transcribe_audio_rejects_empty_upload_before_stt(response_client):
    client, fake_stt = response_client

    response = client.post(
        "/responses/transcribe-audio",
        data={"language": "en"},
        files={"audio": ("empty.webm", b"", "audio/webm")},
    )

    assert response.status_code == 400
    assert fake_stt.calls == []


def test_transcribe_audio_rejects_unsupported_upload_before_stt(response_client):
    client, fake_stt = response_client

    response = client.post(
        "/responses/transcribe-audio",
        data={"language": "en"},
        files={"audio": ("notes.txt", b"not audio", "text/plain")},
    )

    assert response.status_code == 415
    assert fake_stt.calls == []


def test_transcribe_audio_rejects_oversized_upload_before_stt(
    response_client, monkeypatch
):
    client, fake_stt = response_client
    monkeypatch.setattr(response_routes.settings, "MAX_AUDIO_UPLOAD_BYTES", 10)

    response = client.post(
        "/responses/transcribe-audio",
        data={"language": "en"},
        files={"audio": ("large.webm", b"x" * 11, "audio/webm")},
    )

    assert response.status_code == 413
    assert fake_stt.calls == []


def test_transcribe_audio_rejects_provider_reported_overlong_recording(
    response_client, monkeypatch
):
    client, fake_stt = response_client
    fake_stt.duration_seconds = 46.0
    monkeypatch.setattr(response_routes.settings, "MAX_AUDIO_DURATION_SECONDS", 45.0)

    response = client.post(
        "/responses/transcribe-audio",
        data={"language": "en"},
        files={"audio": ("long.webm", b"fake webm bytes", "audio/webm")},
    )

    assert response.status_code == 413
    assert len(fake_stt.calls) == 1


def test_transcribe_audio_stores_successful_upload_behind_auth_route(response_client):
    client, fake_stt = response_client

    response = client.post(
        "/responses/transcribe-audio",
        data={"language": "en"},
        files={"audio": ("clip.webm", b"fake webm bytes", "audio/webm")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["transcript"] == "I usually wake up at seven."
    assert body["audio_url"].startswith("/responses/audio/")
    assert not body["audio_url"].startswith("/audio/")
    assert len(fake_stt.calls) == 1

    audio_response = client.get(body["audio_url"])
    assert audio_response.status_code == 200
    assert audio_response.content == b"fake webm bytes"
    assert audio_response.headers["content-type"].startswith("audio/webm")
