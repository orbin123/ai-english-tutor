# LingosAI Azure go-live — master plan

**Owner:** Orbin Sunny · **Created:** 31 August 2026 · **Target:** `www.lingosai.com`
fully live against the Azure production stack, inside the free allowances.

Progress lives in [AGENT_WORK.md](./AGENT_WORK.md). **Read that file first**, find the
first phase that is not `DONE`, then open this file at that phase and continue there.

---

## Verified starting state (Azure CLI + GitHub CLI, 31 August 2026)

The older docs in `docs/` describe a much earlier situation. These are the facts:

| Resource | Verified state |
| --- | --- |
| VM `vm-lingosai-prod` | `Standard_B2ats_v2` (2 vCPU / 1 GiB RAM), **deallocated** |
| PostgreSQL `psql-lingosai-e231` | `Standard_B1ms`, PG 16, **Stopped**, Entra-only auth |
| ACR `acrlingosaie231` | **Basic** SKU (~$5/mo), admin disabled |
| Public IP `pip-lingosai-prod` | Standard SKU, **Static**, `20.219.52.248` |
| DNS `api.lingosai.com` | **Resolves to `20.219.52.248`** |
| Key Vault `kv-lingosai-e231` | Contains secret `backend-env` |
| Blob | `stlingosaipube231` (`public-media`), `stlingosaiprive231` (`learner-media`, `internal-media`) |
| GitHub var `AZURE_AUTOMATION_ENABLED` | **`true`** |
| GitHub Environment `production` | Exists (reviewer-gated) |
| Last `Azure backend deploy` run | **success**, 30 August 2026, on `main` |
| Azure Speech | `lingosai-speech` (F0 free) in `lingosai-rg` / `eastus` |
| Budget | `budget-lingosai-prod` at **$1/month** (unrealistically low — Phase 6) |

The host is bootstrapped and a deploy has landed. The environment is simply **asleep**.

### Steady-state cost

| Item | Cost |
| --- | --- |
| VM `B2ats_v2` | Free — 750 h/month allowance until **18 June 2027** |
| PostgreSQL `B1ms` + 32 GiB | Free — 12-month allowance |
| Blob, Key Vault | Effectively free at this volume |
| **Static public IP** | ~**$3.6/mo** — required, see below |
| **ACR Basic** | ~**$5/mo** — retained by decision, see below |
| **Total floor** | ≈ **$9/mo (~₹800)** |

**Why the static IP is required.** A dynamic public IP is released when the VM is
deallocated. Because this deployment sleeps and wakes daily, the address would change on
every wake, breaking both the `api.lingosai.com` A record and Caddy's Let's Encrypt
certificate. The static IP is the price of the sleep/wake design.

**Why ACR is retained.** It is Basic (~$5/mo), not the Standard (~$20/mo) the old docs
claim. Keeping it preserves the reviewed digest-pinned deploy and one-command rollback in
`.github/scripts/azure-vm-deploy.sh`, which has already run green. The alternative —
`uv sync` or `docker build` directly on a **1 GiB RAM** VM — is the riskier path on this
machine size.

---

## Feature decisions for production

`.env.production.example` originally disabled several paths purely out of cost caution.
These are the decisions now in force:

| Setting | Prod value | Reason |
| --- | --- | --- |
| `ENABLE_DEEPGRAM` | `true` | Deepgram free credit is sufficient; the A2Z game needs it |
| `ENABLE_RAG_FEEDBACK` | `true` | Required for mentor notes; Pinecone free tier is sufficient |
| `ENABLE_MENTOR_SAMPLING` | `true` | Mentor note is a core product feature |
| `ENABLE_IMAGE_GENERATION` | `true` | Wanted; capped by `QUOTA_MONTHLY_IMAGE_GENS` |
| `QUOTA_MONTHLY_IMAGE_GENS` | `300` | Real cap replacing the `0` kill switch |
| `LANGCHAIN_TRACING_V2` | `true` | Free tier; see the privacy note below |
| `RAG_PER_ACTIVITY_FEEDBACK` | `false` | The expensive RAG path; the mentor note is the goal |
| `SENTRY_DSN` | empty | Sentry deliberately off |
| `RAZORPAY_*` | `rzp_test_*` | Test mode costs nothing and unblocks the payment flow |
| `EMAIL_PROVIDER` | `resend` | The OTP path — without it nobody can verify an account |

