# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

LingosAI is an AI English-tutoring platform. A learner follows a multi-week curriculum of daily lessons; each lesson is a chat-driven session of teaching → task → evaluation → feedback. The backend uses LLMs (via LangChain/LangGraph) to generate tasks, evaluate answers, and produce personalized feedback, with RAG-backed "feedback memory" so the tutor remembers a learner's recurring weaknesses. Scoring is a **separate deterministic (no-LLM) engine** that turns graded activities into per-sub-skill points and a dashboard score.

- **Backend**: FastAPI + SQLAlchemy 2.0 + PostgreSQL, package-managed by `uv` (Python ≥3.11). AI via LangChain/LangGraph + OpenAI; Pinecone for vectors; Azure Speech for pronunciation.
- **Frontend**: Next.js 16 (App Router) + React 19 + TypeScript, TanStack Query for server state, Zustand for client state, Tailwind v4.
- **Infra**: Docker Compose runs Postgres + Redis only (the apps run on the host, not in containers).

## Commands

### Backend (run from `backend/`)
```bash
uv sync                                   # install deps
uv run alembic upgrade head               # apply migrations
uv run uvicorn app.main:app --reload      # API at http://127.0.0.1:8000 (docs at /docs)
uv run pytest                             # all tests (CI uses this)
uv run pytest tests/unit -q               # fast unit suite
uv run pytest tests/integration -q        # integration suite
uv run pytest tests/unit/sessions/test_session_planner.py            # single file
uv run pytest tests/unit/sessions/test_session_planner.py::test_name # single test
uv run ruff check app tests               # lint  (CI also runs `ruff format --check`)
uv run ruff format app tests              # auto-format before pushing (format-check is blocking)
uv run mypy app                           # type-check (app/ is mypy-clean; blocking in CI)
uv run python scripts/export_openapi.py   # regenerate openapi.json after route changes (drift is gated)
uv run alembic revision --autogenerate -m "msg"  # new migration
```
Tests live under `tests/unit/` and `tests/integration/` (the old flat `tests/test_*.py` layout is gone). On this machine, prefer `uv run python -m pytest …` — a broken global `pytest` can shadow `uv run pytest`. From the repo root, `./scripts/dev-backend.sh` is a shortcut for the uvicorn command (`chmod +x` once).

### Frontend (run from `frontend/`)
```bash
npm run dev            # dev server at http://localhost:3000
npm run build
npm run lint
npm test               # Vitest unit + integration suite (`vitest run`)
npm run test:coverage  # Vitest + coverage (the gate CI runs)
npx tsc --noEmit       # type-check (blocking in CI)
```

### Infra
```bash
docker compose up -d   # Postgres + Redis (ports come from .env)
```

## CI/CD, deployment & DCO

Every change ships through **branch → PR → green required checks → squash-merge to `main`**. Never push to `main` directly. The former AWS deployment remains manual recovery-only. Azure deployment automation is authored but every cloud job is skipped unless the non-secret repository variable `AZURE_AUTOMATION_ENABLED` has the exact value `true`; keep it `false` until the separately approved Azure resources, OIDC federation/RBAC, protected GitHub Environment, repository variables, VM host contract, and authorization to begin the production rehearsal are complete. A matching push to `main` still runs the Azure pre-deploy test job, but cannot authenticate to Azure or request Environment approval while the activation variable is disabled. Azure authentication never uses a client secret. Vercel may still deploy the frontend independently from `main` according to its project configuration.

### GitHub Actions (`.github/workflows/`)
PR-triggered jobs run on **every** PR with no `paths` filter — that's deliberate: each is a *required* status check under branch protection, and a path-filtered required check never reports on an unrelated PR and wedges the merge forever. The same jobs are `paths`-filtered on push to `main`.

