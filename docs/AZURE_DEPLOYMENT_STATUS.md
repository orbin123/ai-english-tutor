# Azure Zero-Cost Deployment — Status and Remaining Blockers

**Last updated:** 19 August 2026
**Reference:** [AZURE_ZERO_COST_MIGRATION.md](./AZURE_ZERO_COST_MIGRATION.md)
**Free-tier expiry:** 18 June 2027

**Live cloud (29 August 2026):** the VM topology **is provisioned**. See
[Azure/LIVE_STATUS.md](./Azure/LIVE_STATUS.md). The API process is not on
the VM yet; `api.lingosai.com` does not exist. Container Apps is not in
this subscription.

This document tracks what has been completed toward running `www.lingosai.com`
end-to-end on Azure at zero Azure infrastructure cost, and what remains.

---

## Completed

### WP1 — Neutralize AWS deployment workflow

`deploy.yml` is renamed "AWS recovery deploy (manual only)" and has no `push`
trigger. Pushes and merges to `main` cannot invoke AWS deployment.

### WP2 — Data recovery / fresh-start gate

Resolved 14 August 2026: no AWS data will be restored. The Azure database
starts fresh. The initial administrator is created through the fail-closed
process in
[AZURE_FRESH_START_ADMIN_BOOTSTRAP.md](./AZURE_FRESH_START_ADMIN_BOOTSTRAP.md).

### WP3 — Azure application refactor (code changes)

| Item | Status |
| --- | --- |
| Azure Blob storage adapter (`app/ai/storage/azure_client.py`) | Done |
| Azure Postgres managed-identity auth (`app/core/azure_postgres.py`) | Done |
| Redis made fully optional (`redis_url: str \| None = None`) | Done |
| Health endpoint skips Redis when not configured | Done |
| DB pool size configurable and capped for B1ms (`DB_POOL_SIZE=3`, max 5 total) | Done |
| CORS uses `settings.cors_origins_list` (not hardcoded) | Done |
| Upload size limits enforced (`core/audio_uploads.py`) | Done |
| AI concurrency semaphore (`core/ai_concurrency.py`) | Done |
| Task-generation semaphore in `sessions/service.py` | Done |
| Azure deps added to `pyproject.toml` (`azure-identity`, `azure-storage-blob`) | Done |
| Azure Blob / Key Vault / managed-identity settings in `config.py` | Done |
| `DATABASE_AUTH_MODE` with production URL validation | Done |

### WP5 — CI/CD workflows

| Workflow | Purpose | Status |
| --- | --- | --- |
| `azure-deploy.yml` | Push-to-main deploy through ACR + VM Run Command | Authored |
| `azure-wake.yml` | Manual start with bounded live window (1-24 h) | Authored |
| `azure-sleep.yml` | Manual deallocate VM + stop PostgreSQL | Authored |
| `azure-sleep-watchdog.yml` | Hourly enforcement of expired live windows | Authored |

### WP5 — Azure scripts

Seven scripts in `.github/scripts/`: `azure-vm-bootstrap.sh`,
`azure-vm-deploy.sh`, `azure-vm-verify.sh`, `azure-vm-stop.sh`,
`azure-vm-wake.sh`, `azure-control-plane.sh`,
`azure-postgres-identity-bootstrap.sh`.

### Azure Terraform

Full `infra/azure/` tree with modules for: vm, postgres, acr, storage,
network, key-vault, cost-guardrails. Bootstrap and prod environment roots are
present. Static guardrail and host-contract test scripts included.

### Frontend

`ApiAvailabilityBanner` component detects API sleep/offline state and keeps
public pages usable while the backend is cold.

### Documentation

| Document | Covers |
| --- | --- |
| `AZURE_ZERO_COST_MIGRATION.md` | Full migration architecture and cost analysis |
| `AZURE_CICD_RUNBOOK.md` | Workflow operation, human-owned setup, failure/rollback |
| `AZURE_VM_HOST_BOOTSTRAP.md` | VM provisioning, Caddy, Docker, env-file contract |
| `AZURE_FRESH_START_ADMIN_BOOTSTRAP.md` | One-time admin creation for fresh database |
| `AZURE_POSTGRES_MANAGED_IDENTITY.md` | Entra-only auth, identity bootstrap gate |

