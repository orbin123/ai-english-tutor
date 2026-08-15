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
traffic, an approved member of the configured Microsoft Entra PostgreSQL
administrator group runs the reviewed operator command from the repository
root:

```bash
.github/scripts/azure-postgres-identity-bootstrap.sh \
  <approved-postgres-server-name> \
  "<approved-entra-administrator-group-name>" \
  <vm-managed-identity-object-id> \
  <approved-current-public-ipv4>
```

The wrapper accepts only non-secret identifiers. It requires the server to be
`Ready` with exactly the Terraform-authored `allow-vm-only` firewall rule,
opens one fixed temporary rule for the single operator IPv4, and removes and
verifies removal of that rule on every exit path. A pre-existing temporary or
unexpected rule closes the gate.

The Python operation obtains a PostgreSQL access token in memory through
`AzureCliCredential`; it never accepts or prints the token. It then:

1. Connects to the server's `postgres` database over TLS as the exact
   configured Entra administrator group.
2. Verifies the token has `azure_pg_admin`, `CREATEROLE`, and `CREATEDB`.
3. Refuses an unexpected `vm-lingosai-prod` role, Entra mapping, privilege,
   `lingosai` database, or database owner.
4. Calls `pgaadauth_create_principal_with_oid` with role
   `vm-lingosai-prod`, the exact VM object ID, object type `service`, and
   both administrator and MFA flags set to `false`.
5. Creates the empty `lingosai` database owned by that non-admin role.
6. Re-reads the role flags, one service-principal mapping, object ID,
   non-admin status, database owner, and empty public schema.

The command may resume only the safe partial state where the exact non-admin
role and mapping were created but the database was not. It may verify the exact
role plus still-empty database before Alembic. It refuses all other partial or
post-migration states.

Use Terraform's `vm_principal_id` output rather than a similarly named
application or user. Stop if the command refuses; do not drop or rewrite a role,
database, mapping, object, or firewall rule to make the gate pass.

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
- no `temporary-identity-bootstrap` firewall rule remains;
- an unauthenticated/password-only connection fails;
- Alembic reaches the expected head and the fresh-admin bootstrap passes;
- restarting the container obtains a new connection token and readiness
  returns healthy.

Application rollback is the previous image digest, which must use the same
credential-free connection contract. Database migrations remain forward-only.
Changing the server to password authentication is not a rollback; it is a new
security design requiring a separately reviewed migration.
