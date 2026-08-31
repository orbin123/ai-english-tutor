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

Note the file keeps `OPENAI_CHAT_MODEL=gpt-4o-mini`, not the `gpt-4.1-mini` the repo
template suggests. That is the owner's value and was left alone.

### One thing to remember about `EMAIL_FROM`

It is written **unquoted** (`EMAIL_FROM=LingosAI <noreply@lingosai.com>`). That is correct
for Docker's `--env-file`, which does not strip quotes — quoting it would make the quote
characters part of the address. The side effect is that the file cannot be `source`d in a
shell, because `<` reads as a redirect. Load it with a parser, not `source`.

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
