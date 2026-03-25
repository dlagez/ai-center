from __future__ import annotations

import time
import uuid
from typing import Any

from app.core.config import (
    EmbeddingSettings,
    GatewaySettings,
    RetrievalSettings,
    VectorStoreSettings,
)
from app.core.exceptions import (
    RetrievalQueryEmptyError,
    RetrievalResultError,
    RetrievalValidationError,
)
from app.observability.metrics.retrieval_call_recorder import (
    InMemoryRetrievalCallRecorder,
)
from app.runtime.embedding.gateway_service import (
    EmbeddingGatewayService,
    build_embedding_gateway_service,
)
from app.runtime.embedding.schemas import EmbeddingBatchRequest, EmbeddingInputItem
from app.runtime.retrieval.error_mapper import RetrievalErrorMapper
from app.runtime.retrieval.filter_builder import RetrievalFilterBuilder
from app.runtime.retrieval.result_normalizer import RetrievalResultNormalizer
from app.runtime.retrieval.schemas import (
    RetrievalHit,
    RetrievalRequest,
    RetrievalResult,
)
from app.runtime.retrieval.vector_store import VectorQueryRequest, VectorStoreService
from app.runtime.retrieval.vector_store.service import build_default_vector_store_service


class RetrieverService:
    def __init__(
        self,
        *,
        settings: RetrievalSettings | None = None,
        embedding_service: EmbeddingGatewayService | None = None,
        vector_store_service: VectorStoreService | None = None,
        recorder: InMemoryRetrievalCallRecorder | None = None,
        filter_builder: RetrievalFilterBuilder | None = None,
        error_mapper: RetrievalErrorMapper | None = None,
        normalizer: RetrievalResultNormalizer | None = None,
    ) -> None:
        self._settings = settings or RetrievalSettings.from_env()
        self._embedding_service = embedding_service or build_embedding_gateway_service()
        self._vector_store_service = (
            vector_store_service or build_default_vector_store_service()
        )
        self._recorder = recorder or InMemoryRetrievalCallRecorder()
        self._filter_builder = filter_builder or RetrievalFilterBuilder()
        self._error_mapper = error_mapper or RetrievalErrorMapper()
        self._normalizer = normalizer or RetrievalResultNormalizer()

    @property
    def recorder(self) -> InMemoryRetrievalCallRecorder:
        return self._recorder

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        trace_id = uuid.uuid4().hex
        retrieval_strategy = "vector_search"
        normalized_request = self._normalize_request(request)
        start_time = time.perf_counter()

        try:
            filters = self._filter_builder.build(normalized_request)
            embedding_result = self._embedding_service.embed(
                self._build_embedding_request(normalized_request, trace_id=trace_id)
            )
            query_vector = self._extract_query_vector(embedding_result.items)
            vector_result = self._vector_store_service.query_vectors(
                self._build_vector_query_request(
                    normalized_request,
                    filters=filters,
                    query_vector=query_vector,
                    trace_id=trace_id,
                )
            )
            hits, post_process_debug = self._post_process_hits(
                normalized_request,
                raw_hits=vector_result.hits,
            )
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            result = self._normalizer.normalize(
                trace_id=trace_id,
                request=normalized_request,
                hits=hits,
                latency_ms=latency_ms,
                retrieval_strategy=retrieval_strategy,
                debug_info={
                    "embedding_trace_id": embedding_result.trace_id,
                    "vector_store_trace_id": vector_result.trace_id,
                    "query_vector_dimension": len(query_vector),
                    "candidate_count": len(vector_result.hits),
                    "filter_keys": sorted(filters.keys()),
                    "store_provider": vector_result.provider,
                    **post_process_debug,
                },
            )
            self._recorder.record_success(normalized_request, result)
            return result
        except Exception as exc:
            error = self._error_mapper.to_retrieval_error(exc)
            self._recorder.record_failure(
                request=normalized_request,
                trace_id=trace_id,
                retrieval_strategy=retrieval_strategy,
                error=error,
            )
            raise error

    def _normalize_request(self, request: RetrievalRequest) -> RetrievalRequest:
        query = (request.query or "").strip()
        if not query:
            raise RetrievalQueryEmptyError("Retrieval query must not be empty.")

        requested_top_k = (
            request.top_k
            if request.top_k is not None
            else self._settings.retrieval_default_top_k
        )
        if requested_top_k <= 0:
            raise RetrievalValidationError("Retrieval top_k must be greater than zero.")

        top_k = min(requested_top_k, self._settings.retrieval_max_top_k)
        score_threshold = (
            request.score_threshold
            if request.score_threshold is not None
            else self._settings.retrieval_default_score_threshold
        )
        return request.model_copy(
            update={
                "query": query,
                "top_k": top_k,
                "score_threshold": score_threshold,
            }
        )

    def _build_embedding_request(
        self,
        request: RetrievalRequest,
        *,
        trace_id: str,
    ) -> EmbeddingBatchRequest:
        return EmbeddingBatchRequest(
            tenant_id=request.tenant_id,
            app_id=request.app_id,
            scene=request.scene,
            logical_model=(
                request.query_logical_model
                or self._settings.retrieval_query_logical_model
            ),
            items=[
                EmbeddingInputItem(
                    chunk_id=f"query:{trace_id}",
                    text=request.query,
                    metadata={"query": request.query},
                )
            ],
            timeout_ms=request.timeout_ms or self._settings.retrieval_timeout_ms,
            metadata={
                **request.metadata,
                "retrieval_trace_id": trace_id,
                "retrieval_strategy": "vector_search",
            },
        )

    def _build_vector_query_request(
        self,
        request: RetrievalRequest,
        *,
        filters: dict[str, Any],
        query_vector: list[float],
        trace_id: str,
    ) -> VectorQueryRequest:
        return VectorQueryRequest(
            tenant_id=request.tenant_id,
            app_id=request.app_id,
            knowledge_base_id=request.knowledge_base_id,
            index_name=request.index_name,
            index_version=request.index_version,
            query_vector=query_vector,
            top_k=request.top_k,
            filters=filters,
            metadata={
                **request.metadata,
                "retrieval_trace_id": trace_id,
            },
        )

    @staticmethod
    def _extract_query_vector(items: list[Any]) -> list[float]:
        if not items:
            raise RetrievalResultError("Retriever query embedding returned no items.")
        first_item = items[0]
        vector = getattr(first_item, "vector", None)
        if not vector:
            raise RetrievalResultError("Retriever query embedding returned no vector.")
        return list(vector)

    def _post_process_hits(
        self,
        request: RetrievalRequest,
        *,
        raw_hits: list[Any],
    ) -> tuple[list[RetrievalHit], dict[str, int]]:
        hits: list[RetrievalHit] = []
        seen_chunk_ids: set[str] = set()
        below_threshold_count = 0
        deduped_count = 0

        for raw_hit in raw_hits:
            if (
                request.score_threshold is not None
                and raw_hit.score < request.score_threshold
            ):
                below_threshold_count += 1
                continue
            if raw_hit.chunk_id in seen_chunk_ids:
                deduped_count += 1
                continue
            seen_chunk_ids.add(raw_hit.chunk_id)

            metadata = self._normalize_hit_metadata(
                raw_hit.metadata,
                include_metadata=request.include_metadata,
                include_positions=request.include_positions,
            )
            hits.append(
                RetrievalHit(
                    chunk_id=raw_hit.chunk_id,
                    document_id=raw_hit.document_id,
                    score=raw_hit.score,
                    text=raw_hit.text if request.include_text else None,
                    metadata=metadata,
                    source_position=(
                        self._extract_source_position(raw_hit.metadata)
                        if request.include_positions
                        else {}
                    ),
                )
            )

        return hits, {
            "below_threshold_count": below_threshold_count,
            "deduped_count": deduped_count,
        }

    @staticmethod
    def _normalize_hit_metadata(
        metadata: dict[str, Any],
        *,
        include_metadata: bool,
        include_positions: bool,
    ) -> dict[str, Any]:
        if not include_metadata:
            return {}

        normalized_metadata = dict(metadata)
        if include_positions:
            return normalized_metadata

        for key in (
            "source_position",
            "source_positions",
            "page_no",
            "row_index",
            "start_offset",
            "end_offset",
            "paragraph_index",
            "sheet_name",
            "block_id",
        ):
            normalized_metadata.pop(key, None)
        return normalized_metadata

    @staticmethod
    def _extract_source_position(metadata: dict[str, Any]) -> dict[str, Any]:
        source_position = metadata.get("source_position")
        if isinstance(source_position, dict):
            return dict(source_position)

        source_positions = metadata.get("source_positions")
        if source_positions is not None:
            return {"positions": source_positions}

        extracted: dict[str, Any] = {}
        for key in (
            "page_no",
            "row_index",
            "start_offset",
            "end_offset",
            "paragraph_index",
            "sheet_name",
            "block_id",
        ):
            value = metadata.get(key)
            if value is not None:
                extracted[key] = value
        return extracted


def build_default_retriever_service(
    *,
    retrieval_settings: RetrievalSettings | None = None,
    embedding_settings: EmbeddingSettings | None = None,
    gateway_settings: GatewaySettings | None = None,
    vector_store_settings: VectorStoreSettings | None = None,
    embedding_service: EmbeddingGatewayService | None = None,
    vector_store_service: VectorStoreService | None = None,
    recorder: InMemoryRetrievalCallRecorder | None = None,
) -> RetrieverService:
    return RetrieverService(
        settings=retrieval_settings,
        embedding_service=embedding_service
        or build_embedding_gateway_service(
            embedding_settings=embedding_settings,
            gateway_settings=gateway_settings,
        ),
        vector_store_service=vector_store_service
        or build_default_vector_store_service(settings=vector_store_settings),
        recorder=recorder,
    )
