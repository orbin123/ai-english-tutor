# Live Azure status (CLI, 31 August 2026)

Written from `az` and `gh` signed in as `orbinsunny9495@gmail.com` on subscription
`Azure subscription 1` (`e231ab32-…`, `centralindia`).

This replaces the 29 August snapshot, which was wrong in three material ways: it recorded
the ACR as Standard SKU, said `api.lingosai.com` did not exist, and said the application
had never been installed. All three have since changed or were misread.

The go-live plan built on this state is [MASTER_PLAN.md](./MASTER_PLAN.md); progress is
tracked in [AGENT_WORK.md](./AGENT_WORK.md).

---

## Verified resource state

| Resource | Name | Fact from CLI |
| --- | --- | --- |
| Resource group | `rg-lingosai-prod` | `centralindia`, Succeeded |
| Terraform state | `rg-lingosai-tfstate` / `stlingosaitfe231` | Exists |
| VM | `vm-lingosai-prod` | `Standard_B2ats_v2` (2 vCPU / 1 GiB RAM), **deallocated** |
| Public IP | `pip-lingosai-prod` | Standard SKU, **Static**, `20.219.52.248` |
| PostgreSQL | `psql-lingosai-e231` | `Standard_B1ms`, PG 16, 32 GiB, Entra-only auth, **Stopped** |
| Postgres firewall | `allow-vm-only` | Only `20.219.52.248` |
| ACR | `acrlingosaie231` | **Basic** SKU, admin disabled, repo `lingosai-backend` |
| Blob | `stlingosaipube231` | `public-media` |
| Blob | `stlingosaiprive231` | `learner-media`, `internal-media` |
| Key Vault | `kv-lingosai-e231` | Contains one secret: `backend-env` |
| Cost budget | `budget-lingosai-prod` | **$1/month** — unrealistically low, raised in Phase 6 |
| Speech | `lingosai-speech` in `lingosai-rg` / `eastus` | F0 free tier, separate resource group |
| Redis | — | None, and none needed (`AI_RATE_LIMIT_BACKEND=memory`) |
| Container Apps | — | Not used. `Microsoft.App` stays unregistered |

The VM and PostgreSQL being stopped is the **normal resting state**, not a fault. The
environment is woken deliberately and put back to sleep to stay inside the 750-hour
monthly VM allowance.

## DNS

| Host | Result |
| --- | --- |
| `lingosai.com` | Resolves (Vercel) |
| `www.lingosai.com` | Resolves (Vercel) |
| `api.lingosai.com` | **Resolves to `20.219.52.248`** — the A record exists |

## Automation state

| Item | State |
| --- | --- |
| GitHub variable `AZURE_AUTOMATION_ENABLED` | **`true`** |
| GitHub Environment `production` | Exists, reviewer-gated |
| `AZURE_CLIENT_ID` / `TENANT_ID` / `SUBSCRIPTION_ID` / `ACR_NAME` / `POSTGRES_SERVER` | All set as repository variables |
| Last `Azure backend deploy` run | **success**, 30 August 2026, on `main` |
| `Azure sleep watchdog` | Running hourly, succeeding |
| Local `az` CLI | Authenticated |
| Local `gh` CLI | Authenticated as `orbin123` |

OIDC federation works; deployment is not blocked on credentials.

## Cost

| Item | Cost |
| --- | --- |
| VM `B2ats_v2` | Free within the 750 h/month allowance (to 18 June 2027) |
| PostgreSQL `B1ms` + 32 GiB | Free within the 12-month allowance |
| Blob, Key Vault | Effectively free at this volume |
| Static public IP | ~$3.6/month |
| ACR Basic | ~$5/month |
| **Steady-state floor** | ≈ **$9/month (~₹800)** |

The static IP is **required**: a dynamic address is released on deallocation, so it would
change on every wake and break both DNS and the Let's Encrypt certificate. ACR Basic is
retained because it preserves digest-pinned deploys and one-command rollback, which is
worth more than $5/month on a 1 GiB VM where building images locally is impractical.

## Container Apps

Not pursued. The VM path is provisioned, deployed, and working. Standing up Container Apps
would mean registering `Microsoft.App` and paying a second compute meter for no gain.