---

## Remaining — Code Changes

All items below were completed in the Azure go-live code phase (August 2026).

- [x] **Remove `boto3` from `pyproject.toml`**
- [x] **Remove `s3_client.py`** and `tests/unit/ai/test_s3_blob_storage.py`
- [x] **Remove `ses_client.py`** — email provider is `console` or `resend`
- [x] **Gate debug AI routes in production** — router not mounted when
  `ENVIRONMENT=production`; routes also carry a fail-closed dependency
- [x] **Persistent daily/monthly quota counters** — `usage_quota_counters`
  table + `app/modules/quotas/` service hooks
- [x] **Disable costly features via config flags** — `ENABLE_IMAGE_GENERATION`,
  `ENABLE_DEEPGRAM`, `ENABLE_RAG_FEEDBACK`, `ENABLE_MENTOR_SAMPLING`
- [x] **Blob lifecycle / retention enforcement** — `scripts/cleanup_media_cache.py`
  with configurable retention days

## Remaining — Owner Actions

These require Azure Portal access, billing authority, credential handling, or
DNS control. They are listed in dependency order.

### Phase 0 — Cost safety (before any Azure resource)

See [AZURE_PHASE0_OWNER_CHECKLIST.md](./AZURE_PHASE0_OWNER_CHECKLIST.md) for
step-by-step commands.

- [ ] **Install Azure CLI + Terraform** — `brew install azure-cli` and
  `brew install hashicorp/tap/terraform`, then `az login`.
- [ ] **Confirm subscription and free meters** — screenshot the Free Services
  blade; verify `Standard_B2ats_v2` and `Standard_B1ms` eligibility in the
  chosen region.
- [ ] **Choose and confirm region** — run `az vm list-skus --location
  centralindia --size Standard_B2ats_v2` and `az postgres flexible-server
  list-skus --location centralindia` (or alternative region).
- [ ] **Create budget and cost alerts** — set a $1/month (or equivalent)
  budget with 25/50/75/90/100% actual and forecast alerts before
  provisioning any resource.

### Phase 3 — Infrastructure provisioning

- [ ] **Bootstrap Terraform state storage** — run
  `infra/azure/bootstrap/` to create the remote state account and container.
- [ ] **Run `terraform plan` and `terraform apply`** — provision the
  production stack from `infra/azure/environments/prod/`. Review every
  resource before applying.
- [ ] **Wait 24 hours and verify free meters** — confirm every provisioned
  resource appears under the expected free meter in Cost Analysis and the
  Free Services blade.

### Phase 3b — Identity and secrets

- [ ] **Configure Entra ID / OIDC federation** — create (or reuse) an Entra
  app registration; add federated credentials for subjects
  `repo:orbin123/lingos-ai:environment:production` and
  `repo:orbin123/lingos-ai:ref:refs/heads/main`, audience
  `api://AzureADTokenExchange`.
- [ ] **Grant scoped RBAC** — give the Entra identity a reviewed custom role
  at the resource-group scope (VM start/stop/run-command, PostgreSQL
  start/stop, ACR push/read, tag merge). No Owner/Contributor.
- [ ] **Set GitHub repository variables** —
  `AZURE_AUTOMATION_ENABLED` (initially `false`),
  `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`,
  `AZURE_ACR_NAME`, `AZURE_POSTGRES_SERVER`, `AZURE_API_BASE_URL`.
- [ ] **Create GitHub `production` Environment** — required reviewers,
  deployment-branch rule for `main`, environment variable
  `AZURE_PRODUCTION_ENVIRONMENT_GUARD=reviewed-and-protected`.

### Phase 3c — Database and VM host setup

