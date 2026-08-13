"""Production AI debug endpoints must fail before any provider call."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.routes import router
from app.core.config import settings


def test_ai_debug_routes_return_not_found_in_production(monkeypatch) -> None:
    monkeypatch.setattr(settings, "environment", "production")
    app = FastAPI()
    app.include_router(router)

    response = TestClient(app).get("/debug/ai/ping")

    assert response.status_code == 404
