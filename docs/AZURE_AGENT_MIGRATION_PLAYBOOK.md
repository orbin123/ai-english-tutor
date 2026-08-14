# LingoAI Azure Migration: Coding-Agent Playbook

**Companion document:** [`AZURE_ZERO_COST_MIGRATION.md`](./AZURE_ZERO_COST_MIGRATION.md)
**Purpose:** Turn the approved architecture report into small, reviewable coding-agent tasks without giving an agent unsafe production access.

## The operating principle

Do not ask one coding agent to “migrate everything from AWS to Azure.” That request combines code refactoring, infrastructure creation, identity, data recovery, production deployment, DNS, billing, and irreversible cleanup. Even a capable agent will have too many opportunities to make a locally reasonable but globally unsafe choice.

Use the migration report as the architectural contract, then execute it as a sequence of independently reviewed pull requests and explicit production gates:

```text
human decisions and backups
        ↓
AWS deployment safety PR
        ↓
application portability PRs
        ↓
Azure Terraform plan-only PR
        ↓
human review of SKU and cost plan
        ↓
non-production provisioning and validation
        ↓
data-recovery rehearsal
        ↓
production provisioning and cutover
        ↓
observed meter validation
        ↓
AWS code and credential removal
```

The coding agent can perform analysis, local edits, tests, Terraform validation, and reviewed automation work. It should not independently make cost-bearing purchases, change DNS, rotate production secrets, delete AWS recovery sources, apply production Terraform, restore/overwrite production data, or merge a production-deploying pull request.

## Before opening the coding agent

### Human-owned prerequisites

Resolve or explicitly record each item before implementation begins:

- The exact Azure subscription ID, offer type, free-benefit expiry, eligible region, and eligible SKUs.
- Whether the goal is “no AWS account dependency,” “no data hosted on AWS,” or “only zero Azure invoice.” These differ because Pinecone may host an index in AWS and external providers remain.
- Whether production RDS/S3/Pinecone data is recoverable. Obtain a dump/export/inventory or explicitly approve a fresh start.
- The selected frontend path: keep Vercel for Phase 1,
- The public API hostname and Namecheap ownership.
- A person who can approve Azure subscription changes, GitHub environments, OAuth callbacks, Razorpay webhooks, and DNS.
- The exact interview/demo availability requirement and acceptable warm-up/downtime.

Do not put secret values in the migration report, `AGENTS.md`, issue descriptions, prompts, terminal output, screenshots, or Git history.

### Local workstation setup

Install only the tools required for the current phase:

```bash
brew install azure-cli
brew tap hashicorp/tap
brew install hashicorp/tap/terraform
```

The repository already expects:

- Git;
- Python 3.11+ and `uv`;
- Node.js/npm;
- Docker for container builds and local PostgreSQL/Redis testing.

Authenticate Azure under the human operator's account for read-only discovery at first:

```bash
az login
az account list --output table
az account set --subscription "<subscription-id>"
az account show --output table
```

Never paste an Azure password, service-principal secret, storage key, database password, or OpenAI key into the agent chat. Prefer browser login, GitHub OIDC, and managed identities. If a local command needs a secret, enter it outside the agent-visible transcript or use a secret manager/keychain.

### Repository setup

Before any agent edit:

1. Ensure the working tree contains no unrelated changes.
2. Preserve the current migration reports in a signed-off commit or dedicated branch.
3. Create a fresh branch or Codex worktree for every migration work package.
4. Verify Git author identity:

   ```bash
   git config user.name
   git config user.email
   ```

   This repository requires `Orbin Sunny <91816511+orbin123@users.noreply.github.com>` and DCO sign-off.
5. Never work directly on `main` and never give an agent permission to merge a PR automatically.

## How to configure the coding agent

### Add durable repository instructions

Create a root `AGENTS.md` before asking multiple agents to work on the repository. `CLAUDE.md` contains useful architecture, commands, and conventions, but Codex loads `AGENTS.md` automatically. Keep `AGENTS.md` concise and point to the two migration documents for detail.