| Workflow | Jobs (required check names) | Gate |
| --- | --- | --- |
| `backend.yml` | `lint`, `types`, `unit`, `integration`, `migrations`, `coverage` | ruff check **+ `ruff format --check`**; mypy clean; unit + integration; full Alembic replay on a real Postgres 16; coverage `--cov-fail-under=73` (ratchet up, never down) |
| `frontend.yml` | `ci` | ESLint, `tsc --noEmit`, Vitest + coverage, `next build` |
| `contract.yml` | `openapi-drift` | regenerates `backend/openapi.json` and fails if it drifted — run `uv run python scripts/export_openapi.py` and commit after changing routes |
| `docker.yml` | `docker-build` | backend image builds + Trivy HIGH/CRITICAL CVE scan (repo-root `.trivyignore` is the justified allowlist) |
| `backend-curriculum.yml` | `curriculum-seed-smoke` | path-filtered pre-deploy guard: both 24w/48w calendars import + seed/composer/teacher tests |
| `deploy.yml` | — (manual recovery only) | frozen AWS recovery workflow; never runs on push |
| `azure-deploy.yml` | `test backend before deployment`, `push and deploy immutable digest` | backend gates → OIDC → ACR commit tag → deploy resolved digest through VM Run Command; protected `production` approval and live window required |
| `azure-wake.yml` | — (manual only) | protected, bounded 1–24 hour start: live-window tag → PostgreSQL `Ready` → VM running → public health checks; failure returns the environment to cold state |
| `azure-sleep.yml` | — (manual only) | protected, idempotent drain → VM deallocate/verify → PostgreSQL stop/verify |
| `azure-sleep-watchdog.yml` | — (scheduled) | hourly enforcement of expired live windows, including PostgreSQL's forced seven-day restart |

Two more required checks come from GitHub Apps, not Actions: **`DCO`** (sign-off, see below) and **`Vercel`** (frontend preview/prod deploy). `migrations` exists because the unit/integration suites use SQLite `create_all` and never exercise the real migration graph — never delete it.

### Frozen AWS recovery deploy (`deploy.yml`)
The workflow has no `push` trigger, so pushes and merges to `main` cannot invoke AWS deployment. It is retained as readable recovery history and can run only through a deliberately confirmed `workflow_dispatch` targeting the `staging` or `production` GitHub Environment. Its former backend pipeline remains unchanged: OIDC → build and push to ECR under the immutable `git-<sha>` tag → one-off migrations → idempotent challenge seeds → ECS Fargate rolling update → readiness smoke test with service auto-rollback. Migrations remain forward-only and are not reverted. Do not manually dispatch it without the owner's explicit recovery approval. This AWS workflow never invokes the isolated Azure automation. Vercel remains a separate frontend integration.

### Azure production automation

The four Azure workflows and their host scripts implement PR 7 only. All Azure cloud jobs require `AZURE_AUTOMATION_ENABLED == 'true'`; any missing or different value leaves them skipped. Deployment is restricted to `main`, uses the protected `production` GitHub Environment, requires an already-active live window, pushes the backend to ACR under `git-<full-sha>`, and passes only the resolved `sha256` digest to the VM. Application rollback restores the prior digest; Alembic migrations remain forward-only. Wake defaults to six hours and rejects values outside 1–24. Sleep always deallocates the VM before stopping PostgreSQL. The hourly watchdog does not use the reviewer-gated Environment because an unattended stop cannot wait for approval; its OIDC trust must instead be restricted to the default branch. See `docs/AZURE_CICD_RUNBOOK.md` for required human-owned setup and the VM host contract. Do not enable or run any Azure workflow until those gates are reviewed and complete.

### Frontend API availability

Vercel remains the Phase 1 frontend host while the Azure API is operated on demand. `ApiAvailabilityBanner` probes only `/health/ready`: 2xx is live, 503 is warming, a network failure is offline/unreachable, browser offline is a separate state, and any other HTTP response is an unexpected service error. Do not infer sleep state from ordinary feature requests or Axios errors. The banner keeps public pages usable, retries unavailable states on a bounded interval only while the tab is visible, and allows a manual retry.

### DCO sign-off — required on every commit
A required `DCO` check (the probot DCO app) blocks any PR whose commits lack a `Signed-off-by:` trailer whose name/email **match the commit author**. Always commit with sign-off:
```bash
git commit -s -m "feat(scope): summary"     # -s appends the Signed-off-by trailer
git rebase --signoff main                   # retro-fix a branch that forgot it
```

```
All commits and pull requests must be authored only by me using my GitHub identity:

Orbin Sunny
Email: 91816511+orbin123@users.noreply.github.com

Do not include `Co-Authored-By` or any AI/tool attribution (Claude, Cursor, ChatGPT, Copilot, etc.). The only trailer permitted is my own `Signed-off-by: Orbin Sunny <91816511+orbin123@users.noreply.github.com>`, which the required DCO check needs and is **not** tool attribution. Remove any automatically added attribution before committing or creating a PR.
```
Use the conventional-commit style the history follows (`feat(scope): …`, `fix(scope): …`, `chore(deps): …`). Fill in `.github/pull_request_template.md` (tests, DB-migration, new-env-var, OpenAPI-snapshot, and security-note checklist) — it mirrors the gates above.

## Environment & config

