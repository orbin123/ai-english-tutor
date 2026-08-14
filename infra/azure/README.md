# Azure zero-cost Terraform (plan only)

This directory describes the minimal production topology approved in
`docs/AZURE_ZERO_COST_MIGRATION.md`. It does not deploy anything, configure DNS,
move data, or populate Key Vault. CI/CD, cold-state control, and the separately
reviewed post-Terraform VM host bootstrap live under `.github/` and remain
disabled until their production gates pass.

## Layout

```text
bootstrap/             one-time private Azure Blob state storage
environments/prod/     the only application environment
modules/               minimal network, VM, PostgreSQL, Blob, ACR, Key Vault,
                       and cost-policy components
tests/                 offline resource/count/forbidden-service assertions
```

The existing AWS Terraform under `../terraform` is frozen recovery material and
is intentionally unchanged.

## Region and cloud-access gate

No Azure region has been approved. `environments/prod/locals.tf` therefore has
an empty `approved_locations` set. Any plan fails until the owner approves one
exact region and a reviewed commit adds only that region to the set. Central
India must not be added merely because it is the current candidate.

A real plan also requires explicit approval for the subscription, tenant,
Reader identity, and remote-state discovery. This PR performs no Azure login,
CLI command, subscription inspection, provider registration, or backend access.

## Safe local validation

From this directory:

```bash
terraform fmt -check -recursive
terraform -chdir=bootstrap init -backend=false
terraform -chdir=bootstrap validate
terraform -chdir=environments/prod init -backend=false
terraform -chdir=environments/prod validate
terraform -chdir=environments/prod test
bash tests/static_guardrails.sh
bash tests/host_contract_guardrails.sh
```

The Terraform test uses a mock provider and proves that an unapproved region
cannot produce a plan. It neither authenticates to Azure nor contacts a backend.

Provider downloads create ignored `.terraform/` directories and an ignored lock
file. Do not commit either without a separate review.

## Backend bootstrap

`bootstrap` contains one resource group, one Standard LRS StorageV2 account,
one private state container, and one data-plane RBAC assignment for the approved
state administrator. It uses Entra authentication and never accepts an account
key. Bootstrap must be applied only in a separately approved one-time operation.

The production backend contains no resource names or credentials. Supply its
resource group, account, container, key, subscription, and tenant through
approved out-of-band backend configuration after bootstrap.

## Production constraints

- one `Standard_B2ats_v2` Linux VM, one embedded 64 GiB Premium LRS (P6) OS
  disk, one Standard static IPv4, and no data disk;
- one PostgreSQL Flexible Server `B_Standard_B1ms`, PostgreSQL 16, exactly
  32 GiB/P4 storage, seven-day local backups, HA/geo backup/autogrow disabled,
  and one firewall rule matching only the VM public IP;
- two Standard Hot LRS storage accounts and exactly three containers: public
  blob-only media, private learner media, and private internal data;
- one Standard ACR with admin disabled and one Standard RBAC Key Vault;
- system-assigned VM identity with only ACR pull, Blob data contributor on the
  two application accounts, and Key Vault secret-read roles;
- one action group, one resource-group budget, and enforced allowed-location and
  allowed-resource-type policies;
- Vercel remains the Phase 1 frontend.

PostgreSQL is defined with Entra-only authentication so Terraform never accepts
or stores a database password. Application managed-identity database login and
the least-privilege database role remain a deployment/data gate; this PR neither
creates a secret nor claims the application is ready to connect.

## State and removal

Terraform state contains sensitive infrastructure metadata even without secret
values. Restrict state access, keep Blob versioning off, and include the backend
account in the reviewed free-tier-expiry removal. Normal rollback before apply is
deleting/reverting these files. After a future apply, rollback is a separately
reviewed destroy only after data export and `prevent_destroy` removal approval.
