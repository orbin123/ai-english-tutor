# Azure CI/CD and cold-state operations

This runbook covers migration work package PR 7 only. Every Azure cloud job is
disabled unless the repository variable `AZURE_AUTOMATION_ENABLED` has the
exact value `true`. Keep it `false` until the owner separately provisions and
approves Azure infrastructure, identity/RBAC, GitHub configuration, and the VM
host contract, and explicitly approves the production rehearsal. This
repository does not create any of those external objects and contains no Azure
client secret, database credential, private key, or other credential value.

The frozen AWS workflow and Terraform remain recovery material.

## Workflows and triggers

| Workflow | Trigger | Production boundary |
| --- | --- | --- |
| `azure-deploy.yml` | matching push to `main`, or manual dispatch from `main` | tests first; cloud job requires the activation variable, waits for the protected `production` Environment, and requires an active live window |
| `azure-wake.yml` | manual dispatch from `main` | activation variable and protected `production` Environment; `active_hours` defaults to 6 and is rejected outside 1–24 |
| `azure-sleep.yml` | manual dispatch from `main` | activation variable and protected `production` Environment; repeated runs are safe |
| `azure-sleep-watchdog.yml` | hourly at minute 17 on the default branch | activation variable and autonomous OIDC trust; no reviewer wait, so PostgreSQL's forced seven-day restart is stopped promptly |

Deploy, wake, and manual sleep share the `azure-production-operations`
concurrency group. The watchdog uses `azure-production-watchdog` so a deployment
waiting for Environment approval cannot block the hourly safety net. Its first
decision is always the live-window tag; a concurrent wake that loses this rare
race fails its state verification, cleans up, and can be retried safely. No
Azure workflow runs on a pull request.

## Human-owned GitHub and Entra setup

Do not perform these steps without the owner's explicit approval.

1. Create a GitHub Environment named `production` with required reviewers,
   prevention of self-review where the repository plan supports it, and a
   deployment-branch rule allowing only `main`. Add the Environment-only
   non-secret variable `AZURE_PRODUCTION_ENVIRONMENT_GUARD` with the exact value
   `reviewed-and-protected`; protected jobs fail before OIDC login if it is
   absent. Do not define this guard at repository scope.
2. Add these **non-secret repository variables**:

   - `AZURE_AUTOMATION_ENABLED` (set to `false` during setup; change to the
     exact value `true` only after every other external prerequisite is complete
     and the rehearsal is explicitly approved)
   - `AZURE_CLIENT_ID`
   - `AZURE_TENANT_ID`
   - `AZURE_SUBSCRIPTION_ID`
   - `AZURE_ACR_NAME`
   - `AZURE_POSTGRES_SERVER`
   - `AZURE_API_BASE_URL` (the HTTPS API origin, without credentials)

   The resource group (`rg-lingosai-prod`), VM (`vm-lingosai-prod`), and image
   repository (`lingosai-backend`) are fixed in reviewed code rather than
   supplied as mutable workflow inputs.
3. Add GitHub OIDC federated credentials to the approved Entra identity for
   both exact subjects below, with audience `api://AzureADTokenExchange`:

   - `repo:orbin123/lingos-ai:environment:production`
   - `repo:orbin123/lingos-ai:ref:refs/heads/main`

   The first subject covers reviewer-gated deploy/wake/sleep jobs. The second
   exists only so the default-branch scheduled watchdog can stop compute without
   waiting for an approval that would defeat the safety net. Do not add wildcard
   repository, branch, pull-request, or environment subjects.
4. At the exact production resource-group/registry scopes, grant the identity a
   reviewed custom role containing only the operations used here:

   - read the resource group and read/merge its tags;
   - read VM instance state, start, deallocate, and invoke Run Command;
   - read/start/stop the one PostgreSQL Flexible Server;
   - read the one ACR and push/read repository content.

   Prefer a custom control-plane role plus ACR's narrow push role. Do not grant
   Owner, User Access Administrator, subscription-wide Contributor, role
   assignment mutation, resource creation/deletion, networking changes, Key
   Vault secret mutation, or Terraform/state access. The VM managed identity,
   not GitHub, retains the existing `AcrPull` assignment.
5. Enable normal GitHub Actions failure notifications for the repository. A
   watchdog authentication/stop failure deliberately fails the run and emits
   error annotations; no new paid alerting service or messaging credential is
   introduced.

The identifiers above are not credentials, but they should still be managed as
reviewed configuration. A missing activation variable, `false`, `TRUE`, or any
value other than the lowercase string `true` skips every Azure cloud job. The
deploy workflow still runs its local backend test job on matching pushes. Never
replace OIDC with a client secret.

## VM host contract

Before any workflow is approved, configure and verify the single VM with the
reviewed, idempotent operations in
[`AZURE_VM_HOST_BOOTSTRAP.md`](./AZURE_VM_HOST_BOOTSTRAP.md):

- the Azure VM agent, Azure CLI, Docker, and `curl` are installed;
- the system-assigned VM identity can pull from only the approved ACR;
- `/etc/lingosai/backend.env` exists, is `root:root`, has mode `0600` or
  stricter, and is populated from the approved secret path outside GitHub;
- Caddy proxies the API to `127.0.0.1:8000`, supports WebSockets/TLS, and serves
  a maintenance response while `/var/lib/lingosai/maintenance` exists;
