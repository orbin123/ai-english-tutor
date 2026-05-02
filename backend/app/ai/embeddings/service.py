"""High-level embedding pipeline: text + metadata -> Pinecone.

Sits between business code (ResponseService) and the raw clients.
The contract: caller gives us text + metadata, we return the vector ID
that was stored in Pinecone (so caller can persist it back to Postgres).
"""

import asyncio
import logging
from typing import Any

from app.ai.embeddings.client import hf_embed, pinecone_upsert

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Embed text and store the vector in Pinecone.

    Stateless — safe to instantiate per-request.
    Not bound to any specific entity (UserResponse, Task, etc.) — the
    caller decides the vector_id format.
    """

    async def embed_and_store(
        self,
        *,
        vector_id: str,
        text: str,
        metadata: dict[str, Any],
    ) -> str:
        """Embed `text`, store in Pinecone under `vector_id`, return the id.

        Steps:
          1. Call HF -> 384-dim list[float]
          2. Call Pinecone upsert (sync SDK, run in thread)

        Raises:
          HFEmbeddingFailed   -- HF API failed
          PineconeUpsertFailed -- Pinecone rejected the write

        Caller decides whether to block, retry, or log on these errors.
        """
        # 1. Embed
        values = await hf_embed(text)

        # 2. Upsert (sync SDK -> off-load to thread so event loop stays free)
        await asyncio.to_thread(
            pinecone_upsert,
            vector_id=vector_id,
            values=values,
            metadata=metadata,
        )

        logger.info("Embedded + upserted vector_id=%s", vector_id)
        return vector_id