from __future__ import annotations

from app.runtime.embedding.schemas import (
    EmbeddingBatchResult,
    EmbeddingFallbackHop,
    ProviderEmbeddingResponse,
)


class EmbeddingResponseNormalizer:
    def normalize(
        self,
        *,
        trace_id: str,
        logical_model: str,
        final_channel: str,
        response: ProviderEmbeddingResponse,
        latency_ms: int,
        fallback_hops: list[EmbeddingFallbackHop],
    ) -> EmbeddingBatchResult:
        return EmbeddingBatchResult(
            trace_id=trace_id,
            logical_model=logical_model,
            final_channel=final_channel,
            final_provider=response.provider,
            final_model=response.model,
            dimension=response.dimension,
            items=response.items,
            usage=response.usage,
            latency_ms=latency_ms,
            fallback_hops=fallback_hops,
            raw_response=response.raw_response,
        )
