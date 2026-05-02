"""Low-level clients for HuggingFace embeddings + Pinecone vector DB.

These wrap the SDKs but do NOT know anything about business logic
(user_responses, task_ids, etc). They speak in raw text -> floats.
"""

import logging

import httpx
from pinecone import Pinecone

from app.ai.embeddings.exceptions import (
    HFEmbeddingFailed,
    PineconeUpsertFailed,
)
from app.core.config import settings

logger = logging.getLogger(__name__)


# ----- HuggingFace -----

_HF_URL = (
    f"https://router.huggingface.co/hf-inference/models/"
    f"{settings.HF_EMBEDDING_MODEL}/pipeline/feature-extraction"
)


async def hf_embed(text: str) -> list[float]:
    """Get a 384-dim embedding for `text` from HuggingFace.

    Raises HFEmbeddingFailed on any non-2xx response or shape mismatch.
    """
    headers = {"Authorization": f"Bearer {settings.HF_API_KEY}"}
    payload = {"inputs": text}

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(_HF_URL, headers=headers, json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("HF embed HTTP error: %s", e)
            raise HFEmbeddingFailed(f"HF API call failed: {e}") from e

    data = resp.json()
    # Sentence-transformers models return: list[float] of length 384
    if not isinstance(data, list) or len(data) != settings.EMBEDDING_DIMENSION:
        raise HFEmbeddingFailed(
            f"Unexpected HF response shape: type={type(data)}, "
            f"len={len(data) if hasattr(data, '__len__') else 'n/a'}"
        )
    return data


# ----- Pinecone -----

# Built once on import. Pinecone client is lightweight + thread-safe.
_pc = Pinecone(api_key=settings.PINECONE_API_KEY)
_index = _pc.Index(settings.PINECONE_INDEX_NAME)


def pinecone_upsert(
    *, vector_id: str, values: list[float], metadata: dict
) -> None:
    """Upsert a single vector into the configured Pinecone index.

    Raises PineconeUpsertFailed on any SDK error.
    """
    try:
        _index.upsert(
            vectors=[
                {"id": vector_id, "values": values, "metadata": metadata}
            ]
        )
    except Exception as e:  # pinecone SDK throws various subclasses
        logger.warning("Pinecone upsert error: %s", e)
        raise PineconeUpsertFailed(f"Pinecone upsert failed: {e}") from e