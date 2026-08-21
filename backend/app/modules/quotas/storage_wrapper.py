"""Blob storage wrapper that counts writes against monthly quota."""

from __future__ import annotations

from app.ai.storage.interface import BlobVisibility, IBlobStorage, StoredBlob
from app.core.database import SessionLocal
from app.modules.quotas.constants import QuotaMetric
from app.modules.quotas.service import QuotaService


class QuotaTrackingBlobStorage:
    """Delegate to an inner storage client and increment blob-write quota."""

    def __init__(self, inner: IBlobStorage) -> None:
        self._inner = inner

    @property
    def visibility(self) -> BlobVisibility:
        return self._inner.visibility

    async def put(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str,
    ) -> StoredBlob:
        db = SessionLocal()
        try:
            QuotaService(db).consume(QuotaMetric.BLOB_WRITES)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        return await self._inner.put(key=key, data=data, content_type=content_type)

    async def get(self, *, key: str) -> bytes | None:
        return await self._inner.get(key=key)

    async def exists(self, *, key: str) -> bool:
        return await self._inner.exists(key=key)

    async def delete(self, *, key: str) -> None:
        await self._inner.delete(key=key)

    def url_for(self, *, key: str) -> str:
        return self._inner.url_for(key=key)
