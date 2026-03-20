from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMInvokeRequest(BaseModel):
    tenant_id: str
    app_id: str
    user_id: str | None = None
    scene: str
    task_type: str
    logical_model: str | None = None
    capability_tags: list[str] = Field(default_factory=list)
    stream: bool = False
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] | None = None
    response_format: dict[str, Any] | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    timeout_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FallbackHop(BaseModel):
    source_logical_model: str
    target_logical_model: str
    target_channel: str
    reason: str


class ProviderInvokeResponse(BaseModel):
    provider: str
    model: str
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    finish_reason: str | None = None
    usage: UsageInfo = Field(default_factory=UsageInfo)
    raw_response: dict[str, Any] | None = None


class ResolvedInvocationPlan(BaseModel):
    logical_model: str
    channel: Literal["litellm_proxy", "direct", "internal_proxy"]
    provider: str
    target_model_name: str
    base_url: str | None = None
    api_key: str | None = None
    timeout_ms: int
    task_type: str
    capability_tags: list[str] = Field(default_factory=list)
    fallback_target_logical_model: str | None = None
    max_fallback_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMInvokeResult(BaseModel):
    trace_id: str
    logical_model: str
    final_channel: str
    final_provider: str
    final_model: str
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    finish_reason: str | None = None
    usage: UsageInfo = Field(default_factory=UsageInfo)
    cost: float | None = None
    latency_ms: int
    fallback_hops: list[FallbackHop] = Field(default_factory=list)
    raw_response: dict[str, Any] | None = None


class LLMStreamChunk(BaseModel):
    trace_id: str
    logical_model: str
    final_channel: str
    final_provider: str
    final_model: str
    delta: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    finish_reason: str | None = None
    usage: UsageInfo | None = None
    raw_response: dict[str, Any] | None = None