The root instructions should include:

- repository layout and exact build/test commands from `CLAUDE.md`;
- “branch and PR only; never push or merge `main`”;
- the DCO/sign-off identity requirement;
- “never execute `terraform apply` or `destroy` without explicit approval”;
- “never change DNS, Azure subscription settings, GitHub secrets/environments, OAuth callbacks, payment webhooks, or production data without explicit approval”;
- “never reveal or commit credentials, state, database dumps, or `.env` files”;
- approved Azure resource types, SKUs, quantities, and region as defined in the migration report;
- the code verification commands and acceptance gates;
- “AWS source resources are recovery evidence until the human approves removal.”

Use nested `AGENTS.md` files only where the commands or rules genuinely differ—for example `infra/azure/AGENTS.md` for plan-only Terraform constraints. More specific files override broader guidance.

### Permission ladder

Use least privilege per phase rather than one permanently powerful setup.

| Phase | Filesystem | Network | Azure identity | Agent may do | Agent must not do |
|---|---|---|---|---|---|
| Audit/plan | Read-only | Official docs as needed | None or Azure Reader | Inspect and report | Edit, deploy, or change cloud state |
| Code refactor | Workspace write | Package registries/docs only | None | Edit code/tests/docs; run local checks | Cloud mutation, push, merge |
| Terraform authoring | Workspace write | Provider/docs access | Azure Reader | Query SKUs; `fmt`, `validate`, `plan` against reviewed scope | `apply`, import, destroy, role assignment |
| Test provisioning | Workspace write | Azure/GitHub access | Custom least-privilege non-prod identity | Apply only to an isolated approved resource group after human approval | Subscription-wide policy/RBAC, production data/DNS |
| Production apply | Workspace write | Azure/GitHub access | Time-bounded custom deployment identity | Run an already reviewed saved plan after explicit approval | Ad-lib resources, change SKU/plan, destroy data |
| Cutover | Workspace write | Azure/GitHub/DNS providers | Separate task-specific identities | Run approved runbook step by step | Combine DNS, data deletion, and cleanup into an autonomous run |

Start with the agent's normal “Ask for approval”/workspace-write mode. Do not use full-machine or unrestricted production permissions for implementation. Official Codex guidance recommends tight defaults and explicit approval for external, destructive, costly, or scope-expanding actions.

### Azure identities—not your personal Owner session

Use different identities for different jobs:

1. **Discovery identity:** Reader at the subscription or resource-group scope. It can inspect regions, SKUs, meters, and existing state but cannot create anything.
2. **Terraform plan identity:** Reader plus the minimum data access needed to read the remote state. A plan does not require permission to make every proposed mutation.
3. **Test deploy identity:** A custom role scoped only to a disposable test resource group. Do not grant `Owner`; avoid broad `Contributor` if a custom role suffices.
4. **Production deploy identity:** GitHub OIDC identity scoped to `rg-lingosai-prod`, with only the resource actions required by the approved Terraform and deployment workflows. Grant RBAC-assignment ability separately and temporarily if Terraform must create role assignments.
5. **Runtime identity:** VM managed identity with narrow roles such as `AcrPull`, Blob container access, and Key Vault secret-read access. It must not have general Azure Contributor permission.

The coding agent does not need the Azure Portal UI password. It needs the Azure CLI executable and an already-authenticated, appropriately scoped identity—or an OIDC workflow whose permissions are code-reviewed.

### Network access

During normal code refactoring, allow only destinations actually needed, such as official package registries and documentation. During Terraform work, add Azure management/login endpoints and the Terraform provider registry. Avoid unrestricted internet access when a scoped allowlist works.

Production database and VM access should not be reachable merely because the local agent has general network access. Use Azure control-plane operations, exact firewall rules, and time-bounded access.

## How to prompt each task