- All backend config flows through `app/core/config.py` (`pydantic-settings`). It reads the **single repo-root `.env`** (`env_file="../.env"`, relative to `backend/`). Missing required vars crash the app at startup — that's intentional. Copy `.env.example` to `.env` to start.
- `settings.database_url` is given as `postgresql://…`; `app/core/database.py` rewrites it to `postgresql+psycopg://…` (psycopg 3). Don't hardcode the driver in the URL.
- Tests don't need a real `.env`: `tests/conftest.py` sets dummy env vars and a SQLite `DATABASE_URL` before settings load.
- The standalone `backend/check_*.py`, `delete_bugged_session.py`, and repo-root `test_db.py` scripts are ad-hoc DB debugging tools with hardcoded local connection strings — not part of the app. The root `backup*.sql` files are local DB dumps.

## Backend architecture

### Module layering
Each feature lives in `app/modules/<name>/` and follows a strict layered pattern. Respect it when adding code:

```
routes.py / router.py  → HTTP/WS endpoints (thin; depend on get_db, get_current_user)
service.py             → business logic, owns transaction commits at logical boundaries
repository.py          → all DB queries (the only layer that touches the ORM session directly)
models.py              → SQLAlchemy ORM models for this module
schemas.py             → Pydantic request/response models
exceptions.py          → domain exceptions (routes translate these to HTTPException)
```

Not every module has all layers (e.g. `responses/` is route-only; `skills/` is models + repository). Routes are registered in `app/main.py` via `include_router`. Services receive collaborators (evaluators, feedback generators, repositories) by injection so the LLM-backed implementations can be swapped for stubs in tests.

The modules: `auth`, `admin`, `sessions`, `learning_session`, `curriculum`, `challenges`, `diagnosis`, `progress`, `streaks`, `preferences`, `subscriptions`, `responses`, `skills`, `personalization`, `feedback_memory`, plus the newer `feedback` (user-facing product feedback/ratings — distinct from the RAG `feedback_memory`), `reviews` (testimonials), `blog` (a small CMS with public + admin routers, media under `blog/_media`), and `contact` (contact-form submissions; route + service, no models). All routers are wired in `app/main.py`.

### Model registry — important
`app/models.py` imports **every** ORM model from every module. This populates SQLAlchemy's registry so cross-module `relationship()` string references resolve and Alembic can discover all tables via `Base.metadata`. **When you add a new model, add it to `app/models.py`** or migrations and relationships will silently break. `Base` is defined in `app/core/database.py`; shared column mixins (`IDMixin`, `CreatedAtMixin`, `TimestampMixin`) live in `app/core/mixins.py`.

### The session domain (the core of the app)
There are two related but distinct session concepts — don't conflate them:

- **`app/modules/sessions/`** — the V2 "daily session" engine. `SessionService` owns the start → next-activity → submit → complete → scorecard lifecycle and **all** evaluation/feedback DB writes. It composes injected `Evaluator` and `FeedbackGenerator` (LLM-backed in prod, stubs in tests). `planner.py` decides activity order; `scoring_writer.py` pushes the final scorecard into the learner's `SkillPoints` (replay-guarded: only the first attempt earns points).
- **`app/modules/learning_session/`** — the chat/WebSocket layer that drives a session turn-by-turn for the UI. Its `orchestrator.py` is deliberately "dumb": it does **not** decide lesson flow. The curriculum blueprint + V2 session rows already determine which activities exist and in what order; the orchestrator only turns that deterministic data into structured WebSocket events (`learning_session.event.v1`). It also exposes a REST router for hydrating chat state on reload.

### Archetype contracts — the runtime backbone
`app/modules/sessions/contracts/registry.py` is the **single source of truth** tying each activity *archetype* to its task widget, the agents that run it, the render widgets, and the strict Pydantic I/O schemas (`agent_inputs.py`, `task_payloads.py`, `evaluation.py`, `feedback.py`, `projection.py`). The curriculum blueprint only references an `archetype_id`; the registry resolves everything else. It composes `app.scoring.ARCHETYPE_REGISTRY` rather than duplicating it and **fails at import time** if any registered archetype lacks a contract.

- Add a new *day* → write blueprint data only (no code in the registry changes).
- Add a new *kind* of activity → add one archetype to the scoring registry and one contract row here; it's then reusable forever.

