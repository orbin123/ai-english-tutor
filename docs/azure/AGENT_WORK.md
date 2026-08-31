# Agent work log — Azure go-live

**This is the file to read first.**

## How to resume this work

1. Read this file. Find the **first phase row below that is not `DONE`**.
2. Open [MASTER_PLAN.md](./MASTER_PLAN.md) and go to that phase.
3. Do that phase, and only that phase. One phase = one branch = one PR.
4. When its PR is merged, come back and update the row: set `Status` to `DONE`, fill in
   the PR number and date, and put anything the next session needs to know in `Notes`.
5. If a phase turns up a problem that does not belong to it, write it under
   **Open issues** below rather than widening the phase.

**Right now that means Phase 3.** Jump to *Next up: Phase 3* below — it has the full
runbook, the live resource names, and the failures to expect.

Rules that apply to every phase are in the *Ground rules* section of `MASTER_PLAN.md`.
The short version: never push to `main`, sign off every commit with `git commit -s`, no
AI attribution in commits or PRs, and never commit a real secret.

## Phase status

| # | Phase | Branch | PR | Status | Date | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | Tracking files | `docs/azure-master-plan` | [#208](https://github.com/orbin123/lingos-ai/pull/208) | DONE | 2026-08-31 | `docs/azure/` had to be un-ignored in `.gitignore` |
| 1 | Production environment file | `chore/azure-prod-env-template` | [#209](https://github.com/orbin123/lingos-ai/pull/209) | DONE | 2026-08-31 | Real values uploaded to Key Vault `backend-env` version `b0d33c5f889b4d0fbe392dfd96012e29`. Both gates passed first. Two older versions remain as rollback |
| 2 | External credential verification | `feat/external-service-healthcheck` | [#210](https://github.com/orbin123/lingos-ai/pull/210) | DONE | 2026-08-31 | Run against the **production** values: 10 of 11 pass, including Azure Blob. Only `azure-postgres` fails, correctly — the server is stopped and its firewall admits the VM only. Re-run it on the VM in Phase 3 |
| 3 | Wake, deploy, verify live | `fix/azure-live-bringup` | — | READY | — | Unblocked: Key Vault holds the real environment. **This is the next phase to run.** |
| 4 | End-to-end functional verification | `test/azure-e2e-smoke` | — | NOT STARTED | — | Chat flow, mentor note, stats/streak dates |
| 5 | Local sleep/wake control | `feat/local-azure-lifecycle-scripts` | [#211](https://github.com/orbin123/lingos-ai/pull/211) | DONE | 2026-08-31 | Done out of order because Phase 3 is blocked. `azure-status.sh` verified against live Azure; `azure-up.sh` / `azure-down.sh` get their first real run in Phase 3 |
| 6 | Docs reconciliation + cost guard | `docs/azure-reconcile` | — | NOT STARTED | — | Raise the $1/month budget; fix the stale docs |

## Where this stands

Phases 0, 1, 2 and 5 are merged, and the production environment is in Key Vault. **Phase 3
is the next phase to run.**

### What is in `backend-env` (version `b0d33c5f…96012e29`)

The owner supplied a complete production file. It was uploaded as pasted, except for eight
deliberate changes agreed at the time:

| Setting | Was | Is | Why |
| --- | --- | --- | --- |
| `ENABLE_DEEPGRAM` | false | true | A2Z speech game needs it; free tier |
| `ENABLE_RAG_FEEDBACK` | false | true | Mentor note needs it |
| `ENABLE_MENTOR_SAMPLING` | false | true | Mentor note needs both switches |
| `ENABLE_IMAGE_GENERATION` | false | true | Wanted |
| `QUOTA_MONTHLY_IMAGE_GENS` | 0 | 300 | Finite cap rather than a kill switch |
| `DEEPGRAM_API_KEY` | empty | set | Required once the switch is on |
| `LANGCHAIN_TRACING_V2` | false | true | Deliberate: tracing sends learner content to LangSmith |
| `SENTRY_DSN` | a real DSN | blank | Sentry deliberately off |

`AI_EVAL_ENABLED` and `AI_REQUEST_LOGGING_ENABLED` were left `false` as supplied.

A ninth change was a bug fix rather than a decision — see the `EMAIL_FROM` note below.

The uploaded values were then verified end to end: **10 of 11 probes pass**, including
Pinecone (1024d cosine, 125 vectors), Deepgram, Azure Speech, Azure Blob, Resend, Razorpay
test mode and LangSmith. Only `azure-postgres` fails, correctly, from a laptop.

Note the file keeps `OPENAI_CHAT_MODEL=gpt-4o-mini`, not the `gpt-4.1-mini` the repo
template suggests. That is the owner's value and was left alone.

### `EMAIL_FROM` — a fixed bug, and a trap

It was supplied **quoted** (`EMAIL_FROM="LingosAI <noreply@lingosai.com>"`) and was
uploaded **unquoted**. Docker's `--env-file` does not strip quotes, so the quoted form
would have put literal `"` characters in the sender address and Resend would have rejected
every OTP email — meaning no account could ever have been verified. Do not "helpfully"
re-quote it.

The trap: the unquoted form cannot be `source`d in a shell, because `<` reads as a
redirect. Load the file with a parser, not `source`.

## Live environment quick reference

Verified from `az` on 31 August 2026. Both `az` and `gh` authenticate from the owner's
workstation.

| | |
| --- | --- |
| Subscription | `e231ab32-f4d4-4a1b-b96c-3cf279036ab7` (`Azure subscription 1`) |
| Resource group | `rg-lingosai-prod`, `centralindia` |
| VM | `vm-lingosai-prod`, `Standard_B2ats_v2` — **2 vCPU / 1 GiB RAM** |
| PostgreSQL | `psql-lingosai-e231`, `B1ms`, PG 16, Entra-only auth |
| Public IP | `pip-lingosai-prod`, Standard, **static**, `20.219.52.248` |
| DNS | `api.lingosai.com` → `20.219.52.248` (already resolves) |
| ACR | `acrlingosaie231`, **Basic** SKU, admin disabled, repo `lingosai-backend` |
| Key Vault | `kv-lingosai-e231`, secret `backend-env` |
| Blob | `stlingosaipube231` (`public-media`), `stlingosaiprive231` (`learner-media`, `internal-media`) |
| Frontend | Vercel, `www.lingosai.com` |
| Automation | `AZURE_AUTOMATION_ENABLED=true`; `production` Environment exists and is reviewer-gated |

The VM and PostgreSQL being stopped is the **normal resting state**, not a fault.

### Everyday commands

```bash
./scripts/azure-status.sh          # state, live window, public health, hours vs 750
./scripts/azure-up.sh 4            # wake for 4 hours, then poll the public endpoint
./scripts/azure-down.sh            # drain, deallocate, stop PostgreSQL
```

```bash
cd backend && uv run python scripts/check_external_services.py
```

---

## Next up: Phase 3 — wake, deploy, verify live

Everything Phase 3 needs is in place. This is the phase that makes the API publicly
reachable. Branch `fix/azure-live-bringup`; the PR carries whatever fixes fall out.

**Before starting, check the hour budget** with `./scripts/azure-status.sh`. August 2026
used 713.5 of 750 hours; the allowance resets on the 1st of each month.

1. **Wake it.** `./scripts/azure-up.sh 6`. Expect the public poll to fail on the first run
   — the container is still on the old environment and Caddy's maintenance marker may
   never lift. That is not a reason to stop; continue to step 2.
2. **Make the VM re-read Key Vault.** The VM does *not* notice a new secret version on its
   own. Re-run the host bootstrap through Run Command:
   `bash azure-vm-bootstrap.sh api.lingosai.com kv-lingosai-e231 backend-env`. It
   re-validates the file and installs it at `/etc/lingosai/backend.env`, root-owned, 0600.
3. **Redeploy** so the container restarts with the new environment: `gh workflow run
   azure-deploy.yml`, approve in the `production` Environment. Confirm the run resolves a
   `sha256` digest rather than a floating tag.
4. **Re-run the credential checker on the VM.** This is the first time `azure-postgres`
   and `azure-blob` are exercised through the VM's managed identity:
   ```
   az vm run-command invoke -g rg-lingosai-prod -n vm-lingosai-prod \
     --command-id RunShellScript \
     --scripts 'docker run --rm --env-file /etc/lingosai/backend.env \
       $(cat /var/lib/lingosai/deployed-image) python scripts/check_external_services.py'
   ```
   All eleven probes should pass here. Locally only ten can.
5. **First admin** on the fresh database, per
   [../AZURE_FRESH_START_ADMIN_BOOTSTRAP.md](../AZURE_FRESH_START_ADMIN_BOOTSTRAP.md)
   using `backend/scripts/bootstrap_fresh_admin.py`.
6. **Seed content**: `seed_curriculum.py`, then `seed_ielts_challenge.py` and
   `seed_a2z_challenge.py`.
7. **Public checks**: `/health/live`, `/health/ready`, `/docs`, and confirm the Caddy
   maintenance marker at `/var/lib/lingosai/maintenance` is gone.
8. **Point the frontend at it**: Vercel env `NEXT_PUBLIC_API_URL=https://api.lingosai.com`
   and `NEXT_PUBLIC_WS_URL=wss://api.lingosai.com`, then redeploy.
9. **External callbacks**: add `https://api.lingosai.com/auth/google/callback` to the
   Google OAuth client, and point the Razorpay **test** webhook at
   `https://api.lingosai.com/api/payments/webhook`.

**Done when** `https://www.lingosai.com` loads with the availability banner in its *live*
state and `/health/ready` returns 2xx.

**Then run `./scripts/azure-down.sh`.** Leaving it awake is what burned August.

### Things that will probably bite

- **1 GiB of RAM.** One uvicorn worker with `AI_MAX_CONCURRENT_JOBS=3`, plus RAG and image
  generation now enabled, is tight. The host has 1 GB of swap. If the container OOMs, drop
  `AI_MAX_CONCURRENT_JOBS` to `2` in a new `backend-env` version before resizing the VM.
- **A 503 with the VM running** usually means the container is unhealthy, so the
  maintenance marker was never removed. Check `docker logs --tail 50 lingosai-backend`.
- **PostgreSQL firewall admits only `20.219.52.248`.** Any database probe from a laptop
  will time out. That is correct, not a defect.
- **Azure force-restarts a stopped Flexible Server after seven days.** The hourly watchdog
  puts it back to sleep.

---

## Open issues

- **August 2026 consumed 713.5 of the 750 free VM hours (95%).** Discovered by
  `scripts/azure-status.sh` on 31 August: the VM sat *running but idle* from 1 August until
  30 August, with no application installed. Roughly 37 hours of allowance were left for
  the month. The allowance resets on 1 September, but this is exactly the failure the
  sleep/wake discipline exists to prevent — wake for a bounded window, and run
  `scripts/azure-down.sh` when finished.

- **The `/health/ready?deep=1` idea from MASTER_PLAN Phase 2 was deliberately dropped.**
  `/health/ready` is unauthenticated and public, so a `deep` mode would let anyone on the
  internet trigger outbound calls to Pinecone and Azure Blob on every request — latency
  and third-party amplification against a 1 GiB VM, for no coverage the checker script
  does not already provide. Deep verification runs on demand instead, via
  `backend/scripts/check_external_services.py` on the VM. Revisit only behind admin auth.
- **The production keys should be rotated once the site is stable.** They were pasted
  into a chat transcript on 31 August while assembling the environment file. Nothing is
  known to be leaked, but treat them as burned: OpenAI, Razorpay, Google OAuth, Resend,
  Pinecone, Azure Speech and the Sentry DSN. Rotating means a new `backend-env` version
  plus a redeploy — the same flow as Phase 1.

Findings from Phase 4 in particular belong here.

## Decisions already made (do not re-litigate)

- **Keep the VM + Docker + ACR Basic.** Container Apps is not being pursued. The static
  public IP stays because a dynamic one would change on every sleep/wake cycle.
- **Sleep/wake is driven from local scripts** that wrap
  `.github/scripts/azure-control-plane.sh`. The GitHub workflows and the hourly watchdog
  remain as the audited path and the backstop.
- **Deepgram, Pinecone/RAG, mentor sampling, image generation, LangSmith tracing and
  Razorpay test mode are all ON in production.** Sentry stays off. Rationale and the
  per-setting table are in `MASTER_PLAN.md`.
- **End-to-end testing runs against live Azure**, scripted plus a manual browser pass.