Each prompt should contain four parts: goal, context, constraints, and definition of done. Refer to exact files rather than pasting the entire migration report into every prompt.

Use this template:

```text
Goal
Implement <one bounded migration outcome>.

Context
- Read AGENTS.md.
- Read docs/AZURE_ZERO_COST_MIGRATION.md sections <names>.
- Relevant files: <paths>.
- Base branch/issue: <identifier>.

Constraints
- Do not perform cloud mutations, push, merge, change DNS/secrets, or touch
  production data.
- Preserve current behavior unless the task explicitly changes it.
- Do not add a service or SKU not approved by the migration report.
- Keep AWS recovery paths until their dedicated removal phase.
- Ask before any destructive, external, or cost-bearing action.

Done when
- <observable behavior>.
- <specific tests/checks> pass.
- The diff contains only this work package.
- New configuration and rollback behavior are documented.
- Finish with a risk summary, commands run, results, and unresolved decisions.
```

Do not use prompts such as “make it production ready,” “do whatever is necessary,” or “deploy everything.” They provide no stopping boundary.

## Migration work packages

### PR 0 — Preserve the plan and agent rules

**Goal:** Commit the migration documents and root `AGENTS.md`; update stale deployment guidance in `CLAUDE.md` only enough to reflect the current transition state.

**Cloud access:** None.
**Gate:** Human confirms architecture choices and the permissions/approval rules.

### PR 1 — Neutralize AWS continuous deployment

This PR must land before any other migration PR because `.github/workflows/deploy.yml` still runs on pushes to `main`.

**Goal:** Prevent merges from invoking AWS while preserving the old workflow as reviewable recovery history.

Safer implementation options:

- remove the `push` trigger and retain only a deliberately gated manual recovery trigger; or
- rename/archive the workflow outside `.github/workflows` and add a non-deploying placeholder documenting the migration freeze.

Also update `CLAUDE.md`, because it currently states that every merge auto-deploys AWS production.

**Do not:** revoke/delete source data or AWS recovery access as part of this PR.
**Gate:** Inspect the Actions workflow graph and confirm a push to `main` has no AWS deployment path.

### PR 2 — Cost and privacy guardrails

**Goal:** Disable production AI debug routes, add upload-size/duration limits, add concurrency protection, correct CORS configuration, and make database pool limits configurable.

**Cloud access:** None.
**Verification:** backend unit/integration tests, Ruff, Mypy, OpenAPI regeneration/drift check, and targeted tests proving oversized uploads and unauthenticated debug calls fail.

This comes early because the same defects are risky on any cloud.

### PR 3 — Azure Blob adapter

**Goal:** Add an Azure Blob implementation behind `IBlobStorage`, managed-identity authentication, explicit `public/private/internal` visibility, and shared contract tests.

**Cloud access:** None for initial adapter; Azurite or mocked SDK only.
**Do not:** delete S3 support yet; retain it as a source-migration/recovery path.
**Gate:** storage contract tests verify anonymous/public behavior, authorization of learner media, content types, direct object addressing, deletion, and no container listing in request paths.

### PR 4 — Redis-optional single-worker mode

**Goal:** Make Redis optional, deliberately select the in-memory limiter in zero-cost production, and make readiness conditional on configured dependencies.

**Cloud access:** None.
**Gate:** tests pass with Redis configured and absent; documentation states one-worker limitation.

Do not remove the Python Redis package until imports and all test paths prove it is unused.

### PR 5 — Azure production configuration

**Goal:** Add Azure environment settings and production validation without secrets; update `.env.production.example` and startup checks.

**Cloud access:** None.
**Gate:** configuration tests reject public private-data containers, excess workers/connections, missing production origins, and unsupported storage backends.

### PR 6 — Azure Terraform, plan only

**Goal:** Create `infra/azure` with bootstrap and one minimal production root exactly matching the approved architecture.

