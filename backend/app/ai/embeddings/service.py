"""High-level vector storage pipeline: pre-computed embedding -> Pinecone.

Sits between business code and the raw Pinecone client.
The contract: caller gives us a vector + metadata, we return the vector ID
that was stored in Pinecone (so caller can persist it back to Postgres).

Also supports querying for nearest-neighbour vectors (used by RAG retrieval).
"""

import asyncio
import logging
from typing import Any

from app.ai.embeddings.client import (
    pinecone_delete,
    pinecone_query,
    pinecone_upsert,
)
from app.core.ai_concurrency import ai_provider_slot
from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Store and query embedding vectors in Pinecone.

    Stateless — safe to instantiate per-request.
    Not bound to any specific entity (UserResponse, Task, etc.) — the
    caller decides the vector_id format and produces the embedding upstream.
    """

    async def store(
        self,
        *,
        vector_id: str,
        values: list[float],
        metadata: dict[str, Any],
        namespace: str = "",
    ) -> str:
        """Store `values` in Pinecone under `vector_id`, return the id.

        Raises:
          PineconeUpsertFailed -- Pinecone rejected the write

        Caller decides whether to block, retry, or log on these errors.
        """
        async with ai_provider_slot():
            await asyncio.wait_for(
                asyncio.to_thread(
                    pinecone_upsert,
                    vector_id=vector_id,
                    values=values,
                    metadata=metadata,
                    namespace=namespace,
                ),
                timeout=settings.PINECONE_OPERATION_TIMEOUT_S,
            )

        logger.info("Upserted vector_id=%s namespace=%s", vector_id, namespace)
        return vector_id

    async def query(
        self,
        *,
        values: list[float],
        top_k: int = 10,
        filter: dict | None = None,
        namespace: str = "",
    ) -> list[dict]:
        """Query Pinecone for the `top_k` nearest vectors.

        Returns a list of match dicts with keys: id, score, metadata.

        Raises:
          PineconeQueryFailed -- Pinecone rejected the query
        """
        async with ai_provider_slot():
            matches = await asyncio.wait_for(
                asyncio.to_thread(
                    pinecone_query,
                    values=values,
                    top_k=top_k,
                    filter=filter,
                    namespace=namespace,
                ),
                timeout=settings.PINECONE_OPERATION_TIMEOUT_S,
            )
        logger.info(
            "Queried namespace=%s top_k=%d returned=%d",
            namespace,
            top_k,
            len(matches),
        )
        return matches

    async def delete(
        self,
        *,
        vector_ids: list[str],
        namespace: str = "",
    ) -> None:
        """Delete vectors by id. No-op when ``vector_ids`` is empty.

        Raises:
          PineconeDeleteFailed -- Pinecone rejected the delete
        """
        if not vector_ids:
            return
        async with ai_provider_slot():
            await asyncio.wait_for(
                asyncio.to_thread(
                    pinecone_delete,
                    vector_ids=vector_ids,
                    namespace=namespace,
                ),
                timeout=settings.PINECONE_OPERATION_TIMEOUT_S,
            )
        logger.info(
            "Deleted %d vector(s) namespace=%s",
            len(vector_ids),
            namespace,
        )