### Scoring engine (`app/scoring/`) — deterministic, no LLM
Pure functions implementing the scoring math: **no DB calls, no I/O, no randomness — same inputs → same outputs.** `archetypes.py` holds the `ARCHETYPE_REGISTRY` (each archetype's UI widget, supported themes, CEFR range, sub-skill `weight_map`, and rubric); `engine.py` buckets raw scores into tiers, computes per-activity rewards (24w/48w course variants), distributes them across sub-skills, aggregates a session, caps totals, and converts to a 0–10 dashboard score; `constants.py` holds the locked numerical constants. The rationale for the numbers lives in `backend/RESTRUCTURE_DECISIONS.md`. Sessions/progress modules consume this engine — don't reimplement the math elsewhere.

### Task schemas (`app/tasks/schemas/`)
Typed Pydantic task-payload schemas (`task_schemas.py`) and the LLM structured-output schemas (`llm_output_schemas.py`) used to constrain generation. These are the validated contracts for generated task content (fill-in-blanks, MCQ, dialogue, etc.).

### Curriculum: file-authored vs DB-seeded
Curriculum can come from **authored Python dataclasses** in three level-band files (`source_L_A1A2.py`, `source_L_B1B2.py`, `source_L_C1C2.py`, each with 8 source weeks), composed at runtime by `composer.py` into 24w/48w calendar weeks (`source_24w.py` / `source_48w.py` are thin re-exports). Days are keyed by `(course_length, week_number, day_index 0..6)` or `day_24_WW_DD` / `day_48_WW_DD`. `file_source.py` is the bridge: when a day is file-authored, its archetype order, task specs, teacher instructions, and eval/feedback overrides **take precedence** over the DB. Authored teacher behaviour is smuggled through the existing `teacher_instructions` column under the `SCRIPTED_PLAN_KEY` (`__scripted_plan`) sentinel. `blueprint_adapter.py` / `adapters.py` translate authored data into the runtime blueprint.

### Streaks coupling
`app/modules/streaks/service.py` has two entry points: `record_in_same_tx` is called from `SessionService.submit_activity` **after** an activity is evaluated but **before** the outer commit (it flushes so the unique constraint catches double-fires, but does NOT commit — the caller owns the transaction); `get_streak_data` is a pure read that builds the 91-day activity grid for the dashboard. The MVP freeze rule is strict (every missed day resets) but configurable via constants, no migration needed.

### Progress & points
`app/modules/progress/` owns `SkillPoints` (per-sub-skill running totals), `SkillPointsLog`, and `ProgressLog`. The diagnosis flow seeds points only (see `test_diagnosis_seeds_points_only`). The `skills/` module holds the canonical `Skill` rows.

### AI layer (`app/ai/`)
- Each AI *capability* is a subpackage with the same shape: `interface.py` (abstract contract) + a concrete client (`openai_client.py`, `azure_client.py`) + `exceptions.py`, plus a `get_default_*_service()` factory. Capabilities: `llm`, `tts`, `stt`, `pronunciation` (Azure), `imagegen`, `embeddings`.
- `app/ai/agents/` holds the prompt-driven agents (`teacher`, `evaluator`, `feedback`, `planner`, `task_generator`, `personalization`, `relevance_classifier`). The IELTS-challenge agents live with their feature, under `app/modules/challenges/ielts_sprint/`, and load prompts from `app/ai/agents/prompts/ielts/`. Prompts are Markdown files loaded by `prompt_loader.py` via slash-delimited names (e.g. `ielts/generator`) with `{{variable}}` placeholders rendered by `render_prompt_template` (does not interpret JSON braces).
- `app/ai/sessions/` holds the **LLM-backed session collaborators** the `SessionService` injects in prod: `llm_evaluator.py`, `llm_feedback.py`, `llm_task_generator.py`, `speaking_eval.py`, wired by `factory.py` (`build_default_agents`, `build_rag_services`). Tests swap these for stubs.
- `app/ai/graphs/` is the LangGraph definition. The compiled graph documents the flow and is used in tests; the live chat flow is driven from the WebSocket layer, and DB writes are owned by `SessionService.submit_activity`, not by graph nodes.
- LangSmith tracing is on by default (`LANGCHAIN_TRACING_V2=True`).

### Generated media
TTS audio and generated images are written to disk by `LocalBlobStorage` (`app/ai/storage/`) under `app/ai/{tts,stt,imagegen,pronunciation}/_cache` and served directly via FastAPI `StaticFiles` mounts (`/audio`, `/images`). Cache dirs are configurable in `config.py`. `POST /responses/transcribe-audio` (the `responses/` module) is what the speaking widgets post recordings to — it returns a transcript + audio URL that the evaluator/feedback grade on submit. In prod these would move to object storage + CDN.

### Auth & admin
- JWT bearer auth. `app/modules/auth/dependencies.py` provides `get_current_user` (decodes JWT `sub`, loads the user). Google OAuth is supported; `redirect_slashes=False` in `main.py` is deliberate to avoid a 307 on the OAuth callback.
- Role-based access: `learner`, `admin`, `super_admin` backed by `Role`/`Permission`/`RolePermission`/`UserRole`. Super-admins manage roles and subscriptions; normal admins get scoped reads (e.g. `payments.read`).
- `AdminRateLimitMiddleware` (`app/core/rate_limit.py`) rate-limits admin/login routes.
- Admin mutations are recorded to audit logs (`app/modules/admin/audit_service.py`). The `subscriptions/` module (billing) stores **only provider IDs** (masked in admin views) — never raw payment data.

## Frontend architecture

- **App Router** under `src/app/`. Route groups like `(auth)` and dynamic segments like `sessions/[sessionId]` are in use. Top-level pages include `dashboard`, `courses`, `sessions`, `task`, `challenges`, `diagnosis`, `choose-start`, `payment`, `stats`, `profile`, `settings`, plus marketing/legal pages (`about`, `features`, `pricing`, `how-it-works`, `blog`, `contact`, `privacy`, `terms`). Admin pages live under `src/app/admin/`. Sentry is wired via `instrumentation*.ts` + `sentry.*.config.ts`.
- **API access**: one shared axios instance in `src/lib/api.ts`. It auto-attaches the JWT from `localStorage` and, on a `401` from a non-auth endpoint, clears the token and redirects to `/login`. Per-domain wrappers (`sessions-api.ts`, `auth-api.ts`, `challenges-api.ts`, `progress-api.ts`, `streak-api.ts`, `preferences-api.ts`, `subscriptions-api.ts`, `diagnosis-api.ts`, `tasks-api.ts`, `admin-api.ts`, …) build on it — add new calls to the matching `*-api.ts`, don't create new axios instances. Base URL comes from `NEXT_PUBLIC_API_URL` (defaults to `http://localhost:8000`).
- **Server state** via TanStack Query (`src/providers/query-provider.tsx`); domain hooks in `src/hooks/` (e.g. `useSessionsFlow`, `useNextTask`, `useSubmitResponse`, `useDiagnosis`, `useStreakDisplay`). **Client state** via Zustand stores in `src/store/` (`authStore`, `sessionStore`, `taskStore`, `diagnosisStore`, `streakDemoStore`).
- **Chat UI** is component-driven: `src/components/chat/` (`ChatUI.tsx`, `ChatChrome.tsx`, `orchestrator.tsx`) with `tasks/`, `feedback/`, `teaching/`, `evaluation/` subfolders and per-widget renderers. `runtimeMapping.tsx` / `runtimeReviewMapping.tsx` / `contractTaskAdapter.ts` map backend payloads to widgets. Backend widget keys are normalized to stable snake_case by `app/modules/sessions/widget_mapping.py` — keep that mapping in sync when adding task/widget types on either side.
- Other component areas: `src/components/{admin,auth,dashboard,sessions,streak,layout,ui}/`.
- `@/*` path alias maps to `src/*` (tsconfig). TypeScript `strict` is on.

## Conventions

- Backend: keep DB access in repositories, business logic + commits in services, and routes thin. Raise domain exceptions; translate to HTTP at the route boundary.
- New ORM model → register it in `app/models.py` and generate an Alembic migration.
- New activity *kind* → add an archetype to `app/scoring/archetypes.py` **and** a contract row in `app/modules/sessions/contracts/registry.py` (it will fail at import if you add one without the other).
- New task/widget type → update both the backend widget mapping and the corresponding `src/components/chat/` renderer.
- Scoring math is deterministic and lives only in `app/scoring/` — consume it, don't duplicate it. See `backend/RESTRUCTURE_DECISIONS.md` for the locked constants' rationale.
- Changed backend routes → regenerate `backend/openapi.json` (`uv run python scripts/export_openapi.py`) and commit it, or the `openapi-drift` check fails.
- **Ship via PR, never push to `main`.** Backend deployment is frozen during the Azure transition: `deploy.yml` is manual AWS recovery-only, and no Azure deployment exists yet. Vercel may still deploy the frontend independently. Get the required checks green first, run `ruff format` + `mypy` + the relevant tests locally before pushing, and keep migrations forward-only.
- **Sign off every commit** (`git commit -s`) so the required `DCO` check passes — the trailer's name/email must match the author. Commits and PRs are authored solely by me (Orbin Sunny); the only trailer is my own `Signed-off-by:` — never add `Co-Authored-By` or any AI/agent attribution.
