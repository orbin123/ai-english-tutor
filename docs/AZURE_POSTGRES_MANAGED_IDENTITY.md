# Azure PostgreSQL managed-identity runtime contract

The production PostgreSQL Flexible Server is Microsoft Entra-only. LingoAI does
not create, store, or rotate a database password. The single production VM's
system-assigned identity is mapped to the PostgreSQL role
`vm-lingosai-prod`, and the backend supplies a current Entra access token as the
DBAPI password whenever SQLAlchemy opens a new physical connection.

This document defines the deployment gate. It does not authorize provisioning,
database mutation, or production execution by itself.

## Application configuration

The root-owned VM environment file must contain a credential-free URL:

```dotenv
DATABASE_AUTH_MODE=azure-managed-identity
DATABASE_URL=postgresql://vm-lingosai-prod@<server>.postgres.database.azure.com:5432/lingosai?sslmode=require
```

Production startup refuses managed-identity mode if the URL contains a
password, uses another role/port/database, targets a non-Azure host, omits
`sslmode=require`, or adds another query option. Password mode is preserved for
local development and the frozen non-Azure recovery path, but it is rejected
for an Azure PostgreSQL hostname.

`app/core/azure_postgres.py` registers SQLAlchemy's `do_connect` hook. The hook
requests the fixed
`https://ossrdbms-aad.database.windows.net/.default` scope through
`DefaultAzureCredential` and injects the returned token only into the pending
DBAPI connection parameters. The token is never added to the URL, settings,
logs, image, or environment file. New physical connections receive a current
token; pooled authenticated connections continue normally until recycled.

## One-time database identity gate

After Terraform creates the server and VM, but before Alembic or application
traffic, an approved Microsoft Entra PostgreSQL administrator must:

1. Connect to the server's `postgres` database using an Entra access token over
   TLS from the temporarily approved administration path.
2. Verify that no unexpected `vm-lingosai-prod` role or `lingosai` database
   exists.
3. Map the VM system-assigned identity with PostgreSQL's
   `pgaadauth_create_principal('vm-lingosai-prod', false, false)` function.
4. Create the `lingosai` database owned by that role.
5. Verify the role's Entra mapping, login capability, database ownership, and a
   token-authenticated connection from the VM.
6. Close the temporary administration path before public activation.

Use the VM identity's exact Entra object rather than a similarly named
application or user. Stop if the role/database already exists with a different
owner or mapping; do not drop or rewrite it to make the gate pass.

The same VM identity runs forward-only Alembic migrations and the single
backend process, so it owns only the `lingosai` database. It receives no server
administrator role and no access to other databases. The server firewall still
allows only the VM's static public IP.

## Verification and rollback

Before activation, verify all of the following:

- the server has password authentication disabled and Entra authentication
  enabled;
- the backend environment file contains no database password;
- a VM-side connection succeeds as `vm-lingosai-prod` with `sslmode=require`;
- an unauthenticated/password-only connection fails;
- Alembic reaches the expected head and the fresh-admin bootstrap passes;
- restarting the container obtains a new connection token and readiness
  returns healthy.

Application rollback is the previous image digest, which must use the same
credential-free connection contract. Database migrations remain forward-only.
Changing the server to password authentication is not a rollback; it is a new
security design requiring a separately reviewed migration.