**Agent permissions:** workspace write and Azure Reader.
**Allowed commands:** `terraform fmt`, `terraform init`, `terraform validate`, lint/security checks, and `terraform plan` after backend/discovery setup.
**Forbidden:** `terraform apply`, `destroy`, import, state mutation, subscription changes, or broad RBAC.

**Gate:** Human reviews the complete saved plan line by line. The plan must contain only:

- approved resource groups/policies/budget alerts;
- one eligible VM, one P6 OS disk, one static public IP;
- one B1ms PostgreSQL server at exactly 32 GiB, HA/autogrow/geo backup disabled;
- approved Blob accounts/containers/lifecycle policies;
- one ACR, one Key Vault, and narrow managed identities/RBAC;
- no load balancer, NAT Gateway, Bastion, VPN, private endpoint, Azure DNS, Log Analytics workspace, Application Insights ingestion, Defender paid plan, or Marketplace product.

### PR 7 — CI/CD, wake, sleep, and watchdog

**Goal:** Add GitHub OIDC authentication, build/push/deploy-by-digest, manual `azure-wake.yml`, manual `azure-sleep.yml`, and scheduled `azure-sleep-watchdog.yml`.

**Cloud access during authoring:** Reader only.
**Gate:** workflows are linted, permissions are explicit, production uses a GitHub Environment approval, `workflow_dispatch` inputs are bounded, sleep is idempotent, VM uses `deallocate`, and the PostgreSQL seven-day auto-start is handled.

Do not add Azure client secrets. The workflow must use OIDC.

### PR 8 — Frontend offline/warming experience

**Goal:** Keep Vercel initially and add a clear offline/warming state when the API is asleep, without treating every API error as sleep.

**Cloud access:** None.
**Gate:** frontend lint, TypeScript, tests, build, and browser test against offline/warming/live API simulations.

### Gate A — Human data-recovery decision

**Resolved 14 August 2026:** the owner approved a fresh Azure database with no
AWS data restoration. AWS resources, code, credentials, and data remain recovery
evidence until their separately approved removal phase; this decision does not
authorize access to or deletion of them.

The accepted Gate A choices were:

- verified RDS dump and S3 inventory/export, with reconciliation expectations; or
- written approval that Azure begins as a fresh environment.

The next code-only package is the fail-closed, single-account administrator
bootstrap documented in
[`AZURE_FRESH_START_ADMIN_BOOTSTRAP.md`](./AZURE_FRESH_START_ADMIN_BOOTSTRAP.md).
It receives identity and credential material only at execution time, assigns
exactly `admin` and `super_admin` (never `learner`), is idempotent before
activation, and refuses an unexpected user, runtime row, schema, or role
catalog. Its merge does not authorize running it against Azure.

The agent may write and test migration scripts against synthetic data. It must not point them at production without explicit approval.

The local-only inventory and reconciliation rehearsal is documented in
[`AZURE_DATA_MIGRATION_REHEARSAL.md`](./AZURE_DATA_MIGRATION_REHEARSAL.md). Its
successful completion does not resolve Gate A or authorize production access.

### Gate B — Test provisioning

Use an approved isolated test resource group only long enough to validate Terraform, identity, container startup, Blob privacy, and PostgreSQL connectivity. Because the account's hours/storage are aggregate, destroy the test stack after evidence is captured and verify no disks/IPs/restored databases remain.

Do not call a test stack “free” merely because it is temporary. A second database/VM can still overlap the same monthly meter.

### Gate C — Production provisioning

The human reviews:

- the exact subscription and region;
- Terraform saved plan and resource count;
- every SKU, size, redundancy, retention, and public-access setting;
- projected/free-meter mapping;
- identities and scopes;
- rollback and destroy plans.

Only then may an agent run the saved production apply. If the plan changes after approval, stop and request a new approval.

### Gate D — Data migration rehearsal and cutover

