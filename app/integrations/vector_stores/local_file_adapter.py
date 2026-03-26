from __future__ import annotations

import json
import math
import threading
import time
from pathlib import Path
from typing import Any

from app.core.config import VectorStoreSettings
from app.core.exceptions import (
    VectorStoreCollectionError,
    VectorStoreDimensionMismatchError,
    VectorStoreQueryError,
    VectorStoreValidationError,
    VectorStoreWriteError,
)
from app.integrations.vector_stores.base import BaseVectorStoreAdapter
from app.runtime.retrieval.vector_store.schemas import (
    EnsureCollectionRequest,
    EnsureCollectionResult,
    MetricType,
    VectorDeleteRequest,
    VectorDeleteResult,
    VectorDocumentLookupRequest,
    VectorDocumentLookupResult,
    VectorHit,
    VectorQueryRequest,
    VectorQueryResult,
    VectorRecord,
    VectorStoreCapabilities,
    VectorUpsertRequest,
    VectorUpsertResult,
)


class LocalFileVectorStoreAdapter(BaseVectorStoreAdapter):
    provider_name = "local_file"

    def __init__(self, settings: VectorStoreSettings) -> None:
        self._settings = settings
        self._base_dir = Path(settings.vector_store_local_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def ensure_collection(
        self,
        *,
        collection_name: str,
        request: EnsureCollectionRequest,
        trace_id: str,
    ) -> EnsureCollectionResult:
        start_time = time.perf_counter()
        metric_type = request.metric_type or self._settings.vector_store_default_metric
        path = self._collection_path(collection_name)
        with self._collection_lock(collection_name):
            if path.exists():
                payload = self._read_collection(path, collection_name=collection_name)
                stored_dimension = int(payload.get("dimension", 0))
                stored_metric = payload.get("metric_type")
                if stored_dimension != request.dimension:
                    raise VectorStoreDimensionMismatchError(
                        f"Collection '{collection_name}' expects dimension "
                        f"{stored_dimension}, got {request.dimension}."
                    )
                if stored_metric != metric_type:
                    raise VectorStoreCollectionError(
                        f"Collection '{collection_name}' expects metric "
                        f"'{stored_metric}', got '{metric_type}'."
                    )
                existed = True
                created = False
            else:
                payload = {
                    "collection_name": collection_name,
                    "dimension": request.dimension,
                    "metric_type": metric_type,
                    "metadata_schema": dict(request.metadata_schema),
                    "records": {},
                }
                self._write_collection(path, payload, collection_name=collection_name)
                existed = False
                created = True

        latency_ms = int((time.perf_counter() - start_time) * 1000)
        return EnsureCollectionResult(
            trace_id=trace_id,
            provider=self.provider_name,
            collection_name=collection_name,
            dimension=request.dimension,
            metric_type=metric_type,
            existed=existed,
            created=created,
            latency_ms=latency_ms,
        )

    def upsert(
        self,
        *,
        collection_name: str,
        request: VectorUpsertRequest,
        trace_id: str,
    ) -> VectorUpsertResult:
        start_time = time.perf_counter()
        path = self._collection_path(collection_name)
        with self._collection_lock(collection_name):
            payload = self._read_collection(path, collection_name=collection_name)
            dimension = int(payload.get("dimension", 0))
            records = payload.setdefault("records", {})

            success_count = 0
            errors: list[dict[str, Any]] = []
            for record in request.records:
                if len(record.vector) != dimension:
                    errors.append(
                        {
                            "chunk_id": record.chunk_id,
                            "code": "vector_store_dimension_mismatch",
                            "message": (
                                f"Record '{record.chunk_id}' dimension "
                                f"{len(record.vector)} does not match collection "
                                f"dimension {dimension}."
                            ),
                        }
                    )
                    continue
                records[record.chunk_id] = record.model_dump(mode="json")
                success_count += 1

            self._write_collection(path, payload, collection_name=collection_name)

        latency_ms = int((time.perf_counter() - start_time) * 1000)
        return VectorUpsertResult(
            trace_id=trace_id,
            provider=self.provider_name,
            collection_name=collection_name,
            index_version=request.index_version,
            total_count=len(request.records),
            success_count=success_count,
            failed_count=len(request.records) - success_count,
            latency_ms=latency_ms,
            errors=errors,
        )

    def query(
        self,
        *,
        collection_name: str,
        request: VectorQueryRequest,
        trace_id: str,
    ) -> VectorQueryResult:
        start_time = time.perf_counter()
        path = self._collection_path(collection_name)
        with self._collection_lock(collection_name):
            payload = self._read_collection(path, collection_name=collection_name)
            dimension = int(payload.get("dimension", 0))
            metric_type = payload.get(
                "metric_type", self._settings.vector_store_default_metric
            )
            raw_records = payload.get("records", {})

        if len(request.query_vector) != dimension:
            raise VectorStoreDimensionMismatchError(
                f"Query vector dimension {len(request.query_vector)} does not match "
                f"collection dimension {dimension}."
            )

        records = [
            VectorRecord.model_validate(item)
            for item in raw_records.values()
            if isinstance(item, dict)
        ]
        hits: list[VectorHit] = []
        for record in records:
            if not self._matches_filters(record, request.filters):
                continue
            hits.append(
                VectorHit(
                    chunk_id=record.chunk_id,
                    document_id=record.document_id,
                    score=self._score(
                        request.query_vector,
                        record.vector,
                        metric_type=metric_type,
                    ),
                    text=record.text,
                    metadata=dict(record.metadata),
                )
            )

        hits.sort(key=lambda item: item.score, reverse=True)
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        return VectorQueryResult(
            trace_id=trace_id,
            provider=self.provider_name,
            collection_name=collection_name,
            total_hits=min(len(hits), request.top_k),
            hits=hits[: request.top_k],
            latency_ms=latency_ms,
        )

    def delete(
        self,
        *,
        collection_name: str,
        request: VectorDeleteRequest,
        trace_id: str,
    ) -> VectorDeleteResult:
        start_time = time.perf_counter()
        path = self._collection_path(collection_name)
        with self._collection_lock(collection_name):
            payload = self._read_collection(path, collection_name=collection_name)
            records = payload.setdefault("records", {})
            requested_count = len(request.chunk_ids) + len(request.document_ids)
            deleted_count = 0

            if request.chunk_ids:
                for chunk_id in request.chunk_ids:
                    if chunk_id in records:
                        del records[chunk_id]
                        deleted_count += 1

            if request.document_ids:
                target_documents = set(request.document_ids)
                chunk_ids_to_delete = [
                    chunk_id
                    for chunk_id, item in records.items()
                    if isinstance(item, dict)
                    and item.get("document_id") in target_documents
                ]
                for chunk_id in chunk_ids_to_delete:
                    del records[chunk_id]
                    deleted_count += 1

            self._write_collection(path, payload, collection_name=collection_name)

        latency_ms = int((time.perf_counter() - start_time) * 1000)
        return VectorDeleteResult(
            trace_id=trace_id,
            provider=self.provider_name,
            collection_name=collection_name,
            requested_count=requested_count,
            deleted_count=deleted_count,
            latency_ms=latency_ms,
        )

    def lookup_document(
        self,
        *,
        collection_name: str,
        request: VectorDocumentLookupRequest,
        trace_id: str,
    ) -> VectorDocumentLookupResult:
        start_time = time.perf_counter()
        path = self._collection_path(collection_name)
        if not path.exists():
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            return VectorDocumentLookupResult(
                trace_id=trace_id,
                provider=self.provider_name,
                collection_name=collection_name,
                document_id=request.document_id,
                exists=False,
                chunk_count=0,
                latency_ms=latency_ms,
            )

        with self._collection_lock(collection_name):
            payload = self._read_collection(path, collection_name=collection_name)
            raw_records = payload.get("records", {})

        chunk_count = 0
        metadata: dict[str, Any] = {}
        for item in raw_records.values():
            if not isinstance(item, dict):
                continue
            if item.get("document_id") != request.document_id:
                continue
            chunk_count += 1
            if not metadata:
                metadata = dict(item.get("metadata") or {})

        latency_ms = int((time.perf_counter() - start_time) * 1000)
        return VectorDocumentLookupResult(
            trace_id=trace_id,
            provider=self.provider_name,
            collection_name=collection_name,
            document_id=request.document_id,
            exists=chunk_count > 0,
            chunk_count=chunk_count,
            metadata=metadata,
            latency_ms=latency_ms,
        )

    def describe_capabilities(self) -> VectorStoreCapabilities:
        return VectorStoreCapabilities(
            provider=self.provider_name,
            supports_metadata_filter=True,
            supports_delete_by_document=True,
            supports_collection_schema=True,
            supports_namespace=False,
        )

    def _read_collection(
        self,
        path: Path,
        *,
        collection_name: str,
    ) -> dict[str, Any]:
        if not path.exists():
            raise VectorStoreCollectionError(
                f"Collection '{collection_name}' does not exist."
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise VectorStoreCollectionError(
                f"Failed to read collection '{collection_name}'."
            ) from exc
        if not isinstance(payload, dict):
            raise VectorStoreCollectionError(
                f"Collection '{collection_name}' payload is invalid."
            )
        return payload

    def _write_collection(
        self,
        path: Path,
        payload: dict[str, Any],
        *,
        collection_name: str,
    ) -> None:
        tmp_path = path.with_suffix(".tmp")
        try:
            tmp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(path)
        except OSError as exc:
            raise VectorStoreWriteError(
                f"Failed to persist collection '{collection_name}'."
            ) from exc

    def _collection_path(self, collection_name: str) -> Path:
        return self._base_dir / f"{collection_name}.json"

    def _collection_lock(self, collection_name: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(collection_name, threading.Lock())

    @staticmethod
    def _matches_filters(record: VectorRecord, filters: dict[str, Any]) -> bool:
        if not filters:
            return True
        for key, expected in filters.items():
            actual = record.metadata.get(key)
            if isinstance(actual, list):
                if isinstance(expected, list):
                    if not any(item in actual for item in expected):
                        return False
                elif expected not in actual:
                    return False
                continue
            if isinstance(expected, list):
                if actual not in expected:
                    return False
                continue
            if actual != expected:
                return False
        return True

    @staticmethod
    def _score(
        left: list[float],
        right: list[float],
        *,
        metric_type: MetricType | str,
    ) -> float:
        if len(left) != len(right):
            raise VectorStoreDimensionMismatchError(
                "Vector dimensions do not match for scoring."
            )
        if not left:
            raise VectorStoreValidationError("Vector must not be empty.")

        if metric_type == "dot":
            return sum(a * b for a, b in zip(left, right))
        if metric_type == "euclidean":
            distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right)))
            return -distance
        if metric_type != "cosine":
            raise VectorStoreQueryError(f"Unsupported metric type '{metric_type}'.")

        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            raise VectorStoreValidationError("Vector norm must not be zero.")
        return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)
