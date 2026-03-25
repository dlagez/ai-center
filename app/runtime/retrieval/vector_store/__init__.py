"""Vector store runtime abstractions."""

from app.runtime.retrieval.vector_store.schemas import (
    EnsureCollectionRequest,
    EnsureCollectionResult,
    VectorDeleteRequest,
    VectorDeleteResult,
    VectorHit,
    VectorQueryRequest,
    VectorQueryResult,
    VectorRecord,
    VectorStoreCapabilities,
    VectorUpsertRequest,
    VectorUpsertResult,
)
from app.runtime.retrieval.vector_store.service import (
    VectorStoreService,
    build_default_vector_store_service,
)

__all__ = [
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
