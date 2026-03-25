from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.exceptions import EmbeddingError
from app.runtime.embedding.schemas import (
    EmbeddingBatchRequest,
    EmbeddingBatchResult,
    ResolvedEmbeddingPlan,
)


class EmbeddingCallRecord(BaseModel):
    trace_id: str
    tenant_id: str
    app_id: str
    scene: str
    logical_model: str
    final_channel: str
    final_provider: str | None = None
    final_model: str | None = None
    latency_ms: int | None = None
    batch_size: int = 0
    dimension: int = 0
    prompt_tokens: int = 0
    total_tokens: int = 0
    status: str
    error_code: str | None = None
    error_message: str | None = None
    fallback_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class InMemoryEmbeddingCallRecorder:
    def __init__(self) -> None:
        self._records: list[EmbeddingCallRecord] = []

    @property
    def records(self) -> list[EmbeddingCallRecord]:
        return list(self._records)

    def record_success(
        self,
        request: EmbeddingBatchRequest,
        result: EmbeddingBatchResult,
    ) -> None:
        self._records.append(
            EmbeddingCallRecord(
                trace_id=result.trace_id,
                tenant_id=request.tenant_id,
                app_id=request.app_id,
                scene=request.scene,
                logical_model=result.logical_model,
                final_channel=result.final_channel,
                final_provider=result.final_provider,
                final_model=result.final_model,
                latency_ms=result.latency_ms,
                batch_size=len(request.items),
                dimension=result.dimension,
                prompt_tokens=result.usage.prompt_tokens,
                total_tokens=result.usage.total_tokens,
                status="success",
                fallback_count=len(result.fallback_hops),
                metadata=dict(request.metadata),
            )
        )

    def record_failure(
        self,
        *,
        request: EmbeddingBatchRequest,
        trace_id: str,
        plan: ResolvedEmbeddingPlan,
        error: EmbeddingError,
        fallback_count: int,
    ) -> None:
        self._records.append(
            EmbeddingCallRecord(
                trace_id=trace_id,
                tenant_id=request.tenant_id,
                app_id=request.app_id,
                scene=request.scene,
                logical_model=plan.logical_model,
                final_channel=plan.channel,
                final_provider=plan.provider,
                final_model=plan.target_model_name,
                batch_size=len(request.items),
                status="error",
                error_code=error.code,
                error_message=str(error),
                fallback_count=fallback_count,
                metadata=dict(request.metadata),
            )
        )
