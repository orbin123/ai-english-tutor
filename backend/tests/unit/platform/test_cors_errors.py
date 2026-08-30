"""``CorsErrorSafetyMiddleware`` keeps CORS headers on unhandled 500s.

Without it, an exception that escapes a route is turned into a 500 by
Starlette's ``ServerErrorMiddleware`` — which lives *outside* ``CORSMiddleware`` —
so the browser sees a misleading "No 'Access-Control-Allow-Origin' header" error
instead of the real failure.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.core.cors_errors import CorsErrorSafetyMiddleware

_ALLOWED = "https://www.lingosai.com"


def _client(monkeypatch) -> TestClient:
    monkeypatch.setattr("app.core.cors_errors.capture_to_sentry", lambda exc=None: None)
    app = FastAPI()
    app.add_middleware(CorsErrorSafetyMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[_ALLOWED],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.post("/boom")
    def boom() -> dict:
        raise RuntimeError("kaboom")

    @app.post("/ok")
    def ok() -> dict:
        return {"ok": True}

    return TestClient(app, raise_server_exceptions=False)


def test_unhandled_500_keeps_cors_header_for_allowed_origin(monkeypatch):
    monkeypatch.setattr(
        "app.core.cors_errors.settings.cors_origins", _ALLOWED, raising=False
    )
    client = _client(monkeypatch)
    resp = client.post("/boom", headers={"Origin": _ALLOWED})
    assert resp.status_code == 500
    assert resp.headers.get("access-control-allow-origin") == _ALLOWED
    assert resp.headers.get("access-control-allow-credentials") == "true"


def test_unhandled_500_omits_cors_header_for_unknown_origin(monkeypatch):
    monkeypatch.setattr(
        "app.core.cors_errors.settings.cors_origins", _ALLOWED, raising=False
    )
    client = _client(monkeypatch)
    resp = client.post("/boom", headers={"Origin": "https://evil.example"})
    assert resp.status_code == 500
    assert "access-control-allow-origin" not in resp.headers


def test_normal_response_is_untouched(monkeypatch):
    monkeypatch.setattr(
        "app.core.cors_errors.settings.cors_origins", _ALLOWED, raising=False
    )
    client = _client(monkeypatch)
    resp = client.post("/ok", headers={"Origin": _ALLOWED})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == _ALLOWED
