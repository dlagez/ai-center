from __future__ import annotations

from app.runtime.retrieval.schemas import (
    RetrievalHit,
    RetrievalRequest,
    RetrievalResult,
    RetrievalStrategy,
)


class RetrievalResultNormalizer:
    def normalize(
        self,
        *,
        trace_id: str,
        request: RetrievalRequest,
        hits: list[RetrievalHit],
        latency_ms: int,
        retrieval_strategy: RetrievalStrategy,
        debug_info: dict[str, object],
    ) -> RetrievalResult:
        return RetrievalResult(
            trace_id=trace_id,
            query=request.query,
            total_hits=len(hits),
            hits=hits,
            latency_ms=latency_ms,
            retrieval_strategy=retrieval_strategy,
            debug_info=debug_info,
        )
