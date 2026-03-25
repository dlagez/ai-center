from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


RetrievalStrategy = Literal["vector_search", "hybrid_search"]


class RetrievalRequest(BaseModel):
    tenant_id: str
    app_id: str
    knowledge_base_id: str
    index_name: str = "main"
    index_version: str = "v1"
    scene: str = "knowledge_retrieval"
    query: str
    top_k: int | None = None
    score_threshold: float | None = None
    document_ids: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    include_text: bool = True
    include_metadata: bool = True
    include_positions: bool = True
    query_logical_model: str | None = None
    timeout_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalHit(BaseModel):
    chunk_id: str
    document_id: str
    score: float
    text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_position: dict[str, Any] = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    trace_id: str
    query: str
    total_hits: int
    hits: list[RetrievalHit] = Field(default_factory=list)
    latency_ms: int
    retrieval_strategy: RetrievalStrategy
    debug_info: dict[str, Any] = Field(default_factory=dict)
