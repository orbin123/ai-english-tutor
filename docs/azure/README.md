# Azure production docs

Start here:

| File | What it is |
| --- | --- |
| [AGENT_WORK.md](./AGENT_WORK.md) | **Read this first.** Phase-by-phase progress log — which phases are done and where to resume |
| [MASTER_PLAN.md](./MASTER_PLAN.md) | The full go-live plan: seven phases, one PR each, with the exact commands |
| [LIVE_STATUS.md](./LIVE_STATUS.md) | The verified state of the Azure subscription, written from `az` output |

Operational detail lives one level up: the CI/CD contract in
[../AZURE_CICD_RUNBOOK.md](../AZURE_CICD_RUNBOOK.md), the host contract in
[../AZURE_VM_HOST_BOOTSTRAP.md](../AZURE_VM_HOST_BOOTSTRAP.md), and the managed-identity
database contract in
[../AZURE_POSTGRES_MANAGED_IDENTITY.md](../AZURE_POSTGRES_MANAGED_IDENTITY.md).

The production shape is a **single VM** running the backend container behind Caddy, with
Azure Database for PostgreSQL, Blob storage, Key Vault, and ACR. Container Apps is not
used and `Microsoft.App` stays unregistered.
