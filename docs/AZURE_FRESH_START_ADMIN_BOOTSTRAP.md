# Azure fresh-start administrator bootstrap

Gate A was resolved on 14 August 2026: Azure will start with a new database and
no AWS data restoration. This runbook covers only the local, one-time creation
of the owner-approved administrator after `alembic upgrade head`. It does not
authorize an Azure connection, provisioning, deployment, DNS or secret changes,
or production execution.

## Safety contract

`python -m scripts.bootstrap_fresh_admin` creates exactly one account with the
`admin` and `super_admin` roles. It deliberately creates no `learner` role,
learner profile, OAuth link, subscription, enrollment, or learning data. The
account is active and email-verified so the supplied password can be used for
the first login.

The command fails without changing the database when:

- the schema differs from the application's complete ORM schema;
- the role, permission, or default role-grant catalog differs from code;
- any account exists other than the exact already-bootstrapped account;
- the existing account's identity, password, verification state, active state,
  legacy superuser flag, or exact two-role assignment differs;
- any non-catalog application table contains a row.

Only the exact migration-authored roles, permissions, role grants, skills, and
two initial blog posts are allowed. Curriculum, archetype, and challenge seeders
must not run until bootstrap succeeds. PostgreSQL executions take a
transaction-scoped advisory lock so two bootstrap attempts cannot race. A
repeat run against the unchanged, pre-seed database verifies the account and
exits successfully without rewriting its password hash.

This is intentionally a pre-activation command. Once the application has
written runtime data, a repeat run refuses to proceed; use the normal reviewed
admin and password-recovery flows instead of treating bootstrap as account
repair.

## Prepare the input outside Git

Create a temporary JSON file outside the repository through the operator's
approved secret-entry path. It must contain exactly:

```json
{
  "email": "<owner-approved-email>",
  "name": "<owner-approved-display-name>",
  "password": "<unique-high-entropy-password>"
}
```

Do not add this file to `.env`, a Docker image, Terraform, GitHub configuration,
an issue, a PR, shell arguments, or Git. Restrict it to the operator (`0600`),
do not print it, and remove it through the approved secret-handling process
after the first login/recovery path is verified.

The command reads JSON only from standard input and never prints the email or
password:

```bash
cd backend
uv run alembic upgrade head
uv run python -m scripts.bootstrap_fresh_admin </secure/path/fresh-admin.json
```

For the later, separately approved VM operation, use the already-reviewed image
digest and feed the host file over standard input; do not bake or copy it into
the container:

```bash
docker run --rm -i \
  --network host \
  --env-file /etc/lingosai/backend.env \
  "<approved-image-by-digest>" \
  python -m scripts.bootstrap_fresh_admin \
  </secure/path/fresh-admin.json
```

An exit status of `0` means the sole account was created or its exact bootstrap
state was verified. Any refusal or unexpected error exits `1`; stop and inspect
the database through a separately approved read-only process. Never delete,
rename, or rewrite rows to make this guard pass.

## Ordered fresh-start gate

Before public activation, the human operator must review evidence for each step:

1. Confirm the target is the approved fresh PostgreSQL server and the expected
   Alembic head is installed.
2. Run the bootstrap command once with the owner-approved input.
3. Optionally repeat it before any seed command or application traffic to prove
   idempotency.
4. Run the existing idempotent curriculum and challenge seed commands.
5. Start the application and verify password login plus both admin and
   super-admin authorization surfaces.
6. Confirm learner-only endpoints reject the administrator because it has no
   learner role.
7. Remove the transient input through the approved secret-handling process.

If any other account or runtime row exists, stop. That evidence contradicts the
fresh-start assumption and requires owner review; it is not an invitation to
purge data.

## Rollback

Before activation, rollback is to discard the entire unapproved fresh database
through a separately authorized infrastructure/data operation and repeat from a
new migrated database. The command itself performs no deletion and provides no
down migration. After activation, preserve the account and audit history and
use normal application administration; never re-run bootstrap as a repair tool.
