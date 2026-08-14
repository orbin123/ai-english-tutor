from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.azure_data_rehearsal import (
    RehearsalError,
    build_media_inventory,
    main,
    reconcile_manifests,
    require_loopback_database_url,
)


def test_database_inventory_rejects_remote_hosts() -> None:
    with pytest.raises(RehearsalError, match="only accepts a loopback"):
        require_loopback_database_url(
            "postgresql://user:password@production.example.com/lingosai"
        )


def test_database_inventory_rejects_query_host_override() -> None:
    with pytest.raises(RehearsalError, match="must not contain query"):
        require_loopback_database_url(
            "postgresql://user:password@localhost/lingosai?host=production.example.com"
        )


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql://user:password@localhost/source_rehearsal",
        "postgresql://user:password@127.0.0.1/destination_rehearsal",
        "postgresql://user:password@[::1]/source_rehearsal",
    ],
)
def test_database_inventory_accepts_named_loopback_databases(
    database_url: str,
) -> None:
    require_loopback_database_url(database_url)


def test_media_inventory_is_deterministic_and_separates_visibility(
    tmp_path: Path,
) -> None:
    (tmp_path / "public" / "blog").mkdir(parents=True)
    (tmp_path / "private").mkdir()
    (tmp_path / "internal").mkdir()
    (tmp_path / "public" / "blog" / "cover.png").write_bytes(b"public-image")
    (tmp_path / "private" / "learner.webm").write_bytes(b"private-audio")
    (tmp_path / "internal" / "transcript.json").write_text(
        '{"text":"hello"}', encoding="utf-8"
    )

    first = build_media_inventory(tmp_path)
    second = build_media_inventory(tmp_path)

    assert first == second
    assert [item["visibility"] for item in first["objects"]] == [
        "public",
        "private",
        "internal",
    ]
    assert first["totals"] == {
        "public": {"objects": 1, "bytes": 12},
        "private": {"objects": 1, "bytes": 13},
        "internal": {"objects": 1, "bytes": 16},
    }


def test_media_inventory_rejects_unknown_root_entries(tmp_path: Path) -> None:
    (tmp_path / "unclassified.bin").write_bytes(b"unsafe")

    with pytest.raises(RehearsalError, match="only public/private/internal"):
        build_media_inventory(tmp_path)


def test_media_inventory_rejects_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("private", encoding="utf-8")
    media_root = tmp_path / "media"
    (media_root / "private").mkdir(parents=True)
    (media_root / "private" / "learner.txt").symlink_to(target)

    with pytest.raises(RehearsalError, match="refuses symlinks"):
        build_media_inventory(media_root)


def test_media_reconciliation_detects_missing_and_changed_objects() -> None:
    source = _media_manifest(
        [
            _media_object("public", "cover.png", "a", 10, "image/png"),
            _media_object("private", "recording.webm", "b", 20, "audio/webm"),
        ]
    )
    destination = _media_manifest(
        [
            _media_object("public", "cover.png", "changed", 11, "image/png"),
            _media_object("internal", "extra.json", "c", 5, "application/json"),
        ]
    )

    result = reconcile_manifests(source, destination)

    assert result["matches"] is False
    assert {difference["type"] for difference in result["differences"]} == {
        "size_bytes_mismatch",
        "sha256_mismatch",
        "missing_object",
        "unexpected_object",
    }


def test_postgres_reconciliation_uses_exact_counts_and_extensions() -> None:
    source = _postgres_manifest(
        tables=[{"schema": "public", "table": "users", "row_count": 2}],
        extensions=[{"name": "plpgsql", "version": "1.0"}],
    )
    destination = _postgres_manifest(
        tables=[{"schema": "public", "table": "users", "row_count": 1}],
        extensions=[],
    )

    result = reconcile_manifests(source, destination)

    assert result["matches"] is False
    assert result["differences"] == [
        {
            "type": "row_count_mismatch",
            "table": "public.users",
            "source": 2,
            "destination": 1,
        },
        {"type": "missing_extension", "extension": "plpgsql"},
    ]


def test_reconcile_cli_returns_nonzero_for_mismatch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source_path = tmp_path / "source.json"
    destination_path = tmp_path / "destination.json"
    source_path.write_text(json.dumps(_media_manifest([])), encoding="utf-8")
    destination_path.write_text(
        json.dumps(
            _media_manifest([_media_object("public", "extra.png", "a", 1, "image/png")])
        ),
        encoding="utf-8",
    )

    exit_code = main(["reconcile", str(source_path), str(destination_path)])

    assert exit_code == 1
    assert json.loads(capsys.readouterr().out)["matches"] is False


def _media_manifest(objects: list[dict[str, object]]) -> dict[str, object]:
    return {"manifest_version": 1, "kind": "media", "objects": objects}


def _media_object(
    visibility: str,
    object_key: str,
    sha256: str,
    size_bytes: int,
    content_type: str,
) -> dict[str, object]:
    return {
        "visibility": visibility,
        "object_key": object_key,
        "sha256": sha256,
        "size_bytes": size_bytes,
        "content_type": content_type,
    }


def _postgres_manifest(
    *, tables: list[dict[str, object]], extensions: list[dict[str, str]]
) -> dict[str, object]:
    return {
        "manifest_version": 1,
        "kind": "postgresql",
        "tables": tables,
        "extensions": extensions,
    }
