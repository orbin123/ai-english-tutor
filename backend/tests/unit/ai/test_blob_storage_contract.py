"""Shared storage contract for local and Azure Blob backends.

The cloud adapters use in-memory SDK fakes. No cloud account, credential, or
emulator is required. Public URLs are anonymous/direct (no SAS or application
authorization), while private and internal URLs stay on application paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

from app.ai.storage import (
    AzureBlobStorage,
    BlobVisibility,
    IBlobStorage,
    LocalBlobStorage,
)


class _MissingObject(RuntimeError):
    status_code = 404


class _AzureDownload:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def readall(self) -> bytes:
        return self._data


class _FakeAzureBlobClient:
    def __init__(self, container: _FakeAzureContainerClient, name: str) -> None:
        self._container = container
        self._name = name

    def upload_blob(self, data, *, overwrite, content_settings):
        assert overwrite is True
        self._container.store[self._name] = data
        self._container.content_types[self._name] = content_settings.content_type

    def download_blob(self):
        if self._name not in self._container.store:
            raise _MissingObject("not found")
        return _AzureDownload(self._container.store[self._name])

    def exists(self) -> bool:
        return self._name in self._container.store

    def delete_blob(self, *, delete_snapshots):
        assert delete_snapshots == "include"
        if self._name not in self._container.store:
            raise _MissingObject("not found")
        del self._container.store[self._name]


class _FakeAzureContainerClient:
    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}
        self.content_types: dict[str, str] = {}
        self.addressed: list[str] = []
        self.list_calls = 0

    def get_blob_client(self, *, blob: str) -> _FakeAzureBlobClient:
        self.addressed.append(blob)
        return _FakeAzureBlobClient(self, blob)

    def list_blobs(self, **kwargs):
        self.list_calls += 1
        raise AssertionError("request paths must not list Azure blobs")


@dataclass
class _StorageCase:
    backend: str
    visibility: BlobVisibility
    storage: IBlobStorage
    object_name: str
    provider: Any | None = None
    local_path: Path | None = None


@pytest.fixture(
    params=[
        (backend, visibility)
        for backend in ("local", "azure")
        for visibility in BlobVisibility
    ],
    ids=lambda value: f"{value[0]}-{value[1].value}",
)
def storage_case(request, tmp_path) -> _StorageCase:
    backend, visibility = request.param
    key = "abcdef.bin"
    object_name = f"contract/{key[:2]}/{key}"
    route_prefix = (
        "/public"
        if visibility is BlobVisibility.PUBLIC
        else f"/protected/{visibility.value}"
    )

    if backend == "local":
        root = tmp_path / visibility.value
        return _StorageCase(
            backend=backend,
            visibility=visibility,
            storage=LocalBlobStorage(
                root_dir=root,
                public_url_prefix=route_prefix,
                visibility=visibility,
            ),
            object_name=object_name,
            local_path=root / key[:2] / key,
        )

    client = _FakeAzureContainerClient()
    storage = AzureBlobStorage(
        account_url=f"https://{visibility.value}.blob.example.test",
        container=f"{visibility.value}-media",
        key_prefix="contract",
        visibility=visibility,
        protected_url_prefix=(
            route_prefix if visibility is not BlobVisibility.PUBLIC else None
        ),
        container_client=client,
    )
    return _StorageCase(
        backend=backend,
        visibility=visibility,
        storage=storage,
        object_name=object_name,
        provider=client,
    )


@pytest.mark.asyncio
async def test_shared_round_trip_content_type_and_direct_address(storage_case):
    stored = await storage_case.storage.put(
        key="abcdef.bin",
        data=b"contract bytes",
        content_type="application/x-contract",
    )

    assert stored["storage_key"] == "abcdef.bin"
    assert stored["content_type"] == "application/x-contract"
    assert stored["size_bytes"] == len(b"contract bytes")
    assert await storage_case.storage.get(key="abcdef.bin") == b"contract bytes"
    assert await storage_case.storage.exists(key="abcdef.bin") is True

    if storage_case.provider is not None:
        assert storage_case.object_name in storage_case.provider.addressed
        assert (
            storage_case.provider.content_types[storage_case.object_name]
            == "application/x-contract"
        )
        assert storage_case.provider.list_calls == 0
    else:
        assert storage_case.local_path is not None
        assert storage_case.local_path.read_bytes() == b"contract bytes"


@pytest.mark.asyncio
async def test_shared_deletion_is_idempotent(storage_case):
    await storage_case.storage.put(
        key="abcdef.bin",
        data=b"delete me",
        content_type="application/octet-stream",
    )

    await storage_case.storage.delete(key="abcdef.bin")
    await storage_case.storage.delete(key="abcdef.bin")

    assert await storage_case.storage.exists(key="abcdef.bin") is False
    assert await storage_case.storage.get(key="abcdef.bin") is None
    if storage_case.provider is not None:
        assert storage_case.provider.list_calls == 0


def test_shared_visibility_controls_anonymous_addressing(storage_case):
    url = storage_case.storage.url_for(key="abcdef.bin")
    parsed = urlsplit(url)

    assert storage_case.storage.visibility is storage_case.visibility
    assert parsed.query == ""  # never expose account keys or SAS tokens
    if storage_case.visibility is BlobVisibility.PUBLIC:
        assert "/public/ab/abcdef.bin" in url or "/contract/ab/abcdef.bin" in url
    else:
        assert url.startswith(f"/protected/{storage_case.visibility.value}/")
        assert parsed.scheme == ""
        assert ".blob." not in url


@pytest.mark.asyncio
async def test_shared_miss_uses_direct_address_without_listing(storage_case):
    assert await storage_case.storage.get(key="missing.bin") is None
    assert await storage_case.storage.exists(key="missing.bin") is False
    if storage_case.provider is not None:
        assert storage_case.provider.list_calls == 0
