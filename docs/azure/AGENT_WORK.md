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
| 0 | Tracking files | `docs/azure-master-plan` | — | IN PROGRESS | 2026-08-31 | Creates this file, `MASTER_PLAN.md`, and corrects `LIVE_STATUS.md` |
| 1 | Production environment file | `chore/azure-prod-env-template` | — | NOT STARTED | — | Highest-risk phase. Real keys are filled in by the owner and never committed |
| 2 | External credential verification | `feat/external-service-healthcheck` | — | NOT STARTED | — | Must pass **on the VM**, not just locally |
| 3 | Wake, deploy, verify live | `fix/azure-live-bringup` | — | NOT STARTED | — | Needs Phase 1 uploaded to Key Vault first |
| 4 | End-to-end functional verification | `test/azure-e2e-smoke` | — | NOT STARTED | — | Chat flow, mentor note, stats/streak dates |
| 5 | Local sleep/wake control | `feat/local-azure-lifecycle-scripts` | — | NOT STARTED | — | `azure-up.sh` / `azure-down.sh` / `azure-status.sh` |
| 6 | Docs reconciliation + cost guard | `docs/azure-reconcile` | — | NOT STARTED | — | Raise the $1/month budget; fix the stale docs |

## Open issues

Nothing recorded yet. Findings from Phase 4 in particular belong here.

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
