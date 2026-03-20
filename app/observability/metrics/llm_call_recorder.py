from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.exceptions import ModelGatewayError
from app.runtime.llm.schemas import LLMInvokeRequest, LLMInvokeResult, ResolvedInvocationPlan


class LLMCallRecord(BaseModel):
    trace_id: str
    tenant_id: str
    app_id: str
    scene: str
    logical_model: str
    final_channel: str
    final_provider: str | None = None
    final_model: str | None = None
    latency_ms: int | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float | None = None
    status: str
    error_code: str | None = None
    error_message: str | None = None
    fallback_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class InMemoryLLMCallRecorder:
    def __init__(self) -> None:
        self._records: list[LLMCallRecord] = []

    @property
    def records(self) -> list[LLMCallRecord]:
        return list(self._records)

    def record_success(self, request: LLMInvokeRequest, result: LLMInvokeResult) -> None:
        self._records.append(
            LLMCallRecord(
                trace_id=result.trace_id,
                tenant_id=request.tenant_id,
                app_id=request.app_id,
                scene=request.scene,
                logical_model=result.logical_model,
                final_channel=result.final_channel,
                final_provider=result.final_provider,
                final_model=result.final_model,
                latency_ms=result.latency_ms,
                prompt_tokens=result.usage.prompt_tokens,
                completion_tokens=result.usage.completion_tokens,
                total_tokens=result.usage.total_tokens,
                cost=result.cost,
                status="success",
                fallback_count=len(result.fallback_hops),
                metadata=dict(request.metadata),
            )
        )

    def record_stream_success(
        self,
        *,
        request: LLMInvokeRequest,
        trace_id: str,
        logical_model: str,
        final_channel: str,
        final_provider: str,
        final_model: str,
        fallback_count: int,
    ) -> None:
        self._records.append(
            LLMCallRecord(
                trace_id=trace_id,
                tenant_id=request.tenant_id,
                app_id=request.app_id,
                scene=request.scene,
                logical_model=logical_model,
                final_channel=final_channel,
                final_provider=final_provider,
                final_model=final_model,
                status="stream_success",
                fallback_count=fallback_count,
                metadata=dict(request.metadata),
            )
        )

    def record_failure(
        self,
        *,
        request: LLMInvokeRequest,
        trace_id: str,
        plan: ResolvedInvocationPlan,
        error: ModelGatewayError,
        fallback_count: int,
    ) -> None:
        self._records.append(
            LLMCallRecord(
                trace_id=trace_id,
                tenant_id=request.tenant_id,
                app_id=request.app_id,
                scene=request.scene,
                logical_model=plan.logical_model,
                final_channel=plan.channel,
                final_provider=plan.provider,
                final_model=plan.target_model_name,
                status="error",
                error_code=error.code,
                error_message=str(error),
                fallback_count=fallback_count,
                metadata=dict(request.metadata),
            )
        )