Keep database restore, media transfer, smoke testing, and DNS cutover as separate commands with evidence after each. The agent must stop if counts/checksums, Alembic state, private-media authorization, or health checks differ from the approved thresholds.

DNS, OAuth, Razorpay webhook, and production frontend origin changes are human-approved external mutations. Do not bundle them with source deletion.

### Final PR — AWS runtime removal

Only after Azure has passed cutover and an observation period:

- remove Boto3/S3 and SES runtime code/config/tests;
- remove obsolete AWS Terraform/workflow code after preserving needed history;
- remove AWS GitHub variables/secrets and external callbacks;
- rebuild Pinecone in an Azure-backed location or remove it if “no AWS-hosted data” is required.

AWS source destruction is a separate human-approved operation after recovery evidence and retention requirements are satisfied.

## Verification matrix agents must report

Every implementation task must end with a structured handoff:

| Evidence | Required content |
|---|---|
| Scope | Files changed and why each belongs to the task |
| Tests | Exact commands, exit status, and skipped checks with reasons |
| Security | Secrets/RBAC/public access/privacy effects |
| Cost | Resources/providers/operations introduced and their approved meter |
| Data | Schema, migration, retention, or deletion effects |
| Rollback | How to revert application code and what cannot be rolled back |
| Manual steps | Portal/GitHub/DNS/provider action still owned by the human |
| Open risks | Unverified assumptions and blockers |

Repository-wide verification before a merge should include, as applicable:

```bash
# Backend
cd backend
uv sync --frozen
uv run ruff check app tests
uv run ruff format --check app tests
uv run mypy app
uv run python -m pytest tests/unit -q
uv run python -m pytest tests/integration -q
uv run python scripts/export_openapi.py
git diff --exit-code -- openapi.json

# Frontend
cd frontend
npm ci
npm run lint
npx tsc --noEmit
npm test
npm run test:coverage
npm run build

# Terraform
cd infra/azure/environments/prod
terraform fmt -check -recursive ../../..
terraform init
terraform validate
terraform plan -out=tfplan
terraform show -no-color tfplan > tfplan.txt
```

Do not commit `tfplan`, `tfplan.txt`, Terraform state, `.terraform/`, database dumps, dependency caches, or secrets. The Terraform commands are illustrative until the new folder exists; use the paths and lockfile policy established by its PR.

## Production stop conditions

An agent must stop and ask rather than improvise if any of these occur:

- the active Azure subscription or region differs from the approved value;
- an exact free-eligible SKU is unavailable;
- Terraform proposes a resource not listed in the approved architecture;
- Azure estimates/Portal meters show possible nonzero cost;
- `terraform plan` changes after human approval;
- the source database/media inventory is unavailable or reconciliation fails;
- a migration contains destructive SQL, table rewrites, or irreversible data loss;
- the destination database exceeds 28 GiB or Blob data exceeds 4 GiB;
- an identity needs subscription-wide Owner/User Access Administrator;
- a secret would appear in state, logs, workflow output, or Git;
- TLS, OAuth, payment webhooks, CORS, WebSockets, private media, readiness, or rollback fail;
- the AWS source would be deleted before recovery acceptance;
- a command targets `main`, production DNS, or production data without the matching gate approval.

## Suggested agent chats

Use one chat/worktree per coherent outcome:

1. Migration safety and `AGENTS.md`.
2. Application cost/privacy guardrails.
3. Azure Blob adapter.
4. Redis-optional mode.
5. Azure configuration.
6. Azure Terraform authoring.
7. CI/CD and start/stop automation.
8. Frontend offline experience.
9. Migration-script rehearsal.
10. Production provisioning/cutover runbook execution.
11. Post-cutover AWS removal.

Do not run agents concurrently on overlapping files. Parallelize only bounded, read-only research or disjoint worktrees, and integrate through reviewed PRs.

## First prompts to use

### Prompt 1: safety PR

