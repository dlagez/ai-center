from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


MetricType = Literal["cosine", "dot", "euclidean"]


class VectorStoreCapabilities(BaseModel):
    provider: str
    supports_metadata_filter: bool = True
    supports_delete_by_document: bool = True
    supports_collection_schema: bool = True
    supports_namespace: bool = True


class EnsureCollectionRequest(BaseModel):
    tenant_id: str
    app_id: str
    knowledge_base_id: str
    index_name: str
    index_version: str
    dimension: int
    metric_type: MetricType | None = None
    metadata_schema: dict[str, Any] = Field(default_factory=dict)


class EnsureCollectionResult(BaseModel):
    trace_id: str
    provider: str
    collection_name: str
    dimension: int
    metric_type: MetricType
    existed: bool
    created: bool
    latency_ms: int


class VectorRecord(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    vector: list[float]
    metadata: dict[str, Any] = Field(default_factory=dict)


class VectorUpsertRequest(BaseModel):
    tenant_id: str
    app_id: str
    knowledge_base_id: str
    index_name: str
    index_version: str
    records: list[VectorRecord]
    metadata: dict[str, Any] = Field(default_factory=dict)


class VectorUpsertResult(BaseModel):
    trace_id: str
    provider: str
    collection_name: str
    index_version: str
    total_count: int
    success_count: int
    failed_count: int
    latency_ms: int
    errors: list[dict[str, Any]] = Field(default_factory=list)


class VectorQueryRequest(BaseModel):
    tenant_id: str
    app_id: str
    knowledge_base_id: str
    index_name: str
    index_version: str
    query_vector: list[float]
    top_k: int = 10
    filters: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VectorHit(BaseModel):
    chunk_id: str
    document_id: str
    score: float
    text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VectorQueryResult(BaseModel):
    trace_id: str
    provider: str
    collection_name: str
    total_hits: int
    hits: list[VectorHit] = Field(default_factory=list)
    latency_ms: int


class VectorDeleteRequest(BaseModel):
    tenant_id: str
    app_id: str
    knowledge_base_id: str
    index_name: str
    index_version: str
    chunk_ids: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VectorDeleteResult(BaseModel):
    trace_id: str
    provider: str
    collection_name: str
    requested_count: int
    deleted_count: int
    latency_ms: int


class VectorDocumentLookupRequest(BaseModel):
    tenant_id: str
    app_id: str
    knowledge_base_id: str
    index_name: str
    index_version: str
    document_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class VectorDocumentLookupResult(BaseModel):
    trace_id: str
    provider: str
    collection_name: str
    document_id: str
    exists: bool
    chunk_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int
