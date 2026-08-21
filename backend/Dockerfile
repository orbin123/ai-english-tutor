# syntax=docker/dockerfile:1
#
# LingosAI backend — multi-stage, uv-based, non-root, slim runtime.
#
# Stage 1 (builder) resolves the locked dependency set into a self-contained
# virtualenv; stage 2 (runtime) ships only that venv + the app code, with no
# build toolchain and a non-root user. Base images are pinned by index digest
# so the build is reproducible across architectures (CI amd64 / local arm64).
#
# Migrations are NOT run here — they run as a separate one-off task so N tasks
# don't race `alembic upgrade head` (Phase 1.13 policy; see docs/RUNBOOK.md).

# ---------------------------------------------------------------------------
# Stage 1 — builder
# ---------------------------------------------------------------------------
# ghcr.io/astral-sh/uv:python3.11-bookworm-slim
FROM ghcr.io/astral-sh/uv@sha256:4f5d923c9dcea037f57bda425dd209f3ec643da2f0b74227f68d09dab0b3bb36 AS builder

# Compile to .pyc at install time (faster cold start); copy rather than hardlink
# (the venv is copied across a stage boundary, so links would dangle).
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Dependency layer first: only pyproject + lockfile, so editing app code does
# not bust the (slow) dependency install cache. --no-install-project installs
# only third-party deps; --no-dev excludes the test/lint toolchain.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Now the application code. uv.lock is the source of truth; --frozen fails if it
# is stale relative to pyproject.toml.
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY scripts ./scripts
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
# python:3.11-slim-bookworm
FROM python@sha256:e2d3af735aff6eeee600b1933bedd99da6645fedf572cc12ef4cc1331f2ceebe AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Azure Speech SDK (azure-cognitiveservices-speech) is a NATIVE library, not
# pure Python: pronunciation assessment (/diagnosis/pronunciation-score) loads a
# C++ core that links libasound2 (ALSA) and needs ca-certificates + libssl to
# open the TLS connection to the Azure Speech endpoint. The slim base ships none
# of these, so the call hangs ~28s then fails and the route returns 502 — it
# works on a dev Mac but not in the container (a local↔prod parity bug). Install
# the runtime deps here. (libssl3 is usually already present; listed for clarity
# and to fail loudly if a future base image drops it.)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libasound2 \
        libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime user (no shell, no home). Owns /app so the app can write its
# media _cache dirs under app/ai/** when running locally without Azure Blob.
RUN groupadd --system --gid 10001 appgroup \
    && useradd --system --uid 10001 --gid appgroup --no-create-home appuser

WORKDIR /app

# Bring over the resolved venv and the app code from the builder.
COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appgroup /app/app /app/app
COPY --from=builder --chown=appuser:appgroup /app/alembic /app/alembic
COPY --from=builder --chown=appuser:appgroup /app/alembic.ini /app/alembic.ini
COPY --from=builder --chown=appuser:appgroup /app/scripts /app/scripts

# Strip the build toolchain the base image seeds into the SYSTEM site-packages
# (pip/setuptools/wheel + setuptools' vendored jaraco.context). The app runs
# entirely from /app/.venv (first on PATH) and never installs packages at
# runtime, so these are unused — but Trivy flags their CVEs (CVE-2026-24049
# wheel, CVE-2026-23949 jaraco.context). Removing them realizes this image's
# "no build toolchain" goal and keeps the HIGH/CRITICAL gate green. Verified:
# the full app + AI stack, passlib bcrypt, cryptography and python-jose all
# import without pkg_resources.
RUN rm -rf \
    /usr/local/lib/python3.11/site-packages/setuptools* \
    /usr/local/lib/python3.11/site-packages/pkg_resources \
    /usr/local/lib/python3.11/site-packages/_distutils_hack \
    /usr/local/lib/python3.11/site-packages/distutils-precedence.pth \
    /usr/local/lib/python3.11/site-packages/wheel* \
    /usr/local/lib/python3.11/site-packages/pip* \
    /usr/local/bin/pip*

USER appuser

EXPOSE 8000

# Production process model: gunicorn supervising Uvicorn workers (graceful
# restarts, worker supervision, request timeouts). Mirrors
# backend/scripts/start-prod.sh.
#
# WEB_CONCURRENCY defaults to 1. AI_RATE_LIMIT_BACKEND=memory requires exactly
# one worker because its usage buckets are process-local. A multi-worker
# deployment must select the shared Redis backend. Session correctness itself
# remains guarded by database constraints rather than in-memory state.
CMD ["sh", "-c", "exec gunicorn app.main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers ${WEB_CONCURRENCY:-1} \
  --bind 0.0.0.0:${PORT:-8000} \
  --timeout 120 \
  --graceful-timeout 30 \
  --access-logfile - \
  --error-logfile -"]
