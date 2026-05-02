"""Embeddings + vector storage for user responses (and future entities)."""

from app.ai.embeddings.exceptions import (
    EmbeddingError,
    HFEmbeddingFailed,
    PineconeUpsertFailed,
)
from app.ai.embeddings.service import EmbeddingService

__all__ = [
    "EmbeddingError",
    "EmbeddingService",
    "HFEmbeddingFailed",
    "PineconeUpsertFailed",
]