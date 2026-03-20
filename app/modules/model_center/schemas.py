from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ModelCatalogEntry(BaseModel):
    logical_model: str
    display_name: str | None = None
    provider: str
    channel: Literal["litellm_proxy", "direct", "internal_proxy"]
    gateway_model_name: str | None = None
    direct_model_name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    task_type: str = "chat"
    capability_tags: list[str] = Field(default_factory=list)
    tenant_scope: list[str] = Field(default_factory=list)
    app_scope: list[str] = Field(default_factory=list)
    enabled: bool = True
    is_default: bool = False
    timeout_ms: int | None = None
    retry_limit: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelRoutePolicy(BaseModel):
    logical_model: str
    tenant_id: str | None = None
    app_id: str | None = None
    scene: str | None = None
    task_type: str | None = None
    required_capability_tags: list[str] = Field(default_factory=list)
    priority: int = 100
    enabled: bool = True


class ModelFallbackPolicy(BaseModel):
    source_logical_model: str
    channel_fallback_target: str | None = None
    max_fallback_count: int = 1
    enabled: bool = True
