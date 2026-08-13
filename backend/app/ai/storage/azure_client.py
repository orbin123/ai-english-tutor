"""Azure Blob implementation of :class:`IBlobStorage`.

Runtime authentication is passwordless: the client lazily creates
``DefaultAzureCredential`` so an Azure-hosted process can use its managed
identity. Tests inject a container client and never contact Azure.

Every request addresses one known blob name directly. The adapter never lists
containers or blobs, keeping request paths within the storage transaction
budget and avoiding accidental object-name disclosure.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import quote, urlsplit

from app.ai.storage.exceptions import (
    StorageError,
    StorageReadError,
    StorageWriteError,
)
from app.ai.storage.interface import BlobVisibility, StoredBlob

logger = logging.getLogger(__name__)


class AzureBlobStorage:
    """Managed-identity-compatible Azure Blob storage adapter."""

    def __init__(
        self,
        *,
        account_url: str,
        container: str,
        key_prefix: str,
        visibility: BlobVisibility,
        protected_url_prefix: str | None = None,
        credential: Any | None = None,
        container_client: Any | None = None,
    ) -> None:
        if not account_url.strip():
            raise StorageError("AzureBlobStorage requires account_url")
        parsed_account_url = urlsplit(account_url)
        if (
            not parsed_account_url.scheme
            or not parsed_account_url.netloc
            or parsed_account_url.username
            or parsed_account_url.password
            or parsed_account_url.query
            or parsed_account_url.fragment
            or parsed_account_url.path not in ("", "/")
        ):
            raise StorageError(
                "Azure account_url must be a credential-free account endpoint"
            )
        if not container.strip():
            raise StorageError("AzureBlobStorage requires container")
        if visibility is BlobVisibility.PUBLIC and protected_url_prefix:
            raise StorageError("Public Azure blobs must use their anonymous blob URL")
        if visibility is not BlobVisibility.PUBLIC and not protected_url_prefix:
            raise StorageError(
                f"Azure visibility={visibility.value!r} requires a protected URL prefix"
            )
        if protected_url_prefix:
            parsed_prefix = urlsplit(protected_url_prefix)
            if (
                not protected_url_prefix.startswith("/")
                or parsed_prefix.scheme
                or parsed_prefix.netloc
                or parsed_prefix.query
                or parsed_prefix.fragment
            ):
                raise StorageError(
                    "Azure protected_url_prefix must be an application-relative path"
                )

        self._account_url = account_url.rstrip("/")
        self._container = container.strip("/")
        self._key_prefix = key_prefix.strip("/")
        self._visibility = visibility
        self._protected_url_prefix = (protected_url_prefix or "").rstrip("/")
        self._credential = credential
        self._container_client = container_client
        self._service_client: Any | None = None
        logger.info(
            "azure_blob_storage_init account_url=%s container=%s key_prefix=%s "
            "visibility=%s",
            self._account_url,
            self._container,
            self._key_prefix,
            self._visibility,
        )

    @property
    def visibility(self) -> BlobVisibility:
        return self._visibility

    async def put(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str,
    ) -> StoredBlob:
        object_name = self._object_name(key)
        try:
            await asyncio.to_thread(
                self._sync_put,
                object_name,
                data,
                content_type,
            )
        except Exception as exc:  # noqa: BLE001
            raise StorageWriteError(
                f"Failed to put Azure blob key={key!r} object={object_name!r}: {exc}"
            ) from exc

        return StoredBlob(
            public_url=self.url_for(key=key),
            storage_key=key,
            content_type=content_type,
            size_bytes=len(data),
        )

    async def get(self, *, key: str) -> bytes | None:
        object_name = self._object_name(key)
        try:
            return await asyncio.to_thread(self._sync_get, object_name)
        except Exception as exc:  # noqa: BLE001
            if _is_not_found(exc):
                return None
            raise StorageReadError(
                f"Failed to get Azure blob key={key!r} object={object_name!r}: {exc}"
            ) from exc

    async def exists(self, *, key: str) -> bool:
        object_name = self._object_name(key)
        try:
            result = await asyncio.to_thread(self._sync_exists, object_name)
        except Exception as exc:  # noqa: BLE001
            raise StorageReadError(
                f"Failed to stat Azure blob key={key!r} object={object_name!r}: {exc}"
            ) from exc
        return result

    async def delete(self, *, key: str) -> None:
        object_name = self._object_name(key)
        try:
            await asyncio.to_thread(self._sync_delete, object_name)
        except Exception as exc:  # noqa: BLE001
            if _is_not_found(exc):
                return
            raise StorageWriteError(
                f"Failed to delete Azure blob key={key!r} object={object_name!r}: {exc}"
            ) from exc

    def url_for(self, *, key: str) -> str:
        object_name = self._object_name(key)
        if self._visibility is BlobVisibility.PUBLIC:
            encoded_name = quote(object_name, safe="/")
            return f"{self._account_url}/{self._container}/{encoded_name}"
        return f"{self._protected_url_prefix}/{key[:2]}/{quote(key, safe='')}"

    def _object_name(self, key: str) -> str:
        if "/" in key or "\\" in key or ".." in key:
            raise StorageError(
                f"Invalid blob key (contains path separator or '..'): {key!r}"
            )
        if len(key) < 2:
            raise StorageError(f"Blob key too short: {key!r}")
        return f"{self._key_prefix}/{key[:2]}/{key}"

    def _get_container_client(self) -> Any:
        if self._container_client is None:
            from azure.identity import DefaultAzureCredential
            from azure.storage.blob import BlobServiceClient

            if self._credential is None:
                self._credential = DefaultAzureCredential()
            self._service_client = BlobServiceClient(
                account_url=self._account_url,
                credential=self._credential,
            )
            self._container_client = self._service_client.get_container_client(
                self._container
            )
        return self._container_client

    def _blob_client(self, object_name: str) -> Any:
        return self._get_container_client().get_blob_client(blob=object_name)

    def _sync_put(self, object_name: str, data: bytes, content_type: str) -> None:
        from azure.storage.blob import ContentSettings

        self._blob_client(object_name).upload_blob(
            data,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )

    def _sync_get(self, object_name: str) -> bytes:
        data = self._blob_client(object_name).download_blob().readall()
        if not isinstance(data, bytes):
            raise TypeError("Azure Blob download did not return bytes")
        return data

    def _sync_exists(self, object_name: str) -> bool:
        return bool(self._blob_client(object_name).exists())

    def _sync_delete(self, object_name: str) -> None:
        self._blob_client(object_name).delete_blob(delete_snapshots="include")


def _is_not_found(exc: Exception) -> bool:
    """Recognize Azure's 404 without requiring callers/tests to import it."""
    try:
        from azure.core.exceptions import ResourceNotFoundError

        if isinstance(exc, ResourceNotFoundError):
            return True
    except ImportError:  # pragma: no cover - dependency is installed in runtime
        pass
    return getattr(exc, "status_code", None) == 404
