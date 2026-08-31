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

Rules that apply to every phase are in the *Ground rules* section of `MASTER_PLAN.md`.
The short version: never push to `main`, sign off every commit with `git commit -s`, no
AI attribution in commits or PRs, and never commit a real secret.

## Phase status

| # | Phase | Branch | PR | Status | Date | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | Tracking files | `docs/azure-master-plan` | [#208](https://github.com/orbin123/lingos-ai/pull/208) | DONE | 2026-08-31 | `docs/azure/` had to be un-ignored in `.gitignore` |
| 1 | Production environment file | `chore/azure-prod-env-template` | [#209](https://github.com/orbin123/lingos-ai/pull/209) | CODE DONE, **OWNER STEP PENDING** | 2026-08-31 | Template and `scripts/build-prod-env.sh` are merged. The owner must still run `init` / `edit` / `check` / `upload` to put real keys in Key Vault. **Phase 3 is blocked until that upload happens.** |
| 2 | External credential verification | `feat/external-service-healthcheck` | [#210](https://github.com/orbin123/lingos-ai/pull/210) | DONE (locally) | 2026-08-31 | 9 pass, 2 correctly skip locally. The Azure Blob and PostgreSQL probes only run for real **on the VM**, in Phase 3 |
| 3 | Wake, deploy, verify live | `fix/azure-live-bringup` | — | **BLOCKED** | — | Waiting on the Phase 1 owner step. This is the next phase to run once `backend-env` holds real keys |
| 4 | End-to-end functional verification | `test/azure-e2e-smoke` | — | NOT STARTED | — | Chat flow, mentor note, stats/streak dates |
| 5 | Local sleep/wake control | `feat/local-azure-lifecycle-scripts` | [#211](https://github.com/orbin123/lingos-ai/pull/211) | DONE | 2026-08-31 | Done out of order because Phase 3 is blocked. `azure-status.sh` verified against live Azure; `azure-up.sh` / `azure-down.sh` get their first real run in Phase 3 |
| 6 | Docs reconciliation + cost guard | `docs/azure-reconcile` | — | NOT STARTED | — | Raise the $1/month budget; fix the stale docs |

## What the owner has to do next

Phases 0, 1, 2 and 5 are merged. Everything that can be done without live secrets is done.
The one thing blocking Phase 3, and therefore Phase 4:

```
scripts/build-prod-env.sh init      # pre-fills every non-secret value
scripts/build-prod-env.sh edit      # fill the 13 secrets by hand
scripts/build-prod-env.sh check     # both gates must pass
scripts/build-prod-env.sh upload    # stores it in Key Vault, then shreds the local copy
```

Twelve of the thirteen values can be copied from the repo-root `.env`. Generate fresh
values for `JWT_SECRET` and `OTP_HASHING_SECRET` with `openssl rand -hex 32`.

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
- **Phase 1 leaves one manual step for the owner.** The repository now carries the
  template and the build/validate script, but the file with real secrets must be produced
  and uploaded by hand: `scripts/build-prod-env.sh init`, fill the 13 secret values,
  then `check` and `upload`. Phase 3 cannot start until that upload has happened.

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
