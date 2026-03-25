from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from app.core.exceptions import RetrievalError

if TYPE_CHECKING:
    from app.runtime.retrieval.schemas import RetrievalRequest, RetrievalResult


class RetrievalCallRecord(BaseModel):
    trace_id: str
    tenant_id: str
    app_id: str
    knowledge_base_id: str
    index_name: str
    index_version: str
    query: str
    retrieval_strategy: str
    top_k: int
    score_threshold: float | None = None
    filter_keys: list[str] = Field(default_factory=list)
    candidate_count: int = 0
    total_hits: int = 0
    latency_ms: int | None = None
    status: str
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InMemoryRetrievalCallRecorder:
    def __init__(self) -> None:
        self._records: list[RetrievalCallRecord] = []

    @property
    def records(self) -> list[RetrievalCallRecord]:
        return list(self._records)

    def record_success(
        self,
        request: RetrievalRequest,
        result: RetrievalResult,
    ) -> None:
        self._records.append(
            RetrievalCallRecord(
                trace_id=result.trace_id,
                tenant_id=request.tenant_id,
                app_id=request.app_id,
                knowledge_base_id=request.knowledge_base_id,
                index_name=request.index_name,
                index_version=request.index_version,
                query=result.query,
                retrieval_strategy=result.retrieval_strategy,
                top_k=request.top_k,
                score_threshold=request.score_threshold,
                filter_keys=sorted(result.debug_info.get("filter_keys", [])),
                candidate_count=int(result.debug_info.get("candidate_count", 0)),
                total_hits=result.total_hits,
                latency_ms=result.latency_ms,
                status="success",
                metadata=dict(request.metadata),
            )
        )

    def record_failure(
        self,
        *,
        request: RetrievalRequest,
        trace_id: str,
        retrieval_strategy: str,
        error: RetrievalError,
    ) -> None:
        self._records.append(
            RetrievalCallRecord(
                trace_id=trace_id,
                tenant_id=request.tenant_id,
                app_id=request.app_id,
                knowledge_base_id=request.knowledge_base_id,
                index_name=request.index_name,
                index_version=request.index_version,
                query=request.query,
                retrieval_strategy=retrieval_strategy,
                top_k=request.top_k,
                score_threshold=request.score_threshold,
                filter_keys=sorted(request.filters.keys()),
                status="error",
                error_code=error.code,
                error_message=str(error),
                metadata=dict(request.metadata),
            )
        )
