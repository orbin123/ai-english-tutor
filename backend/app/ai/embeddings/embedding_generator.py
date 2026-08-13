"""OpenAI embedding generator — produces vectors for RAG memory documents.

Uses ``text-embedding-3-small`` with reduced dimensionality (1024) for
cost-efficiency. At $0.02/1M tokens, embedding a ~200-token feedback doc
costs roughly $0.000004 — negligible even at scale.

The ``dimensions`` parameter is an OpenAI API feature that truncates the
full 1536-dim vector down to the requested size using Matryoshka
representation learning, preserving most of the semantic fidelity.
"""

from __future__ import annotations

import asyncio
import logging

import openai

from app.core.ai_concurrency import ai_provider_slot
from app.core.config import settings

logger = logging.getLogger(__name__)


class OpenAIEmbeddingGenerator:
    """Generate embedding vectors using OpenAI's embeddings API.

    Stateless — safe to reuse across requests.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        dimensions: int | None = None,
    ) -> None:
        self._model = model or settings.OPENAI_EMBEDDING_MODEL
        self._dimensions = dimensions or settings.OPENAI_EMBEDDING_DIMENSIONS
        self._client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def embed(self, text: str) -> list[float]:
        """Return an embedding vector for a single text string."""
        async with ai_provider_slot():
            response = await asyncio.wait_for(
                self._client.embeddings.create(
                    input=text,
                    model=self._model,
                    dimensions=self._dimensions,
                ),
                timeout=settings.OPENAI_EMBEDDING_TIMEOUT_S,
            )
        return response.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in a single API call for efficiency."""
        if not texts:
            return []
        async with ai_provider_slot():
            response = await asyncio.wait_for(
                self._client.embeddings.create(
                    input=texts,
                    model=self._model,
                    dimensions=self._dimensions,
                ),
                timeout=settings.OPENAI_EMBEDDING_TIMEOUT_S,
            )
        # Sort by index to preserve input order.
        sorted_data = sorted(response.data, key=lambda d: d.index)
        return [d.embedding for d in sorted_data]