Two things worth being precise about:

- **Image generation bills the OpenAI API account per image** (`gpt-image-2` ≈ $0.04 at
  `medium` quality). That is a *different* wallet from a ChatGPT subscription.
  `QUOTA_MONTHLY_IMAGE_GENS` is the only real guard — keep it finite.
- **LangSmith tracing was disabled for data residency, not cost**
  (see the comment at `backend/app/core/config.py:159`): tracing ships learner content to
  LangSmith. Enabling it is a deliberate privacy choice, and it is free.

Mentor notes need **both** `ENABLE_MENTOR_SAMPLING` and `ENABLE_RAG_FEEDBACK` — both are
read in `backend/app/modules/sessions/service.py` (around lines 1969 and 1989). Enabling
only one produces a degraded note.

---

## Ground rules for every phase

- One phase = one branch = one PR = squash-merge to `main`. **Never push to `main`.**
- Sign off every commit: `git commit -s`. No `Co-Authored-By`, no AI/tool attribution.
- Before pushing: `uv run ruff format app tests`, `uv run ruff check app tests`,
  `uv run mypy app`, and the relevant tests. Regenerate `backend/openapi.json` with
  `uv run python scripts/export_openapi.py` if any route changed.
- Update the phase's row in [AGENT_WORK.md](./AGENT_WORK.md) when the PR merges.
- Real secrets are **never** committed. Only shapes and placeholders go in git.

---

## Phase 0 — Tracking files

**Branch:** `docs/azure-master-plan`

Create this file and `AGENT_WORK.md`, and correct `LIVE_STATUS.md` to the verified facts
above (it previously misstated the ACR SKU, claimed `api.lingosai.com` was NXDOMAIN, and
said automation was disabled).

**Acceptance:** both files on `main`; `LIVE_STATUS.md` matches `az` output.

---

## Phase 1 — Production environment file  ← *highest-risk phase*

**Branch:** `chore/azure-prod-env-template`

The file containing real keys is built locally, validated locally, uploaded straight to
Key Vault, and then destroyed. **It is never committed.**

### 1a — Repo change (committed)

Update `.env.production.example` to the feature decisions in the table above, so the
*shape* of the file is right even though the values are placeholders.

### 1b — Build the real file locally

`scripts/build-prod-env.sh` (added in this phase) produces `/tmp/lingosai-backend.env`
and validates it against the two independent gates it must survive.

**Gate A — the host contract.** `validate_environment_file` in
`.github/scripts/azure-vm-bootstrap.sh` rejects the file unless it contains these lines
*verbatim*:

```
ENVIRONMENT=production
DEBUG=false
DATABASE_AUTH_MODE=azure-managed-identity
AUTH_COOKIE_SECURE=true
AI_RATE_LIMIT_BACKEND=memory
WEB_CONCURRENCY=1
STORAGE_BACKEND=azure
```

It also rejects the file if it has CRLF line endings, if any value still looks like an
angle-bracket placeholder (a value such as `EMAIL_FROM="LingosAI <noreply@lingosai.com>"`
is allowed because it contains `@`), or if `DATABASE_URL` is not exactly:

```
DATABASE_URL=postgresql://vm-lingosai-prod@psql-lingosai-e231.postgres.database.azure.com:5432/lingosai?sslmode=require
```

That URL must carry **no password** — authentication is Entra managed identity.

**Gate B — the application's own production guard.** `_guard_production` in
`backend/app/core/config.py` refuses to boot unless `SQL_ECHO=false`,
`DEV_OTP_BYPASS=false`, `OTP_HASHING_SECRET` is set, `DB_POOL_SIZE + DB_MAX_OVERFLOW <= 5`,
`CORS_ORIGINS` holds only public HTTPS origins, and `FRONTEND_URL` is a public HTTPS
origin **that also appears in `CORS_ORIGINS`**. With `STORAGE_BACKEND=azure` it further
requires these exact values (confirmed against live Azure):

```
AZURE_BLOB_PUBLIC_ACCOUNT_URL=https://stlingosaipube231.blob.core.windows.net
AZURE_BLOB_PRIVATE_ACCOUNT_URL=https://stlingosaiprive231.blob.core.windows.net
AZURE_BLOB_PUBLIC_CONTAINER=public-media
AZURE_BLOB_PRIVATE_CONTAINER=learner-media
AZURE_BLOB_INTERNAL_CONTAINER=internal-media
AZURE_BLOB_PUBLIC_CONTAINER_ACCESS=blob
AZURE_BLOB_PRIVATE_CONTAINER_ACCESS=private
AZURE_BLOB_INTERNAL_CONTAINER_ACCESS=private
```

The public and private accounts must be *different* storage accounts. They are.

The script then dry-runs Gate B for real, so a bad file is caught on the laptop rather
than by a crash-looping container:

```bash
./scripts/build-prod-env.sh
```

### 1c — Values to fill in by hand

Copy these from the repo-root `.env` (all verified present and non-placeholder there):
`OPENAI_API_KEY`, `DEEPGRAM_API_KEY`, `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION`,
`PINECONE_API_KEY`, `LANGCHAIN_API_KEY`, `RESEND_API_KEY`, `GOOGLE_CLIENT_ID`,
`GOOGLE_CLIENT_SECRET`, `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`,
`RAZORPAY_WEBHOOK_SECRET`.

Generate **fresh** production values — do not reuse the dev ones:

```bash
openssl rand -hex 32
```

for `JWT_SECRET` and again for `OTP_HASHING_SECRET`.

Production-specific values:

```
GOOGLE_REDIRECT_URI=https://api.lingosai.com/auth/google/callback
CORS_ORIGINS=https://www.lingosai.com,https://lingosai.com
FRONTEND_URL=https://www.lingosai.com
EMAIL_PROVIDER=resend
SENTRY_DSN=
```

### 1d — Upload as a new Key Vault version

```bash
az keyvault secret set --vault-name kv-lingosai-e231 --name backend-env --file /tmp/lingosai-backend.env --output none
```

This creates a new version; the previous version remains available as a rollback. Then
destroy the local copy:

```bash
shred -u /tmp/lingosai-backend.env 2>/dev/null || rm -P /tmp/lingosai-backend.env
```

**Acceptance:** the dry-run prints `production config OK`; a new `backend-env` version
exists in Key Vault; no real key appears anywhere in git.

---

## Phase 2 — External credential verification

**Branch:** `feat/external-service-healthcheck`

Add `backend/scripts/check_external_services.py`: one read-only, near-free probe per
provider, printing a PASS/FAIL table and exiting non-zero if anything fails.

| Service | Probe |
| --- | --- |
| OpenAI chat | one-token completion on `OPENAI_CHAT_MODEL` |
| OpenAI embeddings | embed `ping`; assert dimension == `OPENAI_EMBEDDING_DIMENSIONS` (1024) |
| OpenAI TTS / STT / image | model-list membership only — no paid generation |
| Pinecone | `describe_index`: assert dimension 1024, metric cosine, namespace reachable |
| Deepgram | project list via REST |
| Azure Speech | issue an auth token from `AZURE_SPEECH_REGION` |
| Azure Blob | list containers on both accounts via `DefaultAzureCredential` |
| Azure PostgreSQL | Entra-token connect + `SELECT 1` through `app/core/azure_postgres.py` |
| Resend | `GET /domains` |
| Razorpay | create then immediately verify a ₹1 **test-mode** order |
| LangSmith | `GET /info` on `LANGCHAIN_ENDPOINT` |

Locally:

```bash
cd backend && uv run python scripts/check_external_services.py
```

On the VM, against the real production environment file:

```bash
az vm run-command invoke -g rg-lingosai-prod -n vm-lingosai-prod --command-id RunShellScript --scripts 'docker run --rm --env-file /etc/lingosai/backend.env $(cat /var/lib/lingosai/deployed-image) python scripts/check_external_services.py'
```

Also add a `?deep=1` mode to `/health/ready` (`backend/app/main.py`) reporting optional
dependency status (Pinecone, Blob) **without** changing the plain `/health/ready`
contract — the frontend `ApiAvailabilityBanner` depends on its existing 2xx/503 semantics.
Regenerate `backend/openapi.json`.

**Acceptance:** every row PASSes when run on the VM.

---

## Phase 3 — Wake, deploy, and verify live

**Branch:** `fix/azure-live-bringup` (carries whatever fixes fall out)

```bash
gh workflow run azure-wake.yml -f hours=6
```

Approve the run in the protected `production` environment, then watch it:

```bash
gh run watch $(gh run list -w azure-wake.yml -L1 --json databaseId --jq '.[0].databaseId')
```

Then, in order:

1. Re-run the host bootstrap so the VM picks up the **new** `backend-env` version.
2. Redeploy from `main` so the container restarts with the new environment:

```bash
gh workflow run azure-deploy.yml
```

   Confirm the run resolves a `sha256` digest, not a floating tag.
3. Bootstrap the first administrator on the fresh database, per
   [../AZURE_FRESH_START_ADMIN_BOOTSTRAP.md](../AZURE_FRESH_START_ADMIN_BOOTSTRAP.md),
   using `backend/scripts/bootstrap_fresh_admin.py`.
4. Seed content: `seed_curriculum.py`, then `seed_ielts_challenge.py` and
   `seed_a2z_challenge.py`.
5. Public checks, and confirm the Caddy maintenance marker is gone:

```bash
curl -sf https://api.lingosai.com/health/live && curl -sf https://api.lingosai.com/health/ready
```

6. Set the Vercel project environment to `NEXT_PUBLIC_API_URL=https://api.lingosai.com`
   and `NEXT_PUBLIC_WS_URL=wss://api.lingosai.com`, then redeploy the frontend.
7. Add `https://api.lingosai.com/auth/google/callback` to the Google OAuth client, and
   point the Razorpay **test** webhook at
   `https://api.lingosai.com/api/payments/webhook`.

**Acceptance:** `https://www.lingosai.com` loads with the availability banner in its
*live* state and `/health/ready` returns 2xx.

---

## Phase 4 — End-to-end functional verification

**Branch:** `test/azure-e2e-smoke`

Add `scripts/e2e-smoke.sh` — bash + `curl` + `jq`, re-runnable, using a throwaway
learner account against the live API:

1. `POST /auth/register` → OTP email via Resend → `POST /auth/verify` → JWT issued and the
   refresh cookie carries `Secure`.
2. Google OAuth login, manually in a browser (the callback cannot be scripted).
3. Diagnosis flow → `SkillPoints` seeded, **no** scorecard points awarded.
4. `POST /sessions/start` → WebSocket connect → the `learning_session.event.v1` stream
   emits `teaching` → `task` → `evaluation` → `feedback` in order.
5. Submit each activity → per-activity feedback returns, scores non-null.
6. Complete the session → scorecard returns, **the `rag_feedback` mentor-note event is
   present and non-empty**, and the Pinecone `feedback_memory` namespace vector count
   increases.
7. Replay guard: re-submit a completed activity → `SkillPoints` does **not** increase.
8. Speaking activity: record → `POST /responses/transcribe-audio` → transcript and audio
   URL returned, and the URL is an **Azure Blob** URL, not a local `/audio` path.
9. A2Z challenge WebSocket → the Deepgram stream connects (proves `ENABLE_DEEPGRAM`).
10. Dashboard: streak + progress → the 91-day grid marks **today** correctly in the
    learner's timezone, and the 0–10 dashboard score matches the scoring engine's output.
11. Razorpay test-mode order creation from the payment page.

Then a **manual browser pass** on `www.lingosai.com`: every chat widget type renders,
generated images appear, audio plays, the mentor note renders at session end, and the
`/stats` dates line up with the sessions actually completed.

Record every discrepancy in `AGENT_WORK.md`; fix it in this PR or open a follow-up phase.

**Acceptance:** all eleven steps pass, and the mentor note and stats dates are confirmed
by eye as well as by assertion.

---

## Phase 5 — Local sleep/wake control

**Branch:** `feat/local-azure-lifecycle-scripts`

Three thin wrappers over the existing `.github/scripts/azure-control-plane.sh` — one
implementation, not two. Each refuses to run unless `az account show` reports the expected
subscription.

