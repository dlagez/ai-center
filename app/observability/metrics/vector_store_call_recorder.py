from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.exceptions import VectorStoreError
from app.runtime.retrieval.vector_store.schemas import (
    EnsureCollectionRequest,
    EnsureCollectionResult,
    VectorDeleteRequest,
    VectorDeleteResult,
    VectorQueryRequest,
    VectorQueryResult,
    VectorUpsertRequest,
    VectorUpsertResult,
)


class VectorStoreCallRecord(BaseModel):
    trace_id: str
    operation: str
    provider: str
    collection_name: str
    tenant_id: str | None = None
    app_id: str | None = None
    knowledge_base_id: str | None = None
    index_name: str | None = None
    index_version: str | None = None
    latency_ms: int | None = None
    total_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    hit_count: int = 0
    status: str
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InMemoryVectorStoreCallRecorder:
    def __init__(self) -> None:
        self._records: list[VectorStoreCallRecord] = []

    @property
    def records(self) -> list[VectorStoreCallRecord]:
        return list(self._records)

    def record_ensure_success(
        self,
        request: EnsureCollectionRequest,
        result: EnsureCollectionResult,
    ) -> None:
        self._records.append(
            VectorStoreCallRecord(
                trace_id=result.trace_id,
                operation="ensure_collection",
                provider=result.provider,
                collection_name=result.collection_name,
                tenant_id=request.tenant_id,
                app_id=request.app_id,
                knowledge_base_id=request.knowledge_base_id,
                index_name=request.index_name,
                index_version=request.index_version,
                latency_ms=result.latency_ms,
                total_count=1,
                success_count=1,
                status="success",
            )
        )

    def record_upsert_success(
        self,
        request: VectorUpsertRequest,
        result: VectorUpsertResult,
    ) -> None:
        self._records.append(
            VectorStoreCallRecord(
                trace_id=result.trace_id,
                operation="upsert_records",
                provider=result.provider,
                collection_name=result.collection_name,
                tenant_id=request.tenant_id,
                app_id=request.app_id,
                knowledge_base_id=request.knowledge_base_id,
                index_name=request.index_name,
                index_version=request.index_version,
                latency_ms=result.latency_ms,
                total_count=result.total_count,
                success_count=result.success_count,
                failed_count=result.failed_count,
                status="success",
                metadata=dict(request.metadata),
            )
        )

    def record_query_success(
        self,
        request: VectorQueryRequest,
        result: VectorQueryResult,
    ) -> None:
        self._records.append(
            VectorStoreCallRecord(
                trace_id=result.trace_id,
                operation="query_vectors",
                provider=result.provider,
                collection_name=result.collection_name,
                tenant_id=request.tenant_id,
                app_id=request.app_id,
                knowledge_base_id=request.knowledge_base_id,
                index_name=request.index_name,
                index_version=request.index_version,
                latency_ms=result.latency_ms,
                hit_count=result.total_hits,
                status="success",
                metadata={
                    **request.metadata,
                    "top_k": request.top_k,
                    "filter_keys": sorted(request.filters.keys()),
                },
            )
        )

    def record_delete_success(
        self,
        request: VectorDeleteRequest,
        result: VectorDeleteResult,
    ) -> None:
        self._records.append(
            VectorStoreCallRecord(
                trace_id=result.trace_id,
                operation="delete_records",
                provider=result.provider,
                collection_name=result.collection_name,
                tenant_id=request.tenant_id,
                app_id=request.app_id,
                knowledge_base_id=request.knowledge_base_id,
                index_name=request.index_name,
                index_version=request.index_version,
                latency_ms=result.latency_ms,
                total_count=result.requested_count,
                success_count=result.deleted_count,
                failed_count=max(0, result.requested_count - result.deleted_count),
                status="success",
                metadata=dict(request.metadata),
            )
        )

    def record_failure(
        self,
        *,
        operation: str,
        request: Any,
        trace_id: str,
        provider: str,
        collection_name: str,
        error: VectorStoreError,
    ) -> None:
        self._records.append(
            VectorStoreCallRecord(
                trace_id=trace_id,
                operation=operation,
                provider=provider,
                collection_name=collection_name,
                tenant_id=getattr(request, "tenant_id", None),
                app_id=getattr(request, "app_id", None),
                knowledge_base_id=getattr(request, "knowledge_base_id", None),
                index_name=getattr(request, "index_name", None),
                index_version=getattr(request, "index_version", None),
                status="error",
                error_code=error.code,
                error_message=str(error),
                metadata=dict(getattr(request, "metadata", {}) or {}),
            )
        )
