"""Embedding pipeline errors. Caller decides whether to block or log."""


class EmbeddingError(Exception):
    """Base class for all embedding-related failures."""


class HFEmbeddingFailed(EmbeddingError):
    """HuggingFace API returned an error or unexpected response."""


class PineconeUpsertFailed(EmbeddingError):
    """Pinecone rejected the upsert."""