"""Retrieval runtime capabilities."""

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
    "VectorDocumentLookupRequest",
    "VectorDocumentLookupResult",
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
        "RetrievalHit",
        "RetrievalRequest",
        "RetrievalResult",
    }:
        from app.runtime.retrieval.schemas import (
            RetrievalHit,
            RetrievalRequest,
            RetrievalResult,
        )

        exports = {
            "RetrievalHit": RetrievalHit,
            "RetrievalRequest": RetrievalRequest,
            "RetrievalResult": RetrievalResult,
        }
        return exports[name]

    if name in {
        "EnsureCollectionRequest",
        "EnsureCollectionResult",
        "VectorDeleteRequest",
        "VectorDeleteResult",
        "VectorDocumentLookupRequest",
        "VectorDocumentLookupResult",
        "VectorHit",
        "VectorQueryRequest",
        "VectorQueryResult",
        "VectorRecord",
        "VectorStoreCapabilities",
        "VectorStoreService",
        "VectorUpsertRequest",
        "VectorUpsertResult",
        "build_default_vector_store_service",
    }:
        from app.runtime.retrieval.vector_store import (
            EnsureCollectionRequest,
            EnsureCollectionResult,
            VectorDeleteRequest,
            VectorDeleteResult,
            VectorDocumentLookupRequest,
            VectorDocumentLookupResult,
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

        exports = {
            "EnsureCollectionRequest": EnsureCollectionRequest,
            "EnsureCollectionResult": EnsureCollectionResult,
            "VectorDeleteRequest": VectorDeleteRequest,
            "VectorDeleteResult": VectorDeleteResult,
            "VectorDocumentLookupRequest": VectorDocumentLookupRequest,
            "VectorDocumentLookupResult": VectorDocumentLookupResult,
            "VectorHit": VectorHit,
            "VectorQueryRequest": VectorQueryRequest,
            "VectorQueryResult": VectorQueryResult,
            "VectorRecord": VectorRecord,
            "VectorStoreCapabilities": VectorStoreCapabilities,
            "VectorStoreService": VectorStoreService,
            "VectorUpsertRequest": VectorUpsertRequest,
            "VectorUpsertResult": VectorUpsertResult,
            "build_default_vector_store_service": build_default_vector_store_service,
        }
        return exports[name]

    if name in {
        "RetrieverService",
        "build_default_retriever_service",
    }:
        from app.runtime.retrieval.gateway_service import (
            RetrieverService,
            build_default_retriever_service,
        )

        exports = {
            "RetrieverService": RetrieverService,
            "build_default_retriever_service": build_default_retriever_service,
        }
        return exports[name]

    raise AttributeError(name)
