"""Offline inventory and reconciliation for the Azure data-migration rehearsal.

This module intentionally supports only loopback PostgreSQL connections and local
filesystem media. Production RDS, S3, Azure PostgreSQL, and Azure Blob operations
belong to later, explicitly approved migration gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from psycopg import Connection, sql

MANIFEST_VERSION = 1
MEDIA_VISIBILITIES = ("public", "private", "internal")
LOOPBACK_DATABASE_HOSTS = {None, "", "localhost", "127.0.0.1", "::1"}


class RehearsalError(ValueError):
    """Raised when rehearsal input violates the local-only safety contract."""


def require_loopback_database_url(database_url: str) -> None:
    """Reject any database URL that could target a remote environment."""

    parsed = urlsplit(database_url)
    if parsed.scheme not in {"postgresql", "postgres"}:
        raise RehearsalError("Rehearsal database URL must use PostgreSQL")
    if parsed.query or parsed.fragment:
        raise RehearsalError(
            "Rehearsal database URL must not contain query parameters or fragments"
        )
    if parsed.hostname not in LOOPBACK_DATABASE_HOSTS:
        raise RehearsalError(
            "This rehearsal command only accepts a loopback PostgreSQL host"
        )
    if not parsed.path or parsed.path == "/":
        raise RehearsalError("Rehearsal database URL must name a database")


def capture_postgres_inventory(connection: Connection[Any]) -> dict[str, Any]:
    """Capture exact row counts and storage metadata from a synthetic database."""

    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('server_version')")
        server_version = str(_first_column(cursor.fetchone(), "server version"))
        cursor.execute("SELECT pg_database_size(current_database())")
        database_size_bytes = int(_first_column(cursor.fetchone(), "database size"))
        cursor.execute(
            """
            SELECT extname, extversion
            FROM pg_extension
            ORDER BY extname
            """
        )
        extensions = [
            {"name": str(name), "version": str(version)}
            for name, version in cursor.fetchall()
        ]
        cursor.execute(
            """
            SELECT schemaname, relname,
                   pg_total_relation_size(relid),
                   pg_indexes_size(relid)
            FROM pg_stat_user_tables
            ORDER BY schemaname, relname
            """
        )
        relations = cursor.fetchall()

        tables: list[dict[str, Any]] = []
        for schema_name, table_name, total_bytes, index_bytes in relations:
            cursor.execute(
                sql.SQL("SELECT count(*) FROM {}.{}").format(
                    sql.Identifier(str(schema_name)),
                    sql.Identifier(str(table_name)),
                )
            )
            row_count = int(_first_column(cursor.fetchone(), "table row count"))
            tables.append(
                {
                    "schema": str(schema_name),
                    "table": str(table_name),
                    "row_count": row_count,
                    "total_bytes": int(total_bytes),
                    "index_bytes": int(index_bytes),
                }
            )

    return {
        "manifest_version": MANIFEST_VERSION,
        "kind": "postgresql",
        "server_version": server_version,
        "database_size_bytes": database_size_bytes,
        "extensions": extensions,
        "tables": tables,
    }


def build_media_inventory(root: Path) -> dict[str, Any]:
    """Hash files under public/private/internal without following symlinks."""

    if root.is_symlink():
        raise RehearsalError(f"Media inventory refuses a symlink root: {root}")
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise RehearsalError(f"Media root is not a directory: {root}")

    unexpected = sorted(
        item.name for item in root.iterdir() if item.name not in MEDIA_VISIBILITIES
    )
    if unexpected:
        raise RehearsalError(
            "Media root may contain only public/private/internal directories; "
            f"found: {', '.join(unexpected)}"
        )

    objects: list[dict[str, Any]] = []
    for visibility in MEDIA_VISIBILITIES:
        visibility_root = root / visibility
        if not visibility_root.exists():
            continue
        if visibility_root.is_symlink() or not visibility_root.is_dir():
            raise RehearsalError(f"Invalid media visibility directory: {visibility}")

        for path in sorted(visibility_root.rglob("*")):
            if path.is_symlink():
                raise RehearsalError(f"Media inventory refuses symlinks: {path}")
            if not path.is_file():
                continue
            relative_key = path.relative_to(visibility_root).as_posix()
            if not relative_key or relative_key.startswith("../"):
                raise RehearsalError(f"Invalid media object path: {path}")
            objects.append(
                {
                    "visibility": visibility,
                    "object_key": relative_key,
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                    "content_type": mimetypes.guess_type(path.name)[0]
                    or "application/octet-stream",
                }
            )

    return {
        "manifest_version": MANIFEST_VERSION,
        "kind": "media",
        "objects": objects,
        "totals": {
            visibility: {
                "objects": sum(item["visibility"] == visibility for item in objects),
                "bytes": sum(
                    int(item["size_bytes"])
                    for item in objects
                    if item["visibility"] == visibility
                ),
            }
            for visibility in MEDIA_VISIBILITIES
        },
    }


def reconcile_manifests(
    source: Mapping[str, Any], destination: Mapping[str, Any]
) -> dict[str, Any]:
    """Compare database or media manifests without reading either environment."""

    source_kind = _validate_manifest_header(source)
    destination_kind = _validate_manifest_header(destination)
    if source_kind != destination_kind:
        raise RehearsalError(
            f"Manifest kinds differ: source={source_kind}, destination={destination_kind}"
        )

    if source_kind == "postgresql":
        differences = _reconcile_postgres(source, destination)
    else:
        differences = _reconcile_media(source, destination)

    return {
        "manifest_version": MANIFEST_VERSION,
        "kind": source_kind,
        "matches": not differences,
        "differences": differences,
    }


def _validate_manifest_header(manifest: Mapping[str, Any]) -> str:
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        raise RehearsalError(
            f"Unsupported manifest_version: {manifest.get('manifest_version')!r}"
        )
    kind = manifest.get("kind")
    if kind not in {"postgresql", "media"}:
        raise RehearsalError(f"Unsupported manifest kind: {kind!r}")
    return str(kind)


def _reconcile_postgres(
    source: Mapping[str, Any], destination: Mapping[str, Any]
) -> list[dict[str, Any]]:
    source_tables = _keyed_rows(source.get("tables"), ("schema", "table"), "tables")
    destination_tables = _keyed_rows(
        destination.get("tables"), ("schema", "table"), "tables"
    )
    differences: list[dict[str, Any]] = []
    for key in sorted(source_tables.keys() | destination_tables.keys()):
        source_row = source_tables.get(key)
        destination_row = destination_tables.get(key)
        table_label = ".".join(key)
        if source_row is None:
            differences.append({"type": "unexpected_table", "table": table_label})
        elif destination_row is None:
            differences.append({"type": "missing_table", "table": table_label})
        elif source_row.get("row_count") != destination_row.get("row_count"):
            differences.append(
                {
                    "type": "row_count_mismatch",
                    "table": table_label,
                    "source": source_row.get("row_count"),
                    "destination": destination_row.get("row_count"),
                }
            )

    source_extensions = _extension_names(source.get("extensions"))
    destination_extensions = _extension_names(destination.get("extensions"))
    for name in sorted(source_extensions - destination_extensions):
        differences.append({"type": "missing_extension", "extension": name})
    for name in sorted(destination_extensions - source_extensions):
        differences.append({"type": "unexpected_extension", "extension": name})
    return differences


def _reconcile_media(
    source: Mapping[str, Any], destination: Mapping[str, Any]
) -> list[dict[str, Any]]:
    key_fields = ("visibility", "object_key")
    source_objects = _keyed_rows(source.get("objects"), key_fields, "objects")
    destination_objects = _keyed_rows(destination.get("objects"), key_fields, "objects")
    differences: list[dict[str, Any]] = []
    for key in sorted(source_objects.keys() | destination_objects.keys()):
        source_object = source_objects.get(key)
        destination_object = destination_objects.get(key)
        visibility, object_key = key
        if source_object is None:
            differences.append(
                {
                    "type": "unexpected_object",
                    "visibility": visibility,
                    "object_key": object_key,
                }
            )
        elif destination_object is None:
            differences.append(
                {
                    "type": "missing_object",
                    "visibility": visibility,
                    "object_key": object_key,
                }
            )
        else:
            for field in ("size_bytes", "sha256", "content_type"):
                if source_object.get(field) != destination_object.get(field):
                    differences.append(
                        {
                            "type": f"{field}_mismatch",
                            "visibility": visibility,
                            "object_key": object_key,
                            "source": source_object.get(field),
                            "destination": destination_object.get(field),
                        }
                    )
    return differences


def _keyed_rows(
    value: Any, key_fields: tuple[str, ...], label: str
) -> dict[tuple[str, ...], Mapping[str, Any]]:
    if not isinstance(value, list):
        raise RehearsalError(f"Manifest {label} must be a list")
    result: dict[tuple[str, ...], Mapping[str, Any]] = {}
    for row in value:
        if not isinstance(row, Mapping):
            raise RehearsalError(f"Manifest {label} entries must be objects")
        key = tuple(str(row.get(field, "")) for field in key_fields)
        if any(not part for part in key):
            raise RehearsalError(f"Manifest {label} entry has an empty key field")
        if key in result:
            raise RehearsalError(f"Manifest {label} contains duplicate key: {key}")
        result[key] = row
    return result


def _extension_names(value: Any) -> set[str]:
    if not isinstance(value, list):
        raise RehearsalError("Manifest extensions must be a list")
    result: set[str] = set()
    for extension in value:
        if not isinstance(extension, Mapping) or not extension.get("name"):
            raise RehearsalError("Manifest extension entries require a name")
        result.add(str(extension["name"]))
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _first_column(row: Any, label: str) -> Any:
    if row is None:
        raise RehearsalError(f"PostgreSQL returned no {label} row")
    return row[0]


def _load_manifest(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RehearsalError(f"Could not read manifest {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise RehearsalError(f"Manifest must contain a JSON object: {path}")
    return value


def _write_json(value: Mapping[str, Any]) -> None:
    json.dump(value, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    postgres = subparsers.add_parser(
        "postgres-inventory", help="Inventory a loopback synthetic PostgreSQL database"
    )
    postgres.add_argument(
        "--database-url-env",
        default="MIGRATION_REHEARSAL_DATABASE_URL",
        help="Environment variable containing the loopback URL (never printed)",
    )

    media = subparsers.add_parser(
        "media-inventory", help="Inventory a local synthetic media tree"
    )
    media.add_argument("root", type=Path)

    reconcile = subparsers.add_parser(
        "reconcile", help="Compare source and destination JSON inventories"
    )
    reconcile.add_argument("source", type=Path)
    reconcile.add_argument("destination", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "postgres-inventory":
            database_url = os.environ.get(args.database_url_env)
            if not database_url:
                raise RehearsalError(
                    f"Missing database URL environment variable: {args.database_url_env}"
                )
            require_loopback_database_url(database_url)
            with Connection.connect(database_url) as connection:
                _write_json(capture_postgres_inventory(connection))
            return 0
        if args.command == "media-inventory":
            _write_json(build_media_inventory(args.root))
            return 0

        result = reconcile_manifests(
            _load_manifest(args.source), _load_manifest(args.destination)
        )
        _write_json(result)
        return 0 if result["matches"] else 1
    except RehearsalError as exc:
        print(f"rehearsal error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
