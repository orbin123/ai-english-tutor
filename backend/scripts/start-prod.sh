#!/usr/bin/env bash
#
# Production entrypoint: gunicorn supervising Uvicorn workers.
#
# Why gunicorn over a bare `uvicorn`: graceful restarts, worker supervision
# (a crashed worker is replaced), and request timeouts — the things you want
# when the process faces the public internet.
#
# Worker count: defaults to 1. Multi-worker is now SAFE for correctness — the
# session-completion double-scoring race (audit B4) is guarded by the unique
# constraint on session_scorecards.session_id, not an in-memory set. Still,
# AI_RATE_LIMIT_BACKEND=memory requires WEB_CONCURRENCY=1 because its buckets
# are process-local. Select the Redis backend before raising worker count.
# (smaller tasks, granular ALB health checks); raise to (2 x vCPU)+1 per task
# only when a single worker per task is the bottleneck.
#
# Migrations are NOT run here — they run as a separate one-off task so N tasks
# don't race `alembic upgrade head` (see docs/RUNBOOK.md, migration policy).
set -euo pipefail
cd "$(dirname "$0")/.."

exec uv run gunicorn app.main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers "${WEB_CONCURRENCY:-1}" \
  --bind "0.0.0.0:${PORT:-8000}" \
  --timeout 120 \
  --graceful-timeout 30 \
  --access-logfile - \
  --error-logfile -
