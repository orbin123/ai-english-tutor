# Azure Terraform instructions

This directory is plan-only infrastructure for the Azure zero-cost migration.
The root `AGENTS.md` and both Azure migration documents remain authoritative.

- Keep exactly one application environment under `environments/prod` plus the
  one-time `bootstrap` state-storage root.
- Never run `terraform apply`, `destroy`, `import`, refresh-only/state mutation,
  `az`, provider registration, role-assignment mutation, or subscription changes.
- A real plan requires the owner's approved region, subscription scope, Reader
  access, and backend/discovery setup. Central India is only a candidate.
- Never commit `.terraform/`, lock files unless separately reviewed, state,
  plans, plan text, tfvars, credentials, secrets, private keys, or real tenant,
  subscription, principal, storage-account, registry, vault, or server IDs.
- Preserve `infra/terraform` and all AWS recovery material unchanged.
- Keep resource types, counts, SKUs, storage/privacy settings, identities, RBAC,
  and cost controls inside the migration documents' approved envelope.
- Do not add deployment workflows, wake/sleep automation, DNS, frontend work,
  data migration, private endpoints, or any PR 7+ work here.

Allowed local checks are `terraform fmt -check -recursive`,
`terraform init -backend=false`, `terraform validate`, and static guardrail
tests. Stop if validation requires cloud access or proposes an unapproved item.
