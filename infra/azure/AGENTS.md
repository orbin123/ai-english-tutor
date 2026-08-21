# Azure Terraform instructions

This directory contains the reviewed infrastructure for the Azure zero-cost
migration. Planning and production execution remain separate approval gates.
The root `AGENTS.md` and both Azure migration documents remain authoritative.

- Keep exactly one application environment under `environments/prod` plus the
  one-time `bootstrap` state-storage root.
- A real plan is allowed only after the owner approves the exact region and
  subscription, Phase 0 is complete, and the active identity has read-only
  discovery plus the minimum remote-state data access. Read-only Azure CLI
  discovery and the backend state lock used by `terraform plan` are allowed.
- A production apply is allowed only from the exact saved plan after the owner
  reviews its complete resource inventory, free-meter mapping, identity scopes,
  and plan hash and then gives separate explicit Gate C approval. Re-run the
  plan and request new approval if the plan or hash changes.
- Never run `terraform destroy`, `import`, refresh-only/state mutation, an
  ad-lib or unsaved apply, provider registration, role-assignment mutation, or
  subscription changes. Production RBAC and provider registration require their
  own explicit reviewed gates.
- Never commit `.terraform/`, lock files unless separately reviewed, state,
  plans, plan text, tfvars, credentials, secrets, private keys, or real tenant,
  subscription, principal, storage-account, registry, vault, or server IDs.
- Preserve `infra/terraform` and all AWS recovery material unchanged.
- Keep resource types, counts, SKUs, storage/privacy settings, identities, RBAC,
  and cost controls inside the migration documents' approved envelope.
- Do not add deployment workflows, wake/sleep automation, DNS, frontend work,
  data migration, private endpoints, or any PR 7+ work here.

Before the real-plan gate, allowed local checks are
`terraform fmt -check -recursive`, `terraform init -backend=false`,
`terraform validate`, and static guardrail tests. At the real-plan gate,
`terraform init` and `terraform plan -out=<untracked-path>` are allowed using
approved out-of-band inputs. Never commit plans, plan text, state, tfvars, or
credentials. Stop if validation or planning proposes an unapproved item.
