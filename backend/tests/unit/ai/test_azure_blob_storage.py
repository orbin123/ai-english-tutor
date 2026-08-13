"""Azure adapter wiring tests; all SDK clients are in-memory fakes."""

from __future__ import annotations

import pytest

from app.ai.storage import (
    AzureBlobStorage,
    BlobVisibility,
    StorageError,
    build_blob_storage,
)
from app.core.config import settings


class _FakeBlobClient:
    def exists(self) -> bool:
        return False


class _FakeAzureContainerClient:
    def __init__(self) -> None:
        self.list_calls = 0

    def get_blob_client(self, *, blob: str) -> _FakeBlobClient:
        return _FakeBlobClient()


@pytest.mark.parametrize(
    "account_url",
    [
        "https://media.blob.example.test?sig=secret",
        "https://user:password@media.blob.example.test",
        "https://media.blob.example.test/container",
    ],
)
def test_rejects_account_urls_that_could_bypass_managed_identity(account_url):
    with pytest.raises(StorageError, match="credential-free account endpoint"):
        AzureBlobStorage(
            account_url=account_url,
            container="public-media",
            key_prefix="audio",
            visibility=BlobVisibility.PUBLIC,
        )


def test_rejects_absolute_private_media_url():
    with pytest.raises(StorageError, match="application-relative path"):
        AzureBlobStorage(
            account_url="https://private.blob.example.test",
            container="learner-media",
            key_prefix="responses/audio",
            visibility=BlobVisibility.PRIVATE,
            protected_url_prefix="https://private.blob.example.test/learner-media",
        )


@pytest.mark.asyncio
async def test_default_client_uses_default_azure_credential(monkeypatch):
    import azure.identity
    import azure.storage.blob

    container = _FakeAzureContainerClient()
    credential = object()
    observed: dict[str, object] = {}

    class _ServiceClient:
        def __init__(self, *, account_url, credential):
            observed["account_url"] = account_url
            observed["credential"] = credential

        def get_container_client(self, container_name):
            observed["container"] = container_name
            return container

    monkeypatch.setattr(
        azure.identity,
        "DefaultAzureCredential",
        lambda: credential,
    )
    monkeypatch.setattr(azure.storage.blob, "BlobServiceClient", _ServiceClient)

    storage = AzureBlobStorage(
        account_url="https://private.blob.example.test",
        container="learner-media",
        key_prefix="responses/audio",
        visibility=BlobVisibility.PRIVATE,
        protected_url_prefix="/responses/audio",
    )

    assert await storage.exists(key="abcdef.webm") is False
    assert observed == {
        "account_url": "https://private.blob.example.test",
        "credential": credential,
        "container": "learner-media",
    }
    assert container.list_calls == 0


def test_factory_selects_visibility_specific_azure_accounts(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "azure")
    monkeypatch.setattr(
        settings,
        "AZURE_BLOB_PUBLIC_ACCOUNT_URL",
        "https://public.blob.example.test",
    )
    monkeypatch.setattr(
        settings,
        "AZURE_BLOB_PRIVATE_ACCOUNT_URL",
        "https://private.blob.example.test",
    )
    monkeypatch.setattr(settings, "AZURE_BLOB_PUBLIC_CONTAINER", "public-media")
    monkeypatch.setattr(settings, "AZURE_BLOB_PRIVATE_CONTAINER", "learner-media")
    monkeypatch.setattr(settings, "AZURE_BLOB_INTERNAL_CONTAINER", "internal-media")

    public = build_blob_storage(
        cache_dir=tmp_path,
        public_url_prefix="/audio",
        visibility=BlobVisibility.PUBLIC,
    )
    private = build_blob_storage(
        cache_dir=tmp_path,
        public_url_prefix="/responses/audio",
        visibility=BlobVisibility.PRIVATE,
    )
    internal = build_blob_storage(
        cache_dir=tmp_path,
        public_url_prefix="/internal/stt",
        visibility=BlobVisibility.INTERNAL,
    )

    assert isinstance(public, AzureBlobStorage)
    assert isinstance(private, AzureBlobStorage)
    assert isinstance(internal, AzureBlobStorage)
    assert public.url_for(key="abcdef.mp3") == (
        "https://public.blob.example.test/public-media/audio/ab/abcdef.mp3"
    )
    assert private.url_for(key="abcdef.webm").startswith("/responses/audio/")
    assert internal.url_for(key="abcdef.json").startswith("/internal/stt/")
