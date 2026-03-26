from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx

try:
    import grpc
except ImportError:  # pragma: no cover - optional dependency
    grpc = None

try:
    from qdrant_client import QdrantClient
    from qdrant_client import models
    from qdrant_client.http.exceptions import (
        ResponseHandlingException,
        UnexpectedResponse,
    )
except ImportError:  # pragma: no cover - handled in _build_client
    QdrantClient = None
    models = None
    ResponseHandlingException = UnexpectedResponse = None

from app.core.config import VectorStoreSettings
from app.core.exceptions import (
    VectorStoreAuthenticationError,
    VectorStoreCollectionError,
    VectorStoreConfigurationError,
    VectorStoreDeleteError,
    VectorStoreDimensionMismatchError,
    VectorStoreProviderUnavailableError,
    VectorStoreQueryError,
    VectorStoreTimeoutError,
    VectorStoreValidationError,
    VectorStoreWriteError,
)
from app.integrations.vector_stores.base import BaseVectorStoreAdapter
from app.runtime.retrieval.vector_store.schemas import (
    EnsureCollectionRequest,
    EnsureCollectionResult,
    VectorDeleteRequest,
    VectorDeleteResult,
    VectorHit,
    VectorQueryRequest,
    VectorQueryResult,
    VectorRecord,
    VectorStoreCapabilities,
    VectorUpsertRequest,
    VectorUpsertResult,
)

_DISTANCE_MAP = {
    "cosine": "COSINE",
    "dot": "DOT",
    "euclidean": "EUCLID",
}

_KEYWORD_PAYLOAD_FIELDS = (
    "tenant_id",
    "app_id",
    "knowledge_base_id",
    "index_name",
    "index_version",
    "document_id",
    "chunk_id",
    "file_name",
    "file_type",
    "source_type",
    "policy_name",
)