- Docker starts on boot; the backend container uses `--restart unless-stopped`,
  one worker, host networking, a 768 MiB memory limit, and bounded local logs;
- the application managed-identity database login, Key Vault access, Blob
  access, CORS, OAuth/payment callbacks, DNS, and media privacy have passed their
  separate gates. The database gate and credential-free runtime URL are defined
  in [`AZURE_POSTGRES_MANAGED_IDENTITY.md`](./AZURE_POSTGRES_MANAGED_IDENTITY.md).
- for the initial fresh database only, the owner-approved administrator is
  created and verified through the fail-closed process in
  [`AZURE_FRESH_START_ADMIN_BOOTSTRAP.md`](./AZURE_FRESH_START_ADMIN_BOOTSTRAP.md)
  before public application traffic is allowed; this is a separately approved
  one-time operation, not an automatic deployment step.

The bootstrap accepts only the API hostname, Key Vault name, and secret name.
It reads the environment directly with the VM identity, validates the Azure
production invariants, writes it as `root:root` mode `0600`, and leaves the
maintenance marker in place. The verifier additionally proves Key Vault/ACR
identity access and PostgreSQL network reachability without printing a secret
or token. Neither operation deploys the backend or removes maintenance mode.

The workflows never write the environment file and never print it. VM Run
Command output must still be treated as operationally sensitive and retained
only under the repository's approved Actions-log policy.

## Operating sequence

1. After the production stack, scoped RBAC, host contract, and rehearsal plan
   are approved, set `AZURE_AUTOMATION_ENABLED` to `true` immediately before
   the production rehearsal. Set it back to `false` if the rehearsal fails;
   leave it enabled afterward only with explicit production activation
   approval. Treat this variable as the final production activation control.
2. Run **Azure wake** roughly 30 minutes before the approved session. Use the
   default six-hour window unless a shorter reviewed window is sufficient.
3. Confirm the workflow reports PostgreSQL `Ready`, VM
   `PowerState/running`, and successful public `/health/live` and
   `/health/ready` checks. On the one-time initial deployment, no digest exists
   yet: wake reports `Existing deployment restored: false`, verifies the Azure
   compute states, and deliberately skips API health so the protected deploy can
   create the first container. Do not use that state for an interview.
4. Approve a pending **Azure backend deploy** only if a deployment is intended.
   It runs locked backend checks, reuses an existing full-commit tag or builds
   and pushes it once, verifies the ACR digest, and deploys only
   `registry/repository@sha256:...`.
5. Perform the separately approved product smoke checks (login, a read-only API
   request, WebSocket, and public/private media). Those calls can consume
   external provider quota and are not automated here.
6. Run **Azure sleep** immediately after the session. Confirm the final states
   are VM `PowerState/deallocated` and PostgreSQL `Stopped`.

The live-window timestamp is stored in the resource-group tag
`lingosai-active-until`. Wake writes the bounded future UTC time before it starts
compute. Sleep expires it before shutdown, so a partial stop is retried by the
next watchdog run. The hourly watchdog treats a missing or malformed tag as
expired. This also limits the compute exposure caused when Azure automatically
starts a stopped PostgreSQL Flexible Server after seven days.

## Failure and rollback behavior

- Wake failure: after a successful OIDC login, the workflow expires the window,
  attempts a graceful application stop, deallocates/verifies the VM, and then
  stops/verifies PostgreSQL.
- Sleep/watchdog partial failure: the live window remains expired, the workflow
  fails visibly, and the next watchdog run retries the cold state.
- Deployment failure in the VM: the script attempts to restore the previously
  recorded digest and keeps the maintenance marker if no healthy image can be
  restored.
- External health-check failure: the workflow invokes the explicit rollback
  mode for the previous digest and still fails the deployment run.
- Database migrations are forward-only and are **never** automatically
  reverted. Schema changes must use expand/contract compatibility so the prior
  application digest remains usable.

To roll back this PR before external setup, revert its Git commit. After a
successful application deployment, dispatch from `main` only after wake and use
the recorded rollback digest through the reviewed workflow; do not retag an
image. Removing Azure infrastructure, identities, assignments, GitHub
configuration, DNS, secrets, or data is a separate approved operation.

## Security and cost caveats

- A protected Environment gates human-initiated production changes, while the
  scheduled watchdog necessarily relies on its exact default-branch OIDC
  subject. A compromised merged workflow could use the identity, so branch
  protection and code review remain mandatory.
- Keep `AZURE_AUTOMATION_ENABLED=false` until the production stack and all
  external controls are approved. This prevents OIDC login, Environment review
  requests, compute starts, and scheduled stop attempts after an early merge.
- The workflow identity can start billable compute. Its custom role and
  resource scope must be independently reviewed before federation is enabled.
- VM deallocation and PostgreSQL stop do not remove managed disks, public IP,
  database storage/backups, Blob data, ACR data, or Key Vault operations.
- GitHub schedules can be delayed or disabled. Continue the portal/free-meter
  review and the separately approved VM auto-shutdown safeguard described in
  `AZURE_ZERO_COST_MIGRATION.md`.
- An hourly watchdog normally limits a forced PostgreSQL restart to about one
  additional hour, but it is a safety net rather than a billing guarantee.
- ACR images are not pruned by these workflows. Retain only the reviewed three
  deployable digests through a separate, approved cleanup operation.
