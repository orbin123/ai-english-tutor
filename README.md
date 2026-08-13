<div align="center">

# 🎓 Lingos AI

### AI-Powered Personal English Learning Coach

A strict, intelligent coach that diagnoses your weaknesses, generates personalized tasks, and gives precise corrective feedback — so non-native speakers can build career-ready English communication skills.

[![Website](https://img.shields.io/badge/website-lingosai.com-2563eb)](https://www.lingosai.com)
[![Backend](https://img.shields.io/badge/backend-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Frontend](https://img.shields.io/badge/frontend-Next.js%2016-000000?logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![Python](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![TypeScript](https://img.shields.io/badge/typescript-5-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](#-license)

</div>

---


https://github.com/user-attachments/assets/3f9b4cfb-8236-492d-94a4-fc720819f812



## 📋 Table of Contents

- [Overview](#-overview)
- [Why Lingos AI](#-why-lingos-ai)
- [Core Features](#-core-features)
- [The Learning Model](#-the-learning-model)
- [Tech Stack](#-tech-stack)
- [Architecture](#-architecture)
- [Data Model](#-data-model)
- [Project Structure](#-project-structure)
- [Local Development](#-local-development)
- [Running with Docker](#-running-with-docker)
- [Deployment](#-deployment)
- [Development Workflow](#-development-workflow)
- [Roadmap](#-roadmap)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🌍 Overview

**Lingos AI** is an AI-powered English-tutoring platform for non-native speakers who want to improve **career-focused** communication. A learner follows a multi-week curriculum of daily lessons; each lesson is a chat-driven session that flows **teaching → task → evaluation → feedback**.

The platform is built around three ideas that distinguish it from flashcard-style apps:

1. **Diagnosis first.** Before generating work, Lingos AI assesses the learner across seven distinct skill dimensions and finds where they actually struggle.
2. **Adaptive, personalized tasks.** An agent-based AI layer generates writing, speaking, reading, and listening activities tuned to the learner's level, goals, and recurring weaknesses.
3. **Precise, actionable feedback.** Corrections are specific — what was wrong, why, and how to fix it — and a RAG-backed *feedback memory* lets the tutor remember a learner's recurring mistakes across sessions.

Scoring is handled by a **separate deterministic engine** (no LLM) that turns graded activities into per-sub-skill points and a 0–10 dashboard score, so progress is reproducible and explainable.

---

## 💡 Why Lingos AI

| Traditional language apps | Lingos AI |
| --- | --- |
| Generic, one-size-fits-all lessons | Tasks generated from your diagnosed weaknesses |
| Gamified streaks over real mastery | Career-focused communication outcomes |
| Vague "Correct / Incorrect" feedback | Specific, actionable corrections with reasoning |
| Forgets your mistakes between sessions | RAG-backed memory of recurring weaknesses |
| Opaque scoring | Deterministic, reproducible, per-skill scoring |

---

## ✨ Core Features

### 🎯 Personalized Learning
- **Learner profiling** — captures goals, level (CEFR), and context
- **Skill assessment** — a diagnosis flow seeds a baseline across all skills
- **Weakness detection** — identifies the sub-skills that need the most work

### 🤖 AI Task Generation
- ✍️ **Writing tasks** — fill-in-the-blank, rewriting, structured composition
- 🗣️ **Speaking tasks** — spoken responses graded for pronunciation & fluency
- 📖 **Reading tasks** — comprehension and word-choice exercises
- 🎧 **Listening tasks** — audio-driven comprehension activities

### 📝 Feedback Engine
- **Grammar correction** with explanations, not just flags
- **Fluency evaluation** for spontaneity and natural flow
- **Vocabulary analysis** for precision and word choice
- **Personalized recommendations** that target recurring weaknesses

### 📊 Progress Tracking
- **Skill scores** — per-sub-skill running totals and a 0–10 dashboard score
- **Learning history** — every graded activity is logged and replay-guarded
- **Performance analytics** — streaks, period averages, and trend insights

### ⚡ Real-Time Experience
- **Streaming AI responses** over WebSockets
- **Chat-based learning interface** that drives each lesson turn-by-turn

---

## 🧠 The Learning Model

Lingos AI evaluates and trains every learner across **seven core skills**. Each generated task maps to a weighted set of these sub-skills, and the scoring engine distributes points accordingly.

| # | Skill | What it measures |
| :-: | --- | --- |
| 1 | **Grammar & Sentence Construction** | Correctness and structure of sentences |
| 2 | **Vocabulary & Word Choice** | Range, precision, and appropriateness of words |
| 3 | **Pronunciation & Speech Clarity** | Intelligibility and accuracy of spoken sounds |
| 4 | **Fluency & Spontaneity** | Smoothness and ease of unscripted speech |
| 5 | **Thought Organization & Expression** | Logical flow and clarity of ideas |
| 6 | **Listening & Comprehension** | Understanding spoken English in context |
| 7 | **Tone & Social Awareness** | Register, politeness, and situational fit |

---

## 🛠 Tech Stack

| Layer | Technologies |
| --- | --- |
| **Frontend** | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS v4, TanStack Query, Zustand |
| **Backend** | FastAPI, Python 3.11+, SQLAlchemy 2.0, Alembic, managed by `uv` |
| **AI Layer** | OpenAI, LangChain & LangGraph, agent-based orchestration, provider-abstracted LLM/TTS/STT interfaces |
| **Data** | PostgreSQL, Pinecone (vector DB for feedback memory) |
| **Speech** | Azure Speech (pronunciation assessment), OpenAI TTS/STT |
| **Infrastructure** | Docker Compose, AWS, Vercel |
| **Supporting Services** | Redis, Celery, LangSmith (tracing), Sentry (monitoring), Razorpay (billing), Resend (email) |

> **Note on the vector DB:** the codebase targets **Pinecone** in production. The architecture diagram lists "Vector DB" generically — a FAISS adapter can be swapped in via the embeddings interface for fully local development.

---

## 🏗 Architecture

The AI layer is **agent-based**: each capability (LLM, TTS, STT, pronunciation, embeddings, image-gen) implements a shared interface, and prompt-driven agents (teacher, evaluator, feedback, planner, task-generator) compose them. Critically, **lesson flow and scoring are deterministic** — the LLM generates and grades content, but it does not decide curriculum order, and it never computes the final score.

```mermaid
flowchart TD
    User([👤 Learner])

    subgraph Client["🖥️ Client"]
        Web["Next.js Frontend<br/>(React 19 · TS · Tailwind)"]
    end

    subgraph Server["⚙️ Application Layer"]
        API["FastAPI Backend<br/>(REST + WebSocket)"]
        Orchestrator["AI Orchestrator<br/>(LangGraph · agents)"]
    end

    subgraph AI["🤖 AI Providers"]
        LLM["LLM Providers<br/>(OpenAI)"]
        Speech["Azure Speech<br/>(pronunciation · TTS/STT)"]
    end

    subgraph Data["💾 Data Layer"]
        PG[("PostgreSQL")]
        Vector[("Vector DB<br/>(Pinecone)")]
    end

    subgraph Support["🔧 Supporting Services"]
        Redis[("Redis")]
        Celery["Celery Workers"]
        Sentry["Sentry"]
        LangSmith["LangSmith"]
    end

    User --> Web --> API
    API --> Orchestrator
    Orchestrator --> LLM
    Orchestrator --> Speech
    Orchestrator --> Vector
    API --> PG
    API --> Redis
    Redis --> Celery
    Orchestrator -. traces .-> LangSmith
    API -. errors .-> Sentry
    Web -. errors .-> Sentry
```

**Request flow at a glance**

| Stage | Responsibility |
| --- | --- |
| **Frontend** | Renders the chat-based lesson UI; streams events over WebSocket; manages server/client state |
| **FastAPI Backend** | Auth, session lifecycle, DB writes, transaction boundaries; thin routes → services → repositories |
| **AI Orchestrator** | Turns deterministic session data into structured events; runs teacher/evaluator/feedback agents |
| **LLM Providers** | Generate task content, evaluate answers, and draft feedback (behind a provider abstraction) |
| **Vector DB** | Stores and retrieves "feedback memory" embeddings for RAG-personalized coaching |
| **Scoring Engine** | Pure, deterministic math — converts graded activities into per-skill points (no LLM, no I/O) |

---

## 🗄 Data Model

A concise, high-level view of the core entities — not an exhaustive schema.

| Entity | Purpose |
| --- | --- |
| **Users** | Accounts, auth identity, and roles (`learner`, `admin`, `super_admin`) |
| **Profiles** | Learner goals, CEFR level, and personalization context |
| **Skills** | The canonical seven skills and their sub-skills |
| **Tasks** | Generated activities (writing, speaking, reading, listening) and their payloads |
| **Responses** | Learner submissions, including transcribed audio for speaking tasks |
| **Feedback** | Per-response corrections, scores, and recommendations |
| **Progress** | Per-sub-skill running totals, point logs, streaks, and the dashboard score |

```mermaid
erDiagram
    USERS ||--|| PROFILES : has
    USERS ||--o{ RESPONSES : submits
    USERS ||--o{ PROGRESS : tracks
    PROFILES }o--o{ SKILLS : "targets"
    TASKS ||--o{ RESPONSES : "answered by"
    SKILLS ||--o{ TASKS : "exercises"
    RESPONSES ||--|| FEEDBACK : "graded into"
    FEEDBACK }o--|| SKILLS : "scores"
    PROGRESS }o--|| SKILLS : "aggregates"
```

---

## 📂 Project Structure

The repository is a two-app layout — a Python backend and a Next.js frontend — sharing a single repo-root `.env`.

```text
lingos-ai/
├── backend/                  # FastAPI application (managed by uv)
│   ├── app/
│   │   ├── main.py           # App entrypoint; registers all routers
│   │   ├── models.py         # Imports every ORM model (SQLAlchemy registry)
│   │   ├── core/             # Config, database, mixins, rate limiting
│   │   ├── modules/          # Feature modules (layered: routes→service→repository)
│   │   │   ├── auth/         # JWT + Google OAuth
│   │   │   ├── sessions/     # V2 daily-session engine + scoring writer
│   │   │   ├── learning_session/  # Chat/WebSocket lesson layer
│   │   │   ├── curriculum/   # Multi-week lesson blueprints
│   │   │   ├── diagnosis/    # Skill assessment & weakness detection
│   │   │   ├── progress/     # Skill points, logs, dashboard score
│   │   │   ├── feedback_memory/   # RAG memory of recurring weaknesses
│   │   │   ├── streaks/ · challenges/ · subscriptions/ · admin/ · ...
│   │   ├── ai/               # The AI layer
│   │   │   ├── agents/       # Prompt-driven agents (teacher, evaluator, ...)
│   │   │   ├── graphs/       # LangGraph definitions
│   │   │   ├── sessions/     # LLM-backed session collaborators
│   │   │   ├── llm/ · tts/ · stt/ · pronunciation/ · embeddings/  # capabilities
│   │   │   └── storage/      # Local blob storage for generated media
│   │   ├── scoring/          # Deterministic scoring engine (no LLM)
│   │   └── tasks/            # Typed task & LLM-output schemas
│   ├── alembic/              # Database migrations
│   ├── tests/                # pytest suite
│   └── pyproject.toml
│
├── frontend/                 # Next.js 16 application
│   ├── src/
│   │   ├── app/              # App Router pages (dashboard, sessions, task, ...)
│   │   ├── components/       # UI, including the chat/ lesson renderers
│   │   ├── hooks/            # TanStack Query domain hooks
│   │   ├── store/            # Zustand client-state stores
│   │   ├── lib/              # Shared axios instance + per-domain API wrappers
│   │   └── providers/        # React providers (query client, etc.)
│   └── package.json
│
├── docs/                     # Architecture, plans, and operational docs
├── scripts/                  # Dev helper scripts (e.g. dev-backend.sh)
├── .github/workflows/        # CI pipelines (backend, frontend, contracts)
├── docker-compose.yml        # Postgres + Redis for local dev
└── .env.example              # Copy to .env and fill in
```

---

## 🚀 Local Development

### Prerequisites

| Tool | Version | Notes |
| --- | --- | --- |
| **Node.js** | 20+ | Frontend runtime |
| **Python** | 3.11+ | Backend runtime |
| **uv** | latest | Python package manager ([install](https://docs.astral.sh/uv/)) |
| **Docker** | latest | Runs Postgres + Redis locally |
| **PostgreSQL** | 16 | Provided via Docker Compose |
| **Redis** | 7 | Provided via Docker Compose |

### 1. Clone the repository

```bash
git clone https://github.com/your-org/lingos-ai.git
cd lingos-ai
```

### 2. Configure environment variables

Copy the example file and fill in your values. The backend reads a **single repo-root `.env`**.

```bash
cp .env.example .env
```

Minimum keys to get started:

```env
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/lingos

# Auth
JWT_SECRET=your-long-random-secret

# AI providers
OPENAI_API_KEY=sk-...

# Observability (optional locally)
LANGCHAIN_API_KEY=ls-...      # LangSmith tracing
SENTRY_DSN=                   # leave blank to disable
```

> The full set of supported variables (Azure Speech, Razorpay, Resend email, OTP, Google OAuth, rate limits, etc.) is documented in [`.env.example`](.env.example).

The local and zero-cost AI rate-limiter configuration is process-local and
does not require Redis. Keep `AI_RATE_LIMIT_BACKEND=memory` with exactly one
backend worker. Multi-worker deployments must select
`AI_RATE_LIMIT_BACKEND=redis` and configure `REDIS_URL` so every worker shares
the same rate-limit buckets.

### 3. Start infrastructure (Postgres + Redis)

```bash
docker compose up -d
```

### 4. Set up and run the backend

```bash
cd backend
uv sync                                       # install dependencies
uv run alembic upgrade head                   # apply migrations
uv run python -m scripts.seed_curriculum      # seed curriculum (idempotent, required)
uv run uvicorn app.main:app --reload          # API → http://127.0.0.1:8000  (docs at /docs)
```

> **The curriculum seed is required on every fresh environment.** Chat / today-plan APIs return `404` until both the 24-week and 48-week calendars exist. The script is safe to re-run.

### 5. Set up and run the frontend

```bash
cd frontend
npm install
npm run dev                                   # app → http://localhost:3000
```

### 6. Access the application

Open **http://localhost:3000** in your browser. The frontend talks to the API at `http://localhost:8000` (override with `NEXT_PUBLIC_API_URL`).

---

## 🐳 Running with Docker

The bundled `docker-compose.yml` runs the **stateful services** (Postgres + Redis); the apps run on the host for fast hot-reload.

```bash
docker compose up --build
```

This starts:

- **`coach_postgres`** — PostgreSQL 16, with a healthcheck and a named volume for persistence
- **`coach_redis`** — optional Redis 7 for shared AI rate-limit buckets in a
  multi-worker configuration

Ports are read from your `.env` (`POSTGRES_PORT`, `REDIS_PORT`). Stop everything with `docker compose down` (add `-v` to also drop the data volumes).

---

## ☁️ Deployment

| Concern | Platform |
| --- | --- |
| **Frontend** | Vercel (Next.js, edge-cached, preview deployments per PR) |
| **Backend** | AWS (containerized FastAPI behind a load balancer) |
| **Database** | PostgreSQL (managed, e.g. AWS RDS) |
| **Vector DB** | Pinecone (managed) |
| **Object Storage** | AWS S3 (generated audio & images; local disk in dev) |
| **Background Jobs** | Celery workers backed by Redis |
| **Monitoring** | Sentry (frontend + backend error tracking) |
| **Observability** | LangSmith (LLM tracing & evaluation) |
| **Domain** | [www.lingosai.com](https://www.lingosai.com) |

```mermaid
flowchart LR
    User([👤 User]) --> CDN["Vercel<br/>(Next.js Frontend)"]

    CDN --> ALB["AWS Load Balancer"]
    ALB --> API["FastAPI<br/>(containers on AWS)"]

    API --> RDS[("PostgreSQL<br/>(RDS)")]
    API --> Pinecone[("Pinecone<br/>(Vector DB)")]
    API --> Redis[("Redis")]
    Redis --> Workers["Celery Workers"]
    API --> S3[("AWS S3<br/>(media)")]
    API --> OpenAI["OpenAI"]

    API -. errors .-> Sentry["Sentry"]
    CDN -. errors .-> Sentry
    API -. traces .-> LangSmith["LangSmith"]
```

---

## 🔄 Development Workflow

CI runs on every pull request via GitHub Actions (`backend`, `frontend`, and `contract` workflows).

```bash
# 1. Create a feature branch off main
git checkout -b feature/your-change

# 2. Make changes, then run the relevant checks locally

# Backend
cd backend
uv run ruff check .          # lint
uv run mypy app              # type-check
uv run pytest                # tests

# Frontend
cd frontend
npm run lint
npm run test

# 3. Commit and push
git add .
git commit -m "feat: describe your change"
git push -u origin feature/your-change

# 4. Open a pull request → CI checks run → review → merge
```

| Step | What happens |
| :-: | --- |
| 1 | Branch from `main` |
| 2 | Implement the change |
| 3 | Run lint, type-check, and tests locally |
| 4 | Open a PR |
| 5 | CI runs (lint · types · tests · contract checks) |
| 6 | Review approval → merge to `main` |

---

## 🗺 Roadmap

- [x] Diagnosis flow & seven-skill scoring engine
- [x] Daily-session engine (teaching → task → evaluation → feedback)
- [x] RAG-backed feedback memory
- [x] Streaming chat lesson UI over WebSocket
- [x] Admin, billing, and role-based access control
- [ ] Expanded speaking & listening activity archetypes
- [ ] Mobile applications (iOS / Android)
- [ ] Multi-language UI localization
- [ ] Group / classroom mode for cohorts
- [ ] Public API for third-party integrations

---

## 🤝 Contributing

Contributions are welcome! To keep the codebase consistent:

1. **Open an issue** describing the change before large PRs.
2. **Branch from `main`** using a descriptive name (`feature/…`, `fix/…`).
3. **Follow the layering conventions:** keep DB access in repositories, business logic and transaction commits in services, and routes thin. Raise domain exceptions and translate them to HTTP at the route boundary.
4. **When adding a new ORM model**, register it in `app/models.py` and generate an Alembic migration.
5. **When adding a new activity kind**, add an archetype to the scoring registry *and* a contract row — the app fails at import if they fall out of sync.
6. **Run all checks** (`ruff`, `mypy`, `pytest`, `npm run lint`, `npm run test`) before opening a PR.
7. **Keep PRs focused** — one logical change per PR, with a clear description.

See [`CLAUDE.md`](CLAUDE.md) for a deeper tour of the architecture and conventions.

---

## 📄 License

This project is licensed under the **MIT License** — see the [`LICENSE`](LICENSE) file for details.

---

<div align="center">

**[🌐 lingosai.com](https://www.lingosai.com)** · Built for learners who want English that works at work.

</div>
