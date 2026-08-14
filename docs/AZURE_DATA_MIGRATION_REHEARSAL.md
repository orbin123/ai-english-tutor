# Azure data-migration rehearsal

This runbook is the code-only work package after PR 8. It implements the
playbook's suggested **migration-script rehearsal**. Gate A was subsequently
resolved on 14 August 2026 in favor of a fresh Azure database with no AWS data
restoration.
It does not authorize or perform production data recovery, Azure provisioning,
RDS/S3 access, Blob transfer, PostgreSQL restore, or cutover.

## Safety boundary

The rehearsal tool in `backend/scripts/azure_data_rehearsal.py` can:

- inventory an explicitly configured PostgreSQL database only when its host is
  loopback (`localhost`, `127.0.0.1`, or `::1`);
- inventory files under a local `public/`, `private/`, and `internal/` tree;
- compare two JSON inventories and fail when rows, extensions, objects, sizes,
  content types, or SHA-256 checksums differ.

It cannot connect to AWS or Azure, copy objects, dump or restore a database,
change schema, or delete data. Database URLs are read from an environment
variable and are never included in inventory output.

Do not add a remote-host override. Production source/destination access belongs
to a separate, explicitly approved Gate D operation after Gate A is resolved.

## Synthetic rehearsal

Create two disposable local PostgreSQL databases, populate the source with
synthetic records only, and apply the same Alembic schema to the destination.
Use native PostgreSQL `pg_dump` and `pg_restore` manually between those local
databases. Do not use a production dump.

Capture the inventories without putting credentials in command arguments:

```bash
cd backend
export MIGRATION_REHEARSAL_DATABASE_URL='postgresql://...@127.0.0.1/source_rehearsal'
uv run python -m scripts.azure_data_rehearsal postgres-inventory > /tmp/source-db.json

export MIGRATION_REHEARSAL_DATABASE_URL='postgresql://...@127.0.0.1/destination_rehearsal'
uv run python -m scripts.azure_data_rehearsal postgres-inventory > /tmp/destination-db.json

uv run python -m scripts.azure_data_rehearsal reconcile \
  /tmp/source-db.json /tmp/destination-db.json
```

For media, arrange synthetic files by intended Azure visibility. Learner audio
belongs under `private/`; transcripts and pronunciation metadata belong under
`internal/`; only intentionally anonymous assets belong under `public/`.

```text
/tmp/source-media/
├── public/
├── private/
└── internal/
```

Generate and compare deterministic manifests:

```bash
cd backend
uv run python -m scripts.azure_data_rehearsal media-inventory \
  /tmp/source-media > /tmp/source-media.json
uv run python -m scripts.azure_data_rehearsal media-inventory \
  /tmp/destination-media > /tmp/destination-media.json
uv run python -m scripts.azure_data_rehearsal reconcile \
  /tmp/source-media.json /tmp/destination-media.json
```

Reconciliation exits `0` only for a match, `1` for differences, and `2` for
invalid or unsafe input. JSON inventories can contain object names and table
metadata; keep real inventories out of Git and share them only through the
approved recovery-evidence channel.

## Historical rehearsal evidence

The local synthetic rehearsal remains useful recovery-tool evidence, but it is
not part of the approved fresh-start production path and authorizes no
production connection or copy. The next code-only package is the single-account
bootstrap in
[`AZURE_FRESH_START_ADMIN_BOOTSTRAP.md`](./AZURE_FRESH_START_ADMIN_BOOTSTRAP.md).
AWS recovery evidence remains protected until the separately approved removal
phase.