| Script | What it does |
| --- | --- |
| `scripts/azure-up.sh [hours]` | Start PostgreSQL → wait `Ready` → start the VM → wait running → set the `lingosai-active-until` tag (default 6 h, clamped 1–24) → run `azure-vm-wake.sh` via Run Command → poll `https://api.lingosai.com/health/ready` until 2xx |
| `scripts/azure-down.sh` | Run `azure-vm-stop.sh` (maintenance marker, stop container) → `az vm deallocate` → verify `Stopped (Deallocated)` → `az postgres flexible-server stop` → verify |
| `scripts/azure-status.sh` | Print VM power state, PostgreSQL state, the active-until tag, the `/health/ready` result, and **VM hours used this calendar month against the 750 h allowance**, warning past 600 h |

One-time:

```bash
chmod +x scripts/azure-up.sh scripts/azure-down.sh scripts/azure-status.sh
```

Wake the environment for four hours:

```bash
./scripts/azure-up.sh 4
```

Check state and hours consumed:

```bash
./scripts/azure-status.sh
```

Put everything back to sleep:

```bash
./scripts/azure-down.sh
```

The hourly `azure-sleep-watchdog.yml` stays enabled as the backstop for a forgotten
`azure-down.sh`.

**Acceptance:** `azure-up.sh` takes the stack from fully cold to a public 2xx
`/health/ready`; `azure-down.sh` returns it to deallocated + stopped; `azure-status.sh`
reports hours used.

---

## Phase 6 — Documentation reconciliation and cost guard

**Branch:** `docs/azure-reconcile`

- Correct `docs/AZURE_DEPLOYMENT_STATUS.md` and `docs/azure/LIVE_STATUS.md`: ACR is
  **Basic**, DNS **exists**, `AZURE_AUTOMATION_ENABLED` is **true**, a deploy **has**
  succeeded, and both `az` and `gh` authenticate from the workstation.
- Remove the Container Apps "Path A / Path B" decision block — the VM path is chosen and
  live.
- Record the real steady-state cost (the table at the top of this file).
- Raise `budget-lingosai-prod` from `$1/month` to roughly `$15` so the alert stops firing
  constantly and starts meaning something.
- Add an ACR retention/purge note so old image tags do not creep toward the Basic 10 GB
  quota.
- Mark every phase `DONE` in `AGENT_WORK.md`.

**Acceptance:** the docs match `az` output and the budget alert is meaningful.

---

## Verification summary

| Layer | How |
| --- | --- |
| Config safety | `Settings()` dry-run against the prod env file (Gate B) before upload |
| Host contract | `validate_environment_file` in `azure-vm-bootstrap.sh` (Gate A) |
| Credentials | `backend/scripts/check_external_services.py`, run on the VM |
| API liveness | `curl https://api.lingosai.com/health/live` and `/health/ready` |
| Product flow | `scripts/e2e-smoke.sh` plus a manual browser pass |
| Cost | `scripts/azure-status.sh` (hours vs 750) and the hourly sleep watchdog |
| Regressions | required checks: `lint`, `types`, `unit`, `integration`, `migrations`, `coverage`, `ci`, `openapi-drift`, `docker-build`, `DCO`, `Vercel` |

## Risks

- **1 GiB RAM VM.** One uvicorn worker with `AI_MAX_CONCURRENT_JOBS=3`, plus RAG and image
  generation now enabled, will be tight. The bootstrap adds 1 GB of swap; if the container
  OOMs during Phase 4, lower `AI_MAX_CONCURRENT_JOBS` to `2` before resizing the VM.
- **The Pinecone index must already exist** at dimension 1024 / metric cosine, or every
  upsert fails silently and mentor notes produce nothing. Phase 2's probe catches this.
- **Image generation bills the OpenAI API account per image.**
  `QUOTA_MONTHLY_IMAGE_GENS` is the only real guard — keep it finite.
- **LangSmith tracing sends learner content off-box** — a privacy choice, not a cost one.
- **Phase 1 is the single highest-risk step.** A malformed environment file either fails
  host validation or crash-loops the container. The local dry-run in 1b is what prevents
  that.
