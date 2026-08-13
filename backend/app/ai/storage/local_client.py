"""Local-disk implementation of IBlobStorage.

For development + early MVP. Stores blobs as files on disk under a
configurable root, sharded by the first 2 chars of the key so we never
end up with one giant flat directory of thousands of files.

Public URL is served by FastAPI's StaticFiles mount (set up in
`app/main.py`) — there is no cloud, no presigning, no auth on the URL.
That's intentional for MVP: anyone with the URL can fetch the audio,
which is fine because the URL itself is non-guessable (hash-based).

Swap to S3 / R2: write `S3BlobStorage` implementing the same interface,
flip a factory in `__init__.py`. Callers don't change.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.ai.storage.exceptions import (
    StorageError,
    StorageReadError,
    StorageWriteError,
)
from app.ai.storage.interface import BlobVisibility, StoredBlob

logger = logging.getLogger(__name__)


class LocalBlobStorage:
    """Local-filesystem implementation of `IBlobStorage`.

    Why a class (not module-level functions)? Two reasons:
      1. Tests can construct one with a tmpdir root, no monkey-patching.
      2. A future S3BlobStorage will need state (bucket name, region,
         credentials). Keeping the contract symmetric now makes the
         swap one line.
    """

    def __init__(
        self,
        *,
        root_dir: Path,
        public_url_prefix: str,
        visibility: BlobVisibility = BlobVisibility.PUBLIC,
    ) -> None:
        """
        Args:
            root_dir: Where blobs live on disk. Created if missing.
            public_url_prefix: URL prefix the StaticFiles mount serves
                under, e.g. "/audio". Must NOT have a trailing slash.
        """
        self._root = Path(root_dir).resolve()
        # Strip any trailing slash so we can join cleanly later.
        self._url_prefix = public_url_prefix.rstrip("/")
        self._visibility = visibility
        # Eagerly create the root so first-write doesn't race.
        self._root.mkdir(parents=True, exist_ok=True)
        logger.info(
            "local_blob_storage_init root=%s url_prefix=%s visibility=%s",
            self._root,
            self._url_prefix,
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
        """Write `data` to disk under `key`. Idempotent — same key + same
        bytes = no-op cost-wise (we still rewrite, but the OS treats it
        as the same inode-class operation; not worth a hash check)."""
        path = self._key_to_path(key)
        # asyncio.to_thread keeps the event loop responsive while the
        # disk write happens. For local SSD this is microseconds, but
        # the same client interface will run against S3 later where it
        # really matters.
        try:
            await asyncio.to_thread(self._sync_write, path, data)
        except OSError as exc:
            raise StorageWriteError(
                f"Failed to write blob key={key!r} path={path}: {exc}"
            ) from exc

        public_url = self._public_url_for(key)
        size = len(data)
        logger.info(
            "blob_stored key=%s size=%d content_type=%s",
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
        """Read bytes for `key`. Returns None on miss (NOT an error)."""
        path = self._key_to_path(key)
        if not path.exists():
            return None
        try:
            return await asyncio.to_thread(path.read_bytes)
        except OSError as exc:
            raise StorageReadError(
                f"Failed to read blob key={key!r} path={path}: {exc}"
            ) from exc

    async def exists(self, *, key: str) -> bool:
        """Cheap stat() — does NOT pull bytes."""
        path = self._key_to_path(key)
        # Path.exists() is sync but only does one stat() — fine inline.
        return path.exists()

    async def delete(self, *, key: str) -> None:
        """Delete one directly addressed file; a missing file is a no-op."""
        path = self._key_to_path(key)
        try:
            await asyncio.to_thread(path.unlink, missing_ok=True)
        except OSError as exc:
            raise StorageWriteError(
                f"Failed to delete blob key={key!r} path={path}: {exc}"
            ) from exc

    def url_for(self, *, key: str) -> str:
        """Return the public URL for `key` without touching the disk."""
        # Re-use the same validation path as read/write helpers so a
        # malformed key fails consistently instead of building a bogus URL.
        self._key_to_path(key)
        return self._public_url_for(key)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _key_to_path(self, key: str) -> Path:
        """Resolve a blob key to an absolute filesystem path.

        Sharding rule: the first 2 chars of the key become a subfolder.
        This caps any single directory at ~256 entries (16² for hex
        keys) so directory-listing performance stays sane even with
        100k+ cached blobs.

        Security: we reject keys containing path separators or '..'
        components so a malicious key like "../../etc/passwd" can't
        escape our root.
        """
        if "/" in key or "\\" in key or ".." in key:
            raise StorageError(
                f"Invalid blob key (contains path separator or '..'): {key!r}"
            )
        if len(key) < 2:
            raise StorageError(f"Blob key too short: {key!r}")

        shard = key[:2]
        # Final extension comes from the caller via a key like
        # "abc123.mp3". If there's no extension we just use the key as
        # the filename.
        return self._root / shard / key

    def _public_url_for(self, key: str) -> str:
        """Translate a key to the URL the frontend will fetch.

        URL layout matches the on-disk shard layout: `<prefix>/<shard>/<key>`.
        Both must agree because StaticFiles serves files relative to the
        cache root — if the URL omits the shard, the request 404s.
        """
        shard = key[:2]
        return f"{self._url_prefix}/{shard}/{key}"

    @staticmethod
    def _sync_write(path: Path, data: bytes) -> None:
        """Atomic-ish write: tmp file + rename. Stops a half-written
        file from being served if the process crashes mid-write."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
