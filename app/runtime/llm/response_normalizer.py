from __future__ import annotations

from app.runtime.llm.schemas import FallbackHop, LLMInvokeResult, ProviderInvokeResponse


class ResponseNormalizer:
    def normalize(
        self,
        *,
        trace_id: str,
        logical_model: str,
        final_channel: str,
        response: ProviderInvokeResponse,
        latency_ms: int,
        fallback_hops: list[FallbackHop],
    ) -> LLMInvokeResult:
        return LLMInvokeResult(
            trace_id=trace_id,
            logical_model=logical_model,
            final_channel=final_channel,
            final_provider=response.provider,
            final_model=response.model,
            content=response.content,
            tool_calls=response.tool_calls,
            finish_reason=response.finish_reason,
            usage=response.usage,
            latency_ms=latency_ms,
            fallback_hops=fallback_hops,
            raw_response=response.raw_response,
        )