- [ ] **Run Postgres identity bootstrap** — execute
  `.github/scripts/azure-postgres-identity-bootstrap.sh` with the approved
  server name, Entra admin group, VM managed-identity object ID, and current
  public IP.
- [ ] **Bootstrap the VM host** — run the reviewed
  `.github/scripts/azure-vm-bootstrap.sh`; populate
  `/etc/lingosai/backend.env` from Key Vault secrets.
- [ ] **Create fresh admin account** — follow
  [AZURE_FRESH_START_ADMIN_BOOTSTRAP.md](./AZURE_FRESH_START_ADMIN_BOOTSTRAP.md)
  before allowing public traffic.

### Phase 5 — Activation and rehearsal

- [ ] **Set `AZURE_AUTOMATION_ENABLED=true`** — only after every preceding
  gate passes.
- [ ] **Run production rehearsal** — dispatch `azure-wake.yml`, approve and
  run `azure-deploy.yml`, complete smoke tests (login, API, WebSocket,
  media), then dispatch `azure-sleep.yml`. Verify final states.

### Phase 6 — DNS cutover and integration

- [ ] **Lower DNS TTL** — at Namecheap, reduce the `api` A-record TTL at
  least 24 hours before cutover.
- [ ] **Point DNS to Azure** — set the `api.lingosai.com` A record to the
  VM's static public IP.
- [ ] **Update OAuth redirect URIs** — Google OAuth callback must point to
  the Azure API URL.
- [ ] **Update Razorpay webhook URL** — point to the Azure API.
- [ ] **Update frontend environment** — set `NEXT_PUBLIC_API_URL` and
  `NEXT_PUBLIC_WS_URL` to the Azure API origin; redeploy on Vercel.
- [ ] **Verify CORS, TLS, WebSocket, email links** — end-to-end from
  every allowed frontend origin.

### Phase 7 — Post-cutover

- [ ] **30-day monitoring** — daily Cost Analysis + Free Services blade
  inspection for the first month, then weekly.
- [ ] **Remove AWS code after stability** — once Azure is stable and no
  rollback to AWS is needed, remove `s3_client.py`, `ses_client.py`,
  `boto3`, AWS Terraform (`infra/terraform/`), and AWS workflow credentials
  through a reviewed PR.

---

## Recommended Sequence

```
Code changes (PRs, can start now)
  |
  v
Phase 0: cost safety (Azure Portal)
  |
  v
Phase 3: terraform apply + 24h meter check
  |
  v
Phase 3b: Entra OIDC + GitHub config
  |
  v
Phase 3c: Postgres identity + VM host + fresh admin
  |
  v
Phase 5: activate + rehearsal
  |
  v
Phase 6: DNS cutover + integrations
  |
  v
Phase 7: 30-day monitoring, then AWS cleanup
```

Code changes and Phase 0 can happen in parallel. Everything from Phase 3
onward is sequential.

---

## Non-Azure Costs to Manage

Azure infrastructure can be $0, but the application depends on external
services with their own billing:

| Service | Used for | Free tier / action needed |
| --- | --- | --- |
| **OpenAI** | LLM evaluation, task generation, feedback, TTS, STT | No perpetual free tier; set spend cap or use Azure OpenAI if added to benefits |
| **Pinecone** | RAG feedback memory vectors | Starter plan has limits; consider replacing with PostgreSQL pgvector |
| **Vercel** | Frontend hosting (Phase 1) | Hobby plan is free for personal use; verify limits |
| **Sentry** | Error monitoring | Free Developer plan; cap event volume |
| **Resend** | Transactional email | Free tier: 100 emails/day, 3000/month |
| **Razorpay** | Payment processing | No hosting cost; transaction fees apply |
| **Deepgram** | STT (if enabled) | $200 free credit; disable after exhaustion or use Azure Speech |
| **LangSmith** | LLM tracing | Free Developer plan; cap traces |

To achieve true $0 total cost, either keep each service within its free tier
or disable the dependent feature via the production config flags described
above.
