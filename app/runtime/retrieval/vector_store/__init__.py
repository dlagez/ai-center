"""Vector store runtime abstractions."""

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


def __getattr__(name: str):
    if name in {
        "EnsureCollectionRequest",
        "EnsureCollectionResult",
        "VectorDeleteRequest",
        "VectorDeleteResult",
        "VectorHit",
        "VectorQueryRequest",
        "VectorQueryResult",
        "VectorRecord",
        "VectorStoreCapabilities",
        "VectorUpsertRequest",
        "VectorUpsertResult",
    }:
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

        exports = {
            "EnsureCollectionRequest": EnsureCollectionRequest,
            "EnsureCollectionResult": EnsureCollectionResult,
            "VectorDeleteRequest": VectorDeleteRequest,
            "VectorDeleteResult": VectorDeleteResult,
            "VectorHit": VectorHit,
            "VectorQueryRequest": VectorQueryRequest,
            "VectorQueryResult": VectorQueryResult,
            "VectorRecord": VectorRecord,
            "VectorStoreCapabilities": VectorStoreCapabilities,
            "VectorUpsertRequest": VectorUpsertRequest,
            "VectorUpsertResult": VectorUpsertResult,
        }
        return exports[name]

    if name in {
        "VectorStoreService",
        "build_default_vector_store_service",
    }:
        from app.runtime.retrieval.vector_store.service import (
            VectorStoreService,
            build_default_vector_store_service,
        )

        exports = {
            "VectorStoreService": VectorStoreService,
            "build_default_vector_store_service": build_default_vector_store_service,
        }
        return exports[name]

    raise AttributeError(name)
