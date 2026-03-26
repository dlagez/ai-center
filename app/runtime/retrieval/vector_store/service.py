from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any

from app.core.config import VectorStoreSettings
from app.core.exceptions import (
    VectorStoreConfigurationError,
    VectorStoreDimensionMismatchError,
    VectorStoreError,
    VectorStoreUnknownError,
    VectorStoreValidationError,
)
from app.integrations.vector_stores.base import BaseVectorStoreAdapter
from app.integrations.vector_stores.local_file_adapter import LocalFileVectorStoreAdapter
from app.integrations.vector_stores.qdrant_adapter import QdrantVectorStoreAdapter
from app.observability.metrics.vector_store_call_recorder import (
    InMemoryVectorStoreCallRecorder,
)
from app.observability.tracing import (
    LangSmithTracer,
    get_default_langsmith_tracer,
    summarize_hits,
)
from app.runtime.retrieval.vector_store.schemas import (
    EnsureCollectionRequest,
    EnsureCollectionResult,
    VectorDeleteRequest,
    VectorDeleteResult,
    VectorDocumentLookupRequest,
    VectorDocumentLookupResult,
    VectorQueryRequest,
    VectorQueryResult,
    VectorRecord,
    VectorStoreCapabilities,
    VectorUpsertRequest,
    VectorUpsertResult,
)

_DEFAULT_METADATA_SCHEMA = {
    "tenant_id": "string",
    "app_id": "string",
    "knowledge_base_id": "string",
    "index_name": "string",
    "index_version": "string",
    "document_id": "string",
    "chunk_id": "string",
}