class QdrantVectorStoreAdapter(BaseVectorStoreAdapter):
    provider_name = "qdrant"

    def __init__(
        self,
        settings: VectorStoreSettings,
        *,
        client: Any | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or self._build_client(settings)

    def ensure_collection(
        self,
        *,
        collection_name: str,
        request: EnsureCollectionRequest,
        trace_id: str,
    ) -> EnsureCollectionResult:
        start_time = time.perf_counter()
        metric_type = request.metric_type or self._settings.vector_store_default_metric
        distance = self._to_distance(metric_type)
        existed = False
        created = False

        try:
            if self._client.collection_exists(collection_name):
                info = self._client.get_collection(collection_name)
                vectors_config = getattr(info.config.params, "vectors", None)
                if vectors_config is None or not hasattr(vectors_config, "size"):
                    raise VectorStoreCollectionError(
                        f"Collection '{collection_name}' does not expose a single-vector config."
                    )
                stored_dimension = int(vectors_config.size)
                stored_distance = str(vectors_config.distance)
                if stored_dimension != request.dimension:
                    raise VectorStoreDimensionMismatchError(
                        f"Collection '{collection_name}' expects dimension "
                        f"{stored_dimension}, got {request.dimension}."
                    )
                if stored_distance != str(distance):
                    raise VectorStoreCollectionError(
                        f"Collection '{collection_name}' expects metric "
                        f"'{stored_distance}', got '{distance}'."
                    )
                existed = True
            else:
                self._client.create_collection(
                    collection_name=collection_name,
                    vectors_config=models.VectorParams(
                        size=request.dimension,
                        distance=distance,
                    ),
                    timeout=self._timeout_seconds,
                )
                self._ensure_payload_indexes(collection_name)
                created = True
        except Exception as exc:
            raise self._map_exception(exc, operation="ensure_collection") from exc

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
        points = [self._to_point(record) for record in request.records]
        try:
            self._client.upsert(
                collection_name=collection_name,
                points=points,
                wait=True,
            )
        except Exception as exc:
            raise self._map_exception(exc, operation="upsert") from exc

        latency_ms = int((time.perf_counter() - start_time) * 1000)
        return VectorUpsertResult(
            trace_id=trace_id,
            provider=self.provider_name,
            collection_name=collection_name,
            index_version=request.index_version,
            total_count=len(request.records),
            success_count=len(request.records),
            failed_count=0,
            latency_ms=latency_ms,
        )

    def query(
        self,
        *,
        collection_name: str,
        request: VectorQueryRequest,
        trace_id: str,
    ) -> VectorQueryResult:
        start_time = time.perf_counter()
        query_filter = self._build_filter(request.filters)

        try:
            response = self._client.query_points(
                collection_name=collection_name,
                query=request.query_vector,
                query_filter=query_filter,
                limit=request.top_k,
                with_payload=True,
                with_vectors=False,
                timeout=self._timeout_seconds,
            )
        except Exception as exc:
            raise self._map_exception(exc, operation="query") from exc

        hits: list[VectorHit] = []
        for point in response.points:
            payload = dict(getattr(point, "payload", {}) or {})
            chunk_id = str(payload.get("chunk_id") or "")
            document_id = str(payload.get("document_id") or "")
            text = payload.pop("text", None)
            hits.append(
                VectorHit(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    score=float(getattr(point, "score", 0.0) or 0.0),
                    text=text if isinstance(text, str) else None,
                    metadata=payload,
                )
            )

        latency_ms = int((time.perf_counter() - start_time) * 1000)
        return VectorQueryResult(
            trace_id=trace_id,
            provider=self.provider_name,
            collection_name=collection_name,
            total_hits=len(hits),
            hits=hits,
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
        point_ids = self._collect_target_point_ids(collection_name, request=request)
        requested_count = len(request.chunk_ids) + len(request.document_ids)

        if point_ids:
            try:
                self._client.delete(
                    collection_name=collection_name,
                    points_selector=models.PointIdsList(points=sorted(point_ids)),
                    wait=True,
                )
            except Exception as exc:
                raise self._map_exception(exc, operation="delete") from exc

        latency_ms = int((time.perf_counter() - start_time) * 1000)
        return VectorDeleteResult(
            trace_id=trace_id,
            provider=self.provider_name,
            collection_name=collection_name,
            requested_count=requested_count,
            deleted_count=len(point_ids),
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

    def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            close()

    @property
    def _timeout_seconds(self) -> int:
        return max(1, math.ceil(self._settings.vector_store_timeout_ms / 1000))

    @staticmethod
    def _build_client(settings: VectorStoreSettings) -> Any:
        if QdrantClient is None:
            raise VectorStoreConfigurationError(
                "The 'qdrant-client' package is required to use the Qdrant vector store adapter."
            )
        if settings.qdrant_local_mode:
            local_path = (settings.qdrant_local_path or "").strip()
            if not local_path:
                raise VectorStoreConfigurationError(
                    "Qdrant local mode requires QDRANT_LOCAL_PATH to be configured."
                )
            Path(local_path).mkdir(parents=True, exist_ok=True)
            return QdrantClient(
                path=local_path,
                timeout=max(1, math.ceil(settings.vector_store_timeout_ms / 1000)),
            )
        if not settings.qdrant_url:
            raise VectorStoreConfigurationError(
                "Qdrant vector store requires QDRANT_URL to be configured."
            )
        return QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            grpc_port=settings.qdrant_grpc_port,
            prefer_grpc=settings.qdrant_prefer_grpc,
            https=settings.qdrant_https,
            timeout=max(1, math.ceil(settings.vector_store_timeout_ms / 1000)),
        )

    def _ensure_payload_indexes(self, collection_name: str) -> None:
        if self._is_local_client():
            return
        for field_name in _KEYWORD_PAYLOAD_FIELDS:
            try:
                self._client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field_name,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                    wait=True,
                )
            except Exception as exc:
                raise self._map_exception(
                    exc,
                    operation="ensure_collection",
                ) from exc

        try:
            self._client.create_payload_index(
                collection_name=collection_name,
                field_name="chunk_index",
                field_schema=models.PayloadSchemaType.INTEGER,
                wait=True,
            )
        except Exception as exc:
            raise self._map_exception(exc, operation="ensure_collection") from exc

    def _is_local_client(self) -> bool:
        client_impl = getattr(self._client, "_client", None)
        module_name = getattr(type(client_impl), "__module__", "")
        return module_name.startswith("qdrant_client.local.")

    def _collect_target_point_ids(
        self,
        collection_name: str,
        *,
        request: VectorDeleteRequest,
    ) -> set[str]:
        point_ids: set[str] = set()
        if request.chunk_ids:
            point_ids.update(
                self._scroll_point_ids(
                    collection_name,
                    filter_=self._build_filter({"chunk_id": request.chunk_ids}),
                )
            )
        if request.document_ids:
            point_ids.update(
                self._scroll_point_ids(
                    collection_name,
                    filter_=self._build_filter({"document_id": request.document_ids}),
                )
            )
        return point_ids

    def _scroll_point_ids(self, collection_name: str, *, filter_: Any | None) -> set[str]:
        point_ids: set[str] = set()
        offset = None
        while True:
            try:
                records, offset = self._client.scroll(
                    collection_name=collection_name,
                    scroll_filter=filter_,
                    limit=256,
                    offset=offset,
                    with_payload=False,
                    with_vectors=False,
                    timeout=self._timeout_seconds,
                )
            except Exception as exc:
                raise self._map_exception(exc, operation="delete") from exc

            for record in records:
                point_ids.add(str(record.id))
            if offset is None:
                break
        return point_ids

    @staticmethod
    def _to_point(record: VectorRecord) -> Any:
        return models.PointStruct(
            id=str(uuid5(NAMESPACE_URL, record.chunk_id)),
            vector=list(record.vector),
            payload={
                "chunk_id": record.chunk_id,
                "document_id": record.document_id,
                "text": record.text,
                **dict(record.metadata),
            },
        )

    @staticmethod
    def _build_filter(filters: dict[str, Any]) -> Any | None:
        if not filters:
            return None

        conditions = []
        for key, expected in filters.items():
            if expected is None:
                continue
            if isinstance(expected, tuple):
                expected = list(expected)
            if isinstance(expected, list):
                if not expected:
                    raise VectorStoreValidationError(
                        f"Filter '{key}' must not be an empty list."
                    )
                if not all(isinstance(item, (str, int)) for item in expected):
                    raise VectorStoreValidationError(
                        f"Filter '{key}' only supports lists of str or int values."
                    )
                if len(expected) == 1:
                    conditions.append(
                        models.FieldCondition(
                            key=key,
                            match=models.MatchValue(value=expected[0]),
                        )
                    )
                else:
                    conditions.append(
                        models.FieldCondition(
                            key=key,
                            match=models.MatchAny(any=expected),
                        )
                    )
                continue
            if isinstance(expected, (str, int, bool)):
                conditions.append(
                    models.FieldCondition(
                        key=key,
                        match=models.MatchValue(value=expected),
                    )
                )
                continue
            raise VectorStoreValidationError(
                f"Filter '{key}' uses an unsupported value type: {type(expected).__name__}."
            )

        if not conditions:
            return None
        return models.Filter(must=conditions)

    @staticmethod
    def _to_distance(metric_type: str) -> Any:
        if models is None:
            raise VectorStoreConfigurationError(
                "The 'qdrant-client' package is required to use the Qdrant vector store adapter."
            )
        normalized_metric = metric_type.strip().lower()
        distance_name = _DISTANCE_MAP.get(normalized_metric)
        if distance_name is None:
            raise VectorStoreValidationError(
                f"Unsupported vector store metric type '{metric_type}'."
            )
        return getattr(models.Distance, distance_name)

    @staticmethod
    def _map_exception(exc: Exception, *, operation: str) -> Exception:
        if isinstance(
            exc,
            (
                VectorStoreAuthenticationError,
                VectorStoreCollectionError,
                VectorStoreConfigurationError,
                VectorStoreDeleteError,
                VectorStoreDimensionMismatchError,
                VectorStoreProviderUnavailableError,
                VectorStoreQueryError,
                VectorStoreTimeoutError,
                VectorStoreValidationError,
                VectorStoreWriteError,
            ),
        ):
            return exc

        if isinstance(exc, httpx.TimeoutException):
            return VectorStoreTimeoutError(str(exc))
        if grpc is not None and isinstance(exc, grpc.RpcError):
            code = exc.code()
            if code == grpc.StatusCode.DEADLINE_EXCEEDED:
                return VectorStoreTimeoutError(str(exc))
            if code == grpc.StatusCode.UNAUTHENTICATED:
                return VectorStoreAuthenticationError(str(exc))
            return VectorStoreProviderUnavailableError(str(exc))
        if isinstance(exc, httpx.HTTPStatusError):
            if exc.response.status_code in {401, 403}:
                return VectorStoreAuthenticationError(str(exc))
            if exc.response.status_code == 404:
                return VectorStoreCollectionError(str(exc))
            return QdrantVectorStoreAdapter._operation_error(operation, str(exc))
        if ResponseHandlingException is not None and isinstance(exc, ResponseHandlingException):
            cause = exc.__cause__
            if isinstance(cause, httpx.TimeoutException):
                return VectorStoreTimeoutError(str(cause))
            if isinstance(cause, httpx.RequestError):
                return VectorStoreProviderUnavailableError(str(cause))
            return VectorStoreProviderUnavailableError(str(exc))
        if UnexpectedResponse is not None and isinstance(exc, UnexpectedResponse):
            if exc.status_code in {401, 403}:
                return VectorStoreAuthenticationError(str(exc))
            if exc.status_code == 404:
                return VectorStoreCollectionError(str(exc))
            return QdrantVectorStoreAdapter._operation_error(operation, str(exc))
        if isinstance(exc, httpx.RequestError):
            return VectorStoreProviderUnavailableError(str(exc))
        if isinstance(exc, TimeoutError):
            return VectorStoreTimeoutError(str(exc))
        if isinstance(exc, ValueError):
            return VectorStoreValidationError(str(exc))
        return QdrantVectorStoreAdapter._operation_error(operation, str(exc))

    @staticmethod
    def _operation_error(operation: str, message: str) -> Exception:
        if operation == "query":
            return VectorStoreQueryError(message)
        if operation == "delete":
            return VectorStoreDeleteError(message)
        if operation == "upsert":
            return VectorStoreWriteError(message)
        return VectorStoreCollectionError(message)
