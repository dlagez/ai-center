"""Retrieval runtime capabilities."""

from app.runtime.retrieval.gateway_service import (
    RetrieverService,
    build_default_retriever_service,
)
from app.runtime.retrieval.schemas import RetrievalHit, RetrievalRequest, RetrievalResult
from app.runtime.retrieval.vector_store import (
    EnsureCollectionRequest,
    EnsureCollectionResult,
    VectorDeleteRequest,
    VectorDeleteResult,
    VectorHit,
    VectorQueryRequest,
    VectorQueryResult,
    VectorRecord,
    VectorStoreCapabilities,
    VectorStoreService,
    VectorUpsertRequest,
    VectorUpsertResult,
    build_default_vector_store_service,
)

__all__ = [
    "RetrieverService",
    "build_default_retriever_service",
    "RetrievalHit",
    "RetrievalRequest",
    "RetrievalResult",
    "EnsureCollectionRequest",
    "EnsureCollectionResult",
    "VectorDeleteRequest",
    "VectorDeleteResult",
    "VectorHit",
    "VectorQueryRequest",
    "VectorQueryResult",
    "VectorRecord",
    "VectorStoreCapabilities",
    "VectorStoreService",
    "VectorUpsertRequest",
    "VectorUpsertResult",
    "build_default_vector_store_service",
]
