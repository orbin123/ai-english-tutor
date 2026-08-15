# Azure VM host bootstrap

This runbook installs and verifies the reviewed runtime contract on the single
`vm-lingosai-prod` host. It is a post-Terraform, pre-deployment operation. It
does not provision infrastructure, create database roles, deploy an image,
change DNS, or activate public traffic.

The scripts accept only non-secret resource names. The VM's system-assigned
identity reads the complete production environment from one Key Vault secret,
and the secret value is redirected directly into a temporary root-only file.
Neither Azure Run Command parameters nor script output contain the value.

## Prerequisites

Before running the bootstrap:

1. The reviewed Azure stack exists and the VM is running.
2. The VM identity has only the Terraform-defined `AcrPull`, Blob data, and Key
   Vault secret-read assignments.
3. Key Vault contains an enabled secret named `backend-env` whose value is the
   completed production dotenv file. The file must satisfy
   `.env.production.example`, contain no placeholders or database password,
   and use the Azure managed-identity database and Blob modes.
4. PostgreSQL is running, its firewall permits only the VM's static public IP,
   and the managed-identity database mapping gate is ready to execute.
5. DNS remains unchanged and Azure automation remains disabled.

Upload the completed environment from a temporary `0600` file outside the
repository using the approved secret-entry path. Do not pass the value on a
command line or print it:

```bash
az keyvault secret set \
  --vault-name <approved-key-vault-name> \
  --name backend-env \
  --file /secure/path/backend.env \
  --output none \
  --only-show-errors
```

Key Vault secret creation is a production secret mutation. Record only the
secret version identifier as evidence, never its value.

## Install the host contract

Run this command from the repository root after the bootstrap PR is merged:

```bash
az vm run-command invoke \
  --resource-group rg-lingosai-prod \
  --name vm-lingosai-prod \
  --command-id RunShellScript \
  --scripts @.github/scripts/azure-vm-bootstrap.sh \
  --parameters \
    api.lingosai.com \
    <approved-key-vault-name> \
    backend-env \
  --output none \
  --only-show-errors
```

The operation is idempotent. It:

- installs Docker, Caddy, Azure CLI, bounded journaling, unattended security
  updates, and a 1 GiB disk-backed swapfile;
- configures Caddy for ACME HTTPS, WebSockets, a 5 MiB request cap, the local
  API at `127.0.0.1:8000`, and a marker-controlled `503` maintenance
  response;
- creates the root-owned host directories and keeps maintenance mode active;
- signs in with the VM identity and writes the Key Vault environment to
  `/etc/lingosai/backend.env` as `root:root` mode `0600`;
- rejects missing Azure production invariants, placeholders, Windows line
  endings, and password-bearing database URLs.

Package or Key Vault failures leave public maintenance mode active. The script
does not start the application container.

## Verify the contract

After the PostgreSQL server and identity assignments are ready, run:

```bash
az vm run-command invoke \
  --resource-group rg-lingosai-prod \
  --name vm-lingosai-prod \
  --command-id RunShellScript \
  --scripts @.github/scripts/azure-vm-verify.sh \
  --parameters \
    api.lingosai.com \
    <approved-key-vault-name> \
    backend-env \
    <approved-acr-name> \
    <approved-postgres-server-name> \
  --output none \
  --only-show-errors
```

Success proves:

- Docker and Caddy are active and enabled for boot;
- the environment remains root-owned and no more permissive than `0600`;
- maintenance mode, the bounded swapfile, Caddy syntax, upload cap, and local
  reverse proxy are present;
- the VM identity can read the approved Key Vault secret metadata and acquire
  an ACR token without displaying either credential;
- the PostgreSQL hostname resolves and port `5432` is reachable from the VM.

This is not the database-authentication gate. Complete
`AZURE_POSTGRES_MANAGED_IDENTITY.md`, then run Alembic, the fresh administrator
bootstrap, seeders, and the digest-pinned deployment. Caddy removes maintenance
mode only after local liveness and readiness both pass.

## Refresh and rollback

Re-running the bootstrap safely refreshes the environment from the current
enabled Key Vault version while restoring maintenance mode. Use that behavior
only during a reviewed maintenance window.

Before the first deployment, rollback is leaving the marker in place and
stopping the VM/PostgreSQL. After deployment, use the recorded previous image
digest. Do not delete the environment, identity assignments, secret versions,
or infrastructure as an application rollback.