```text
Read CLAUDE.md, docs/AZURE_ZERO_COST_MIGRATION.md, and
docs/AZURE_AGENT_MIGRATION_PLAYBOOK.md. Plan and implement only PR 0 and PR 1
from the playbook on a new branch.

Neutralize automatic AWS deployment on pushes to main while preserving the old
workflow as readable recovery history. Add a concise root AGENTS.md with the
repository commands, migration constraints, approval boundaries, DCO identity,
and links to the two Azure documents. Correct stale deployment statements in
CLAUDE.md.

Do not access Azure or AWS, push, merge, delete recovery material, change
secrets, or implement any Azure infrastructure. Run relevant static validation
for workflow/YAML and inspect the final diff. Finish with tests run, risks,
rollback, and items requiring my approval.
```

### Prompt 2: application guardrails

```text
Read AGENTS.md and the Required product and code changes section of
docs/AZURE_ZERO_COST_MIGRATION.md. Implement only PR 2 from
docs/AZURE_AGENT_MIGRATION_PLAYBOOK.md on a new branch based on the merged
safety PR.

Do not access cloud services, alter deployment workflows, or perform unrelated
refactors. Add regression tests first or alongside each behavior. Regenerate
the OpenAPI snapshot if routes change. Run the complete applicable backend
checks and finish with exact evidence and any remaining risks.
```

### Prompt 3: Terraform plan-only

```text
Read AGENTS.md and the Azure resource configuration, Terraform recommendation,
cost containment, and interview-only operating sections of the Azure migration
report. Implement only PR 6 from the agent playbook.

You may use Azure CLI read-only commands to verify the active subscription,
regional SKU availability, and existing resource names. Before every Azure CLI
command, classify it as read-only. Do not run terraform apply/destroy/import,
create resources, assign roles, register providers, alter state, change the
subscription, or access secret values.

Make invalid paid configurations fail validation. Produce a Terraform plan and
an inventory mapping each proposed resource to the account's free meter. Stop
if an eligible SKU is unavailable or the plan includes anything outside the
approved architecture. Finish with the saved-plan hash and full human approval
checklist; do not apply it.
```

## What you should personally review

You do not need to understand every line of FastAPI or Terraform, but never approve production until you can answer:

- Which subscription and region will this change target?
- What exact resources will exist afterward, and which free meter covers each?
- Can any setting grow automatically or create a secondary resource?
- What secrets or customer data does the operation touch?
- What is backed up and how was restore verified?
- What will happen if migration step N fails halfway?
- Which old system remains the recovery source?
- How do you deallocate the VM and stop PostgreSQL afterward?
- What exact observable tests prove login, learning sessions, speech, private media, OAuth, payment webhooks, and rollback work?
- Is DNS/source deletion happening in a separate approval step?

If an agent cannot provide a precise answer with evidence, do not approve the next gate.

## Recommended Codex operating setup

- Start in Plan mode for each new work package, then authorize implementation of only the approved package.
- Use workspace-write/Ask for approval for local implementation; use read-only for audits.
- Keep one task per chat and one worktree/branch per PR.
- Review the diff and run `/review` before accepting a PR.
- Keep durable rules in root `AGENTS.md`; do not repeatedly paste them into every prompt.
- Provide Azure access only when a task reaches the relevant gate, and remove/expire it afterward.
- Use GitHub Environment required reviewers for production workflows so repository code alone cannot deploy.
- Never make a coding agent the sole authority for cost, backup validity, production data deletion, or DNS cutover.

Official Codex guidance supports this pattern: provide goal/context/constraints/done criteria, plan difficult work, place durable repository rules in `AGENTS.md`, begin with tight permissions, verify changes with tests and review, and require confirmation for external, destructive, costly, or scope-expanding actions. See [Codex best practices](https://learn.chatgpt.com/guides/best-practices), [AGENTS.md guidance](https://learn.chatgpt.com/docs/agent-configuration/agents-md), and [agent approvals and security](https://learn.chatgpt.com/docs/agent-approvals-security).
