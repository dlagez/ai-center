from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class EmbeddingUsageInfo(BaseModel):
    prompt_tokens: int = 0
    total_tokens: int = 0


class EmbeddingInputItem(BaseModel):
    chunk_id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class EmbeddedChunk(BaseModel):
    chunk_id: str
    text: str
    vector: list[float]
    dimension: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class EmbeddingBatchRequest(BaseModel):
    tenant_id: str
    app_id: str
    scene: str
    task_type: str = "embedding"
    logical_model: str | None = None
    capability_tags: list[str] = Field(default_factory=list)
    items: list[EmbeddingInputItem]
    timeout_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderEmbeddingResponse(BaseModel):
    provider: str
    model: str
    dimension: int
    items: list[EmbeddedChunk]
    usage: EmbeddingUsageInfo = Field(default_factory=EmbeddingUsageInfo)
    raw_response: dict[str, Any] | None = None


class EmbeddingFallbackHop(BaseModel):
    source_logical_model: str
    target_logical_model: str
    target_channel: str
    reason: str


class ResolvedEmbeddingPlan(BaseModel):
    logical_model: str
    channel: Literal["litellm_proxy", "direct", "internal_proxy"]
    provider: str
    target_model_name: str
    base_url: str | None = None
    api_key: str | None = None
    timeout_ms: int
    batch_size: int
    task_type: str
    capability_tags: list[str] = Field(default_factory=list)
    fallback_target_logical_model: str | None = None
    max_fallback_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class EmbeddingBatchResult(BaseModel):
    trace_id: str
    logical_model: str
    final_channel: str
    final_provider: str
    final_model: str
    dimension: int
    items: list[EmbeddedChunk]
    usage: EmbeddingUsageInfo = Field(default_factory=EmbeddingUsageInfo)
    latency_ms: int
    fallback_hops: list[EmbeddingFallbackHop] = Field(default_factory=list)
    raw_response: dict[str, Any] | None = None
