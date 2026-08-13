"""S3 implementation of IBlobStorage.

For production on Fargate, where the container filesystem is ephemeral and
there can be more than one task — local disk (`LocalBlobStorage`) cannot be
shared or survive a redeploy, so generated media must live in S3.

Two URL modes, selected by the factory in `__init__.py`:

  * **public** (`public_url_base` set) — the blob is served via CloudFront.
    `url_for` returns `<cdn-base>/<object-key>`. Used for TTS audio, generated
    images, blog covers: content that the browser fetches directly.
  * **private** (`internal_url_prefix` set) — the blob is NOT public. `url_for`
    returns an app route path (`<prefix>/<shard>/<key>`) that an owner-checked
    FastAPI route streams from S3 via `get`. Used for learner audio recordings.

The on-disk shard layout of `LocalBlobStorage` is preserved as the S3 key
layout (`<key-prefix>/<shard>/<key>`) so a blob written by one backend resolves
to the same logical location under the other, and the hash-cache `exists`/
`url_for` lookups stay consistent across a local→S3 migration.

boto3 is synchronous; every network call is wrapped in `asyncio.to_thread` so
the event loop stays responsive — exactly the pattern `LocalBlobStorage` uses
for disk I/O, where it actually matters here.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from app.ai.storage.exceptions import (
    StorageError,
    StorageReadError,
    StorageWriteError,
)
from app.ai.storage.interface import BlobVisibility, StoredBlob

if TYPE_CHECKING:
    from botocore.client import BaseClient

logger = logging.getLogger(__name__)


class S3BlobStorage:
    """S3-backed implementation of `IBlobStorage`.

    Credentials come from the ambient AWS environment — in production the ECS
    **task role** (no keys in env); locally the developer's AWS profile. The
    constructor accepts an injected client so tests can pass an in-memory fake
    and never touch AWS.
    """

    def __init__(
        self,
        *,
        bucket: str,
        key_prefix: str,
        region: str | None = None,
        public_url_base: str | None = None,
        internal_url_prefix: str | None = None,
        visibility: BlobVisibility | None = None,
        client: Any | None = None,
    ) -> None:
        """
        Args:
            bucket: S3 bucket name holding the blobs.
            key_prefix: Logical namespace within the bucket, e.g. "audio".
                Combined with the shard to form the object key. No slashes.
            region: AWS region for the lazily-built client (defaults to the
                ambient region if None).
            public_url_base: CloudFront base URL for public blobs, e.g.
                "https://media.lingosai.com". Mutually exclusive with
                `internal_url_prefix`.
            internal_url_prefix: App route prefix for private blobs, e.g.
                "/responses/audio". Mutually exclusive with `public_url_base`.
            client: Optional pre-built boto3 S3 client (for tests).
        """
        if visibility is None:
            if bool(public_url_base) == bool(internal_url_prefix):
                raise StorageError(
                    "S3BlobStorage requires exactly one of public_url_base or "
                    "internal_url_prefix to be set"
                )
            visibility = (
                BlobVisibility.PUBLIC if public_url_base else BlobVisibility.PRIVATE
            )
        if visibility is BlobVisibility.PUBLIC:
            valid_url_mode = bool(public_url_base) and not internal_url_prefix
        else:
            valid_url_mode = bool(internal_url_prefix) and not public_url_base
        if not valid_url_mode:
            raise StorageError(
                f"S3BlobStorage visibility={visibility.value!r} has an invalid URL mode"
            )
        self._bucket = bucket
        self._key_prefix = key_prefix.strip("/")
        self._region = region
        self._public_url_base = (public_url_base or "").rstrip("/")
        self._internal_url_prefix = (internal_url_prefix or "").rstrip("/")
        self._visibility = visibility
        self._client = client
        logger.info(
            "s3_blob_storage_init bucket=%s key_prefix=%s visibility=%s",
            self._bucket,
            self._key_prefix,
            self._visibility,
        )

    # ------------------------------------------------------------------
    # Public — IBlobStorage contract
    # ------------------------------------------------------------------
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
        """Upload `data` to S3 under `key`. Idempotent — re-putting the same
        key overwrites with identical bytes (S3 PUT is last-writer-wins)."""
        object_key = self._object_key(key)
        try:
            await asyncio.to_thread(self._sync_put, object_key, data, content_type)
        except Exception as exc:  # noqa: BLE001 — normalize to StorageWriteError
            raise StorageWriteError(
                f"Failed to put blob key={key!r} object={object_key!r}: {exc}"
            ) from exc

        public_url = self.url_for(key=key)
        size = len(data)
        logger.info(
            "blob_stored backend=s3 key=%s size=%d content_type=%s",
            key,
            size,
            content_type,
        )
        return StoredBlob(
            public_url=public_url,
            storage_key=key,
            content_type=content_type,
            size_bytes=size,
        )

    async def get(self, *, key: str) -> bytes | None:
        """Download bytes for `key`. Returns None on a miss (NOT an error)."""
        object_key = self._object_key(key)
        try:
            return await asyncio.to_thread(self._sync_get, object_key)
        except _S3NotFound:
            return None
        except Exception as exc:  # noqa: BLE001 — normalize to StorageReadError
            raise StorageReadError(
                f"Failed to get blob key={key!r} object={object_key!r}: {exc}"
            ) from exc

    async def exists(self, *, key: str) -> bool:
        """HEAD the object — does NOT pull bytes. False on a miss."""
        object_key = self._object_key(key)
        try:
            return await asyncio.to_thread(self._sync_head, object_key)
        except Exception as exc:  # noqa: BLE001 — normalize to StorageReadError
            raise StorageReadError(
                f"Failed to stat blob key={key!r} object={object_key!r}: {exc}"
            ) from exc

    async def delete(self, *, key: str) -> None:
        """Delete one directly addressed object; S3 deletion is idempotent."""
        object_key = self._object_key(key)
        try:
            await asyncio.to_thread(self._sync_delete, object_key)
        except Exception as exc:  # noqa: BLE001
            raise StorageWriteError(
                f"Failed to delete blob key={key!r} object={object_key!r}: {exc}"
            ) from exc

    def url_for(self, *, key: str) -> str:
        """Return the fetchable URL for `key` without any network call.

        Public mode → CloudFront URL over the full object key. Private mode →
        the owner-checked app route path (shard layout matches the route).
        """
        object_key = self._object_key(key)
        if self._public_url_base:
            return f"{self._public_url_base}/{object_key}"
        # Private: the serving route is `<prefix>/<shard>/<key>`.
        return f"{self._internal_url_prefix}/{key[:2]}/{key}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _object_key(self, key: str) -> str:
        """Map a blob key to its S3 object key, mirroring local sharding.

        Same validation as `LocalBlobStorage._key_to_path`: reject path
        separators / '..' so a crafted key cannot escape the prefix, and
        require >=2 chars for the shard.
        """
        if "/" in key or "\\" in key or ".." in key:
            raise StorageError(
                f"Invalid blob key (contains path separator or '..'): {key!r}"
            )
        if len(key) < 2:
            raise StorageError(f"Blob key too short: {key!r}")
        return f"{self._key_prefix}/{key[:2]}/{key}"

    def _get_client(self) -> BaseClient:
        if self._client is None:
            import boto3  # lazy: keeps `import app.ai.storage` cheap

            self._client = boto3.client("s3", region_name=self._region)
        return self._client

    def _sync_put(self, object_key: str, data: bytes, content_type: str) -> None:
        self._get_client().put_object(
            Bucket=self._bucket,
            Key=object_key,
            Body=data,
            ContentType=content_type,
        )

    def _sync_get(self, object_key: str) -> bytes:
        try:
            resp = self._get_client().get_object(Bucket=self._bucket, Key=object_key)
        except Exception as exc:  # noqa: BLE001
            if _is_not_found(exc):
                raise _S3NotFound() from exc
            raise
        body = resp["Body"].read()
        assert isinstance(body, bytes)
        return body

    def _sync_head(self, object_key: str) -> bool:
        try:
            self._get_client().head_object(Bucket=self._bucket, Key=object_key)
        except Exception as exc:  # noqa: BLE001
            if _is_not_found(exc):
                return False
            raise
        return True

    def _sync_delete(self, object_key: str) -> None:
        self._get_client().delete_object(Bucket=self._bucket, Key=object_key)


class _S3NotFound(Exception):
    """Internal sentinel: object does not exist (→ get returns None)."""


def _is_not_found(exc: Exception) -> bool:
    """True if a boto3 exception means 'object not found' (404/NoSuchKey).

    Checked structurally so we don't import botocore at module load.
    """
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        error = response.get("Error", {})
        code = str(error.get("Code", ""))
        if code in ("404", "NoSuchKey", "NotFound"):
            return True
        status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if status == 404:
            return True
    return False
