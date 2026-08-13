"""S3BlobStorage + build_blob_storage factory — no live AWS.

A fake boto3 S3 client (in-memory dict keyed by object key) exercises the full
put/get/exists/url_for contract, the shard key layout, and the public-vs-private
URL selection. The factory test confirms `STORAGE_BACKEND` routes to the right
implementation without touching settings the rest of the suite relies on.
"""

import pytest

from app.ai.storage import (
    BlobVisibility,
    LocalBlobStorage,
    S3BlobStorage,
    build_blob_storage,
)
from app.ai.storage.exceptions import (
    StorageError,
    StorageReadError,
    StorageWriteError,
)
from app.core.config import settings


class _FakeS3Client:
    """Minimal in-memory S3 stand-in covering the calls S3BlobStorage makes."""

    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.put_errors = 0  # set >0 to make the next N puts raise

    def put_object(self, *, Bucket, Key, Body, ContentType):  # noqa: N803
        if self.put_errors > 0:
            self.put_errors -= 1
            raise RuntimeError("boom")
        self.store[Key] = Body

    def get_object(self, *, Bucket, Key):  # noqa: N803
        if Key not in self.store:
            raise self._not_found()
        return {"Body": _Body(self.store[Key])}

    def head_object(self, *, Bucket, Key):  # noqa: N803
        if Key not in self.store:
            raise self._not_found()
        return {}

    def delete_object(self, *, Bucket, Key):  # noqa: N803
        self.store.pop(Key, None)

    @staticmethod
    def _not_found():
        exc = RuntimeError("not found")
        exc.response = {  # type: ignore[attr-defined]
            "Error": {"Code": "NoSuchKey"},
            "ResponseMetadata": {"HTTPStatusCode": 404},
        }
        return exc


class _Body:
    def __init__(self, data: bytes):
        self._data = data

    def read(self) -> bytes:
        return self._data


def _public_storage(client) -> S3BlobStorage:
    return S3BlobStorage(
        bucket="media-bucket",
        key_prefix="audio",
        public_url_base="https://media.lingosai.com",
        client=client,
    )


def _private_storage(client) -> S3BlobStorage:
    return S3BlobStorage(
        bucket="media-bucket",
        key_prefix="responses/audio",
        internal_url_prefix="/responses/audio",
        client=client,
    )


@pytest.mark.asyncio
class TestS3BlobStorageContract:
    async def test_put_then_get_round_trips(self):
        fake = _FakeS3Client()
        storage = _public_storage(fake)
        stored = await storage.put(
            key="abcdef.mp3", data=b"hello", content_type="audio/mpeg"
        )
        assert stored["storage_key"] == "abcdef.mp3"
        assert stored["size_bytes"] == 5
        assert await storage.get(key="abcdef.mp3") == b"hello"

    async def test_object_key_uses_shard_layout(self):
        fake = _FakeS3Client()
        storage = _public_storage(fake)
        await storage.put(key="abcdef.mp3", data=b"x", content_type="audio/mpeg")
        # <key_prefix>/<first-2-chars>/<key> — mirrors LocalBlobStorage sharding.
        assert "audio/ab/abcdef.mp3" in fake.store

    async def test_get_miss_returns_none(self):
        storage = _public_storage(_FakeS3Client())
        assert await storage.get(key="missing.mp3") is None

    async def test_exists_true_then_false(self):
        fake = _FakeS3Client()
        storage = _public_storage(fake)
        assert await storage.exists(key="abcdef.mp3") is False
        await storage.put(key="abcdef.mp3", data=b"x", content_type="audio/mpeg")
        assert await storage.exists(key="abcdef.mp3") is True

    async def test_put_failure_raises_write_error(self):
        fake = _FakeS3Client()
        fake.put_errors = 1
        with pytest.raises(StorageWriteError):
            await _public_storage(fake).put(
                key="abcdef.mp3", data=b"x", content_type="audio/mpeg"
            )

    async def test_invalid_key_rejected(self):
        storage = _public_storage(_FakeS3Client())
        with pytest.raises(StorageError):
            await storage.put(key="../escape", data=b"x", content_type="text/plain")

    async def test_read_error_normalized(self, monkeypatch):
        class _BadClient(_FakeS3Client):
            def get_object(self, *, Bucket, Key):  # noqa: N803
                raise RuntimeError("transient s3 failure")

        with pytest.raises(StorageReadError):
            await _public_storage(_BadClient()).get(key="abcdef.mp3")


class TestUrlModes:
    def test_public_url_is_cloudfront_over_object_key(self):
        storage = _public_storage(_FakeS3Client())
        assert (
            storage.url_for(key="abcdef.mp3")
            == "https://media.lingosai.com/audio/ab/abcdef.mp3"
        )

    def test_private_url_is_owner_checked_route(self):
        storage = _private_storage(_FakeS3Client())
        # Matches the GET /responses/audio/{shard}/{key} streaming route.
        assert storage.url_for(key="abcdef.webm") == "/responses/audio/ab/abcdef.webm"

    def test_requires_exactly_one_url_mode(self):
        with pytest.raises(StorageError):
            S3BlobStorage(bucket="b", key_prefix="p")  # neither
        with pytest.raises(StorageError):
            S3BlobStorage(
                bucket="b",
                key_prefix="p",
                public_url_base="https://x",
                internal_url_prefix="/y",
            )  # both


class TestFactory:
    def test_local_backend_returns_local(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
        storage = build_blob_storage(cache_dir=tmp_path, public_url_prefix="/audio")
        assert isinstance(storage, LocalBlobStorage)

    def test_s3_public_backend(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "STORAGE_BACKEND", "s3")
        monkeypatch.setattr(settings, "MEDIA_S3_BUCKET", "media-bucket")
        monkeypatch.setattr(settings, "MEDIA_CDN_URL", "https://cdn.lingosai.com")
        storage = build_blob_storage(cache_dir=tmp_path, public_url_prefix="/audio")
        assert isinstance(storage, S3BlobStorage)
        assert (
            storage.url_for(key="abcdef.mp3")
            == "https://cdn.lingosai.com/audio/ab/abcdef.mp3"
        )

    def test_s3_private_backend(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "STORAGE_BACKEND", "s3")
        monkeypatch.setattr(settings, "MEDIA_S3_BUCKET", "media-bucket")
        monkeypatch.setattr(settings, "MEDIA_CDN_URL", "https://cdn.lingosai.com")
        storage = build_blob_storage(
            cache_dir=tmp_path,
            public_url_prefix="/responses/audio",
            visibility=BlobVisibility.PRIVATE,
        )
        assert isinstance(storage, S3BlobStorage)
        # Private blobs never get a CDN URL.
        assert storage.url_for(key="abcdef.webm").startswith("/responses/audio/")
