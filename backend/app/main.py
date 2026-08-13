"""FastAPI application entry point."""

import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.ai.routes import router as ai_router
from app.core.config import settings
from app.core.database import engine
from app.core.logging import AccessLogMiddleware, TraceIDMiddleware, configure_logging
from app.core.rate_limit import AdminRateLimitMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.sentry import init_sentry
from app.modules.admin.routes import router as admin_router
from app.modules.auth.routes import router as auth_router
from app.modules.blog.routes import (
    admin_router as blog_admin_router,
    public_router as blog_public_router,
)
from app.modules.challenges.routes import router as challenges_router
from app.modules.contact.routes import router as contact_router
from app.modules.diagnosis.routes import router as diagnosis_router
from app.modules.progress.routes import router as progress_router
from app.modules.subscriptions.payment_routes import payments_router
from app.modules.subscriptions.routes import (
    subscription_router,
    users_router,
)
from app.modules.learning_session.router import (
    rest_router as learning_rest_router,
    ws_router as learning_ws_router,
)
from app.modules.feedback.routes import feedback_router
from app.modules.preferences.routes import router as preferences_router
from app.modules.responses.routes import router as responses_router
from app.modules.reviews.routes import reviews_router
from app.modules.sessions.routes import router as sessions_router
from app.modules.streaks.routes import router as streaks_router

load_dotenv("../.env")

configure_logging()
init_sentry()

app = FastAPI(
    title="LingosAI - English Tutor API",
    version="0.1.0",
    redirect_slashes=False,  # prevents 307 redirect on /auth/google/callback
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.add_middleware(AdminRateLimitMiddleware)

# Runs inside TraceIDMiddleware so every access line carries a bound trace_id;
# wraps the rate limiter so 429s are logged too.
app.add_middleware(AccessLogMiddleware)

# Added last → outermost: stamps a trace_id before any other middleware logs.
app.add_middleware(TraceIDMiddleware)

# Security headers (HSTS, nosniff) — production-only, outermost so they ride on
# every response (incl. errors). No-op outside ENVIRONMENT=production.
app.add_middleware(SecurityHeadersMiddleware)


# ---------------------------------------------------------------------------
# Static files: serve cached AI blobs written by LocalBlobStorage.
#
# Today that includes:
#   - TTS audio under /audio/<shard>/<key>.mp3
#   - image-generation outputs under /images/<shard>/<key>.png
#
# In production this would likely move to S3 / Cloudflare R2 with a CDN.
# For dev, StaticFiles is the simplest possible path: the same files
# `LocalBlobStorage` writes to disk become directly fetchable here.
# ---------------------------------------------------------------------------
_audio_root = Path(settings.TTS_CACHE_DIR).resolve()
_audio_root.mkdir(parents=True, exist_ok=True)
app.mount(
    settings.TTS_PUBLIC_URL_PREFIX,
    StaticFiles(directory=_audio_root),
    name="audio",
)

_image_root = Path(settings.IMAGEGEN_CACHE_DIR).resolve()
_image_root.mkdir(parents=True, exist_ok=True)
app.mount(
    settings.IMAGEGEN_PUBLIC_URL_PREFIX,
    StaticFiles(directory=_image_root),
    name="images",
)

_blog_media_root = Path(settings.BLOG_MEDIA_CACHE_DIR).resolve()
_blog_media_root.mkdir(parents=True, exist_ok=True)
app.mount(
    settings.BLOG_MEDIA_PUBLIC_URL_PREFIX,
    StaticFiles(directory=_blog_media_root),
    name="blog-media",
)


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    """Friendly landing payload so browsers hitting `/` don't see a 404."""
    return {
        "app": "LingosAI",
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Liveness probe — confirms the process is up. Always 200; no dependencies.

    Use this for the container/orchestrator liveness check: a 200 means "the
    process is alive, don't kill it". For "is this task ready to serve traffic"
    use /health/ready, which checks DB + Redis.
    """
    return {"status": "ok"}


@app.get("/health/ready", tags=["system"])
def readiness_check() -> JSONResponse:
    """Readiness probe — 200 only when DB **and** Redis are reachable.

    Wired to the ALB/ECS target-group health check so a task with a broken
    dependency is pulled out of rotation instead of serving 500s. Returns 503
    with a per-dependency breakdown when anything is down.
    """
    checks: dict[str, str] = {}
    ready = True

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # pragma: no cover - exercised manually
        ready = False
        checks["database"] = "error"
        logging.getLogger("app.health").warning("readiness_db_failed: %s", exc)

    try:
        import redis

        client = redis.Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
        client.ping()
        checks["redis"] = "ok"
    except Exception as exc:  # pragma: no cover - exercised manually
        ready = False
        checks["redis"] = "error"
        logging.getLogger("app.health").warning("readiness_redis_failed: %s", exc)

    return JSONResponse(
        status_code=status.HTTP_200_OK
        if ready
        else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "ready" if ready else "not_ready", "checks": checks},
    )


app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(admin_router)
app.include_router(diagnosis_router, prefix="/diagnosis", tags=["diagnosis"])
app.include_router(progress_router)
if settings.environment != "production":
    app.include_router(ai_router)
app.include_router(subscription_router)
app.include_router(payments_router)
app.include_router(users_router)
app.include_router(challenges_router, prefix="/api")
app.include_router(sessions_router, prefix="/api")
app.include_router(streaks_router, prefix="/api")
app.include_router(preferences_router, prefix="/api")
app.include_router(responses_router)
app.include_router(learning_rest_router, prefix="/api")
app.include_router(learning_ws_router)
app.include_router(reviews_router)
app.include_router(feedback_router)
app.include_router(blog_public_router)
app.include_router(blog_admin_router)
app.include_router(contact_router)
