from __future__ import annotations

from abc import ABC, abstractmethod

from app.runtime.retrieval.vector_store.schemas import (
    EnsureCollectionRequest,
    EnsureCollectionResult,
    VectorDeleteRequest,
    VectorDeleteResult,
    VectorDocumentLookupRequest,
    VectorDocumentLookupResult,
    VectorQueryRequest,
    VectorQueryResult,
    VectorStoreCapabilities,
    VectorUpsertRequest,
    VectorUpsertResult,
)


class BaseVectorStoreAdapter(ABC):
    provider_name: str

    def close(self) -> None:
        return None

    @abstractmethod
    def ensure_collection(
        self,
        *,
        collection_name: str,
        request: EnsureCollectionRequest,
        trace_id: str,
    ) -> EnsureCollectionResult:
        raise NotImplementedError

    @abstractmethod
    def upsert(
        self,
        *,
        collection_name: str,
        request: VectorUpsertRequest,
        trace_id: str,
    ) -> VectorUpsertResult:
        raise NotImplementedError

    @abstractmethod
    def query(
        self,
        *,
        collection_name: str,
        request: VectorQueryRequest,
        trace_id: str,
    ) -> VectorQueryResult:
        raise NotImplementedError

    @abstractmethod
    def delete(
        self,
        *,
        collection_name: str,
        request: VectorDeleteRequest,
        trace_id: str,
    ) -> VectorDeleteResult:
        raise NotImplementedError

    @abstractmethod
    def lookup_document(
        self,
        *,
        collection_name: str,
        request: VectorDocumentLookupRequest,
        trace_id: str,
    ) -> VectorDocumentLookupResult:
        raise NotImplementedError

    @abstractmethod
    def describe_capabilities(self) -> VectorStoreCapabilities:
        raise NotImplementedError