class VectorStoreService:
    def __init__(
        self,
        *,
        settings: VectorStoreSettings | None = None,
        adapters: dict[str, BaseVectorStoreAdapter] | None = None,
        recorder: InMemoryVectorStoreCallRecorder | None = None,
        tracer: LangSmithTracer | None = None,
    ) -> None:
        self._settings = settings or VectorStoreSettings.from_env()
        self._adapters = adapters or {
            "qdrant": QdrantVectorStoreAdapter(self._settings),
            "local_file": LocalFileVectorStoreAdapter(self._settings),
        }
        self._recorder = recorder or InMemoryVectorStoreCallRecorder()
        self._tracer = tracer or get_default_langsmith_tracer()

    @property
    def recorder(self) -> InMemoryVectorStoreCallRecorder:
        return self._recorder

    def close(self) -> None:
        closed_adapters: set[int] = set()
        for adapter in self._adapters.values():
            adapter_id = id(adapter)
            if adapter_id in closed_adapters:
                continue
            closed_adapters.add(adapter_id)
            adapter.close()

    def describe_capabilities(self) -> VectorStoreCapabilities:
        return self._get_adapter().describe_capabilities()

    def ensure_collection(
        self,
        request: EnsureCollectionRequest,
    ) -> EnsureCollectionResult:
        trace_id = uuid.uuid4().hex
        collection_name = self.build_collection_name(
            tenant_id=request.tenant_id,
            app_id=request.app_id,
            knowledge_base_id=request.knowledge_base_id,
            index_name=request.index_name,
            index_version=request.index_version,
        )
        normalized_request = request.model_copy(
            update={
                "metric_type": request.metric_type
                or self._settings.vector_store_default_metric,
                "metadata_schema": {
                    **_DEFAULT_METADATA_SCHEMA,
                    **dict(request.metadata_schema),
                },
            }
        )
        adapter = self._get_adapter()
        with self._tracer.trace(
            name="vector_store.ensure_collection",
            run_type="tool",
            inputs={
                "tenant_id": normalized_request.tenant_id,
                "app_id": normalized_request.app_id,
                "knowledge_base_id": normalized_request.knowledge_base_id,
                "index_name": normalized_request.index_name,
                "index_version": normalized_request.index_version,
                "dimension": normalized_request.dimension,
                "metric_type": normalized_request.metric_type,
                "metadata_schema": dict(normalized_request.metadata_schema),
            },
            metadata={
                "tenant_id": normalized_request.tenant_id,
                "app_id": normalized_request.app_id,
                "knowledge_base_id": normalized_request.knowledge_base_id,
                "index_name": normalized_request.index_name,
                "index_version": normalized_request.index_version,
                "collection_name": collection_name,
                "provider": adapter.provider_name,
                "app_trace_id": trace_id,
            },
        ) as trace_run:
            try:
                result = adapter.ensure_collection(
                    collection_name=collection_name,
                    request=normalized_request,
                    trace_id=trace_id,
                )
                self._recorder.record_ensure_success(normalized_request, result)
                trace_run.end(
                    outputs={
                        "trace_id": result.trace_id,
                        "provider": result.provider,
                        "collection_name": result.collection_name,
                        "dimension": result.dimension,
                        "metric_type": result.metric_type,
                        "existed": result.existed,
                        "created": result.created,
                        "latency_ms": result.latency_ms,
                    }
                )
                return result
            except Exception as exc:
                error = self._to_vector_store_error(exc)
                trace_run.metadata.update({"error_code": error.code})
                self._recorder.record_failure(
                    operation="ensure_collection",
                    request=normalized_request,
                    trace_id=trace_id,
                    provider=adapter.provider_name,
                    collection_name=collection_name,
                    error=error,
                )
                raise error

    def upsert_records(self, request: VectorUpsertRequest) -> VectorUpsertResult:
        if not request.records:
            raise VectorStoreValidationError(
                "Vector upsert request records must not be empty."
            )

        dimension = self._validate_record_dimensions(request.records)
        self.ensure_collection(
            EnsureCollectionRequest(
                tenant_id=request.tenant_id,
                app_id=request.app_id,
                knowledge_base_id=request.knowledge_base_id,
                index_name=request.index_name,
                index_version=request.index_version,
                dimension=dimension,
            )
        )

        trace_id = uuid.uuid4().hex
        collection_name = self.build_collection_name(
            tenant_id=request.tenant_id,
            app_id=request.app_id,
            knowledge_base_id=request.knowledge_base_id,
            index_name=request.index_name,
            index_version=request.index_version,
        )
        normalized_request = request.model_copy(
            update={"records": self._enrich_records(request)}
        )
        adapter = self._get_adapter()
        with self._tracer.trace(
            name="vector_store.upsert_records",
            run_type="tool",
            inputs=self._build_upsert_trace_inputs(normalized_request),
            metadata={
                "tenant_id": normalized_request.tenant_id,
                "app_id": normalized_request.app_id,
                "knowledge_base_id": normalized_request.knowledge_base_id,
                "index_name": normalized_request.index_name,
                "index_version": normalized_request.index_version,
                "collection_name": collection_name,
                "provider": adapter.provider_name,
                "app_trace_id": trace_id,
                **normalized_request.metadata,
            },
        ) as trace_run:
            try:
                result = adapter.upsert(
                    collection_name=collection_name,
                    request=normalized_request,
                    trace_id=trace_id,
                )
                self._recorder.record_upsert_success(normalized_request, result)
                trace_run.end(
                    outputs={
                        "trace_id": result.trace_id,
                        "provider": result.provider,
                        "collection_name": result.collection_name,
                        "index_version": result.index_version,
                        "total_count": result.total_count,
                        "success_count": result.success_count,
                        "failed_count": result.failed_count,
                        "latency_ms": result.latency_ms,
                        "errors": list(result.errors),
                    }
                )
                return result
            except Exception as exc:
                error = self._to_vector_store_error(exc)
                trace_run.metadata.update({"error_code": error.code})
                self._recorder.record_failure(
                    operation="upsert_records",
                    request=normalized_request,
                    trace_id=trace_id,
                    provider=adapter.provider_name,
                    collection_name=collection_name,
                    error=error,
                )
                raise error

    def query_vectors(self, request: VectorQueryRequest) -> VectorQueryResult:
        if not request.query_vector:
            raise VectorStoreValidationError("Query vector must not be empty.")
        if request.top_k <= 0:
            raise VectorStoreValidationError("Query top_k must be greater than zero.")

        trace_id = uuid.uuid4().hex
        collection_name = self.build_collection_name(
            tenant_id=request.tenant_id,
            app_id=request.app_id,
            knowledge_base_id=request.knowledge_base_id,
            index_name=request.index_name,
            index_version=request.index_version,
        )
        adapter = self._get_adapter()
        with self._tracer.trace(
            name="vector_store.query_vectors",
            run_type="tool",
            inputs={
                "tenant_id": request.tenant_id,
                "app_id": request.app_id,
                "knowledge_base_id": request.knowledge_base_id,
                "index_name": request.index_name,
                "index_version": request.index_version,
                "query_vector_dimension": len(request.query_vector),
                "top_k": request.top_k,
                "filters": dict(request.filters),
            },
            metadata={
                "tenant_id": request.tenant_id,
                "app_id": request.app_id,
                "knowledge_base_id": request.knowledge_base_id,
                "index_name": request.index_name,
                "index_version": request.index_version,
                "collection_name": collection_name,
                "provider": adapter.provider_name,
                "app_trace_id": trace_id,
                **request.metadata,
            },
        ) as trace_run:
            try:
                result = adapter.query(
                    collection_name=collection_name,
                    request=request,
                    trace_id=trace_id,
                )
                self._recorder.record_query_success(request, result)
                trace_run.end(
                    outputs={
                        "trace_id": result.trace_id,
                        "provider": result.provider,
                        "collection_name": result.collection_name,
                        "total_hits": result.total_hits,
                        "latency_ms": result.latency_ms,
                        "hits": summarize_hits(
                            result.hits,
                            capture_text=self._tracer.capture_retrieved_text(),
                            max_text_chars=self._tracer.settings.app_langsmith_max_text_chars,
                            redact_pii=self._tracer.settings.app_langsmith_redact_pii,
                        ),
                    }
                )
                return result
            except Exception as exc:
                error = self._to_vector_store_error(exc)
                trace_run.metadata.update({"error_code": error.code})
                self._recorder.record_failure(
                    operation="query_vectors",
                    request=request,
                    trace_id=trace_id,
                    provider=adapter.provider_name,
                    collection_name=collection_name,
                    error=error,
                )
                raise error

    def delete_records(self, request: VectorDeleteRequest) -> VectorDeleteResult:
        if not request.chunk_ids and not request.document_ids:
            raise VectorStoreValidationError(
                "Delete request must include chunk_ids or document_ids."
            )

        trace_id = uuid.uuid4().hex
        collection_name = self.build_collection_name(
            tenant_id=request.tenant_id,
            app_id=request.app_id,
            knowledge_base_id=request.knowledge_base_id,
            index_name=request.index_name,
            index_version=request.index_version,
        )
        adapter = self._get_adapter()
        with self._tracer.trace(
            name="vector_store.delete_records",
            run_type="tool",
            inputs={
                "tenant_id": request.tenant_id,
                "app_id": request.app_id,
                "knowledge_base_id": request.knowledge_base_id,
                "index_name": request.index_name,
                "index_version": request.index_version,
                "chunk_ids": list(request.chunk_ids),
                "document_ids": list(request.document_ids),
            },
            metadata={
                "tenant_id": request.tenant_id,
                "app_id": request.app_id,
                "knowledge_base_id": request.knowledge_base_id,
                "index_name": request.index_name,
                "index_version": request.index_version,
                "collection_name": collection_name,
                "provider": adapter.provider_name,
                "app_trace_id": trace_id,
                **request.metadata,
            },
        ) as trace_run:
            try:
                result = adapter.delete(
                    collection_name=collection_name,
                    request=request,
                    trace_id=trace_id,
                )
                self._recorder.record_delete_success(request, result)
                trace_run.end(
                    outputs={
                        "trace_id": result.trace_id,
                        "provider": result.provider,
                        "collection_name": result.collection_name,
                        "requested_count": result.requested_count,
                        "deleted_count": result.deleted_count,
                        "latency_ms": result.latency_ms,
                    }
                )
                return result
            except Exception as exc:
                error = self._to_vector_store_error(exc)
                trace_run.metadata.update({"error_code": error.code})
                self._recorder.record_failure(
                    operation="delete_records",
                    request=request,
                    trace_id=trace_id,
                    provider=adapter.provider_name,
                    collection_name=collection_name,
                    error=error,
                )
                raise error

    def lookup_document(
        self,
        request: VectorDocumentLookupRequest,
    ) -> VectorDocumentLookupResult:
        trace_id = uuid.uuid4().hex
        collection_name = self.build_collection_name(
            tenant_id=request.tenant_id,
            app_id=request.app_id,
            knowledge_base_id=request.knowledge_base_id,
            index_name=request.index_name,
            index_version=request.index_version,
        )
        adapter = self._get_adapter()
        with self._tracer.trace(
            name="vector_store.lookup_document",
            run_type="tool",
            inputs={
                "tenant_id": request.tenant_id,
                "app_id": request.app_id,
                "knowledge_base_id": request.knowledge_base_id,
                "index_name": request.index_name,
                "index_version": request.index_version,
                "document_id": request.document_id,
            },
            metadata={
                "tenant_id": request.tenant_id,
                "app_id": request.app_id,
                "knowledge_base_id": request.knowledge_base_id,
                "index_name": request.index_name,
                "index_version": request.index_version,
                "document_id": request.document_id,
                "collection_name": collection_name,
                "provider": adapter.provider_name,
                "app_trace_id": trace_id,
                **request.metadata,
            },
        ) as trace_run:
            try:
                result = adapter.lookup_document(
                    collection_name=collection_name,
                    request=request,
                    trace_id=trace_id,
                )
                trace_run.end(
                    outputs={
                        "trace_id": result.trace_id,
                        "provider": result.provider,
                        "collection_name": result.collection_name,
                        "document_id": result.document_id,
                        "exists": result.exists,
                        "chunk_count": result.chunk_count,
                        "latency_ms": result.latency_ms,
                        "metadata": dict(result.metadata),
                    }
                )
                return result
            except Exception as exc:
                error = self._to_vector_store_error(exc)
                trace_run.metadata.update({"error_code": error.code})
                raise error

    def build_collection_name(
        self,
        *,
        tenant_id: str,
        app_id: str,
        knowledge_base_id: str,
        index_name: str,
        index_version: str,
    ) -> str:
        prefix = self._sanitize_prefix(self._settings.vector_store_collection_prefix)
        segments = [
            self._sanitize_segment(tenant_id),
            self._sanitize_segment(app_id),
            self._sanitize_segment(knowledge_base_id),
            self._sanitize_segment(index_name),
            self._sanitize_segment(index_version),
        ]
        base_name = f"{prefix}{'__'.join(segments)}" if prefix else "__".join(segments)
        if len(base_name) <= 120:
            return base_name
        digest = hashlib.sha1(base_name.encode("utf-8")).hexdigest()[:12]
        return f"{base_name[:107]}__{digest}"

    def _get_adapter(self) -> BaseVectorStoreAdapter:
        adapter = self._adapters.get(self._settings.vector_store_provider)
        if adapter is None:
            raise VectorStoreConfigurationError(
                f"No vector store adapter is registered for provider "
                f"'{self._settings.vector_store_provider}'."
            )
        return adapter

    def _enrich_records(self, request: VectorUpsertRequest) -> list[VectorRecord]:
        enriched_records: list[VectorRecord] = []
        for record in request.records:
            enriched_records.append(
                record.model_copy(
                    update={
                        "metadata": {
                            **record.metadata,
                            "tenant_id": request.tenant_id,
                            "app_id": request.app_id,
                            "knowledge_base_id": request.knowledge_base_id,
                            "index_name": request.index_name,
                            "index_version": request.index_version,
                            "document_id": record.document_id,
                            "chunk_id": record.chunk_id,
                        }
                    }
                )
            )
        return enriched_records

    @staticmethod
    def _validate_record_dimensions(records: list[VectorRecord]) -> int:
        if not records:
            raise VectorStoreValidationError("Vector records must not be empty.")
        dimensions = {len(record.vector) for record in records}
        if 0 in dimensions:
            raise VectorStoreValidationError("Vector must not be empty.")
        if len(dimensions) != 1:
            raise VectorStoreDimensionMismatchError(
                "All vectors in a batch must have the same dimension."
            )
        return dimensions.pop()

    @staticmethod
    def _sanitize_segment(value: str) -> str:
        sanitized = re.sub(r"[^0-9A-Za-z_-]+", "_", value.strip())
        sanitized = sanitized.strip("_")
        return sanitized or "na"

    @staticmethod
    def _sanitize_prefix(value: str) -> str:
        sanitized = re.sub(r"[^0-9A-Za-z_-]+", "_", value.strip())
        return sanitized

    @staticmethod
    def _to_vector_store_error(exc: Exception) -> VectorStoreError:
        if isinstance(exc, VectorStoreError):
            return exc
        return VectorStoreUnknownError(str(exc))

    def _build_upsert_trace_inputs(
        self,
        request: VectorUpsertRequest,
    ) -> dict[str, Any]:
        record_previews: list[dict[str, Any]] = []
        for record in request.records[:5]:
            preview: dict[str, Any] = {
                "chunk_id": record.chunk_id,
                "document_id": record.document_id,
                "vector_dimension": len(record.vector),
            }
            if self._tracer.capture_retrieved_text():
                preview["text"] = record.text
            if record.metadata:
                preview["metadata"] = dict(record.metadata)
            record_previews.append(preview)

        return {
            "tenant_id": request.tenant_id,
            "app_id": request.app_id,
            "knowledge_base_id": request.knowledge_base_id,
            "index_name": request.index_name,
            "index_version": request.index_version,
            "record_count": len(request.records),
            "records": record_previews,
        }


def build_default_vector_store_service(
    settings: VectorStoreSettings | None = None,
    adapters: dict[str, BaseVectorStoreAdapter] | None = None,
    recorder: InMemoryVectorStoreCallRecorder | None = None,
    tracer: LangSmithTracer | None = None,
) -> VectorStoreService:
    return VectorStoreService(
        settings=settings,
        adapters=adapters,
        recorder=recorder,
        tracer=tracer,
    )
