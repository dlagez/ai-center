from __future__ import annotations

import unittest

from app.core.config import RetrievalSettings
from app.core.exceptions import (
    EmbeddingTimeoutError,
    RetrievalEmbeddingError,
    RetrievalFilterError,
    RetrievalQueryEmptyError,
)
from app.observability.metrics.retrieval_call_recorder import (
    InMemoryRetrievalCallRecorder,
)
from app.runtime.embedding.schemas import EmbeddedChunk, EmbeddingBatchResult
from app.runtime.retrieval import RetrievalRequest, RetrieverService
from app.runtime.retrieval.vector_store.schemas import VectorHit, VectorQueryResult


class FakeEmbeddingGatewayService:
    def __init__(
        self,
        *,
        result: EmbeddingBatchResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self._result = result
        self._error = error
        self.requests = []

    def embed(self, request):
        self.requests.append(request)
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


class FakeVectorStoreService:
    def __init__(
        self,
        *,
        result: VectorQueryResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self._result = result
        self._error = error
        self.requests = []

    def query_vectors(self, request):
        self.requests.append(request)
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


class RetrieverServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = RetrievalSettings(
            retrieval_default_top_k=3,
            retrieval_max_top_k=5,
            retrieval_default_score_threshold=None,
            retrieval_timeout_ms=30000,
            retrieval_enable_hybrid=False,
            retrieval_query_logical_model="embedding_query_default",
        )

    def test_retrieve_runs_full_vector_search_flow(self) -> None:
        recorder = InMemoryRetrievalCallRecorder()
        embedding_service = FakeEmbeddingGatewayService(
            result=EmbeddingBatchResult(
                trace_id="embedding-trace",
                logical_model="embedding_query_default",
                final_channel="litellm_proxy",
                final_provider="litellm_proxy",
                final_model="text-embedding-3-small",
                dimension=2,
                items=[
                    EmbeddedChunk(
                        chunk_id="query:1",
                        text="alpha question",
                        vector=[1.0, 0.0],
                        dimension=2,
                    )
                ],
                latency_ms=10,
            )
        )
        vector_service = FakeVectorStoreService(
            result=VectorQueryResult(
                trace_id="vector-trace",
                provider="local_file",
                collection_name="kb_tenant-a__app-a__kb-a__main__v1",
                total_hits=1,
                hits=[
                    VectorHit(
                        chunk_id="chunk-1",
                        document_id="doc-1",
                        score=0.92,
                        text="alpha answer",
                        metadata={
                            "tenant_id": "tenant-a",
                            "app_id": "app-a",
                            "knowledge_base_id": "kb-a",
                            "document_id": "doc-1",
                            "tag": "finance",
                            "source_position": {"page_no": 3, "start_offset": 12},
                        },
                    )
                ],
                latency_ms=15,
            )
        )
        service = RetrieverService(
            settings=self.settings,
            embedding_service=embedding_service,
            vector_store_service=vector_service,
            recorder=recorder,
        )

        result = service.retrieve(
            RetrievalRequest(
                tenant_id="tenant-a",
                app_id="app-a",
                knowledge_base_id="kb-a",
                query="  alpha question  ",
                document_ids=["doc-1"],
                filters={"tag": "finance"},
            )
        )

        self.assertEqual(result.query, "alpha question")
        self.assertEqual(result.total_hits, 1)
        self.assertEqual(result.hits[0].chunk_id, "chunk-1")
        self.assertEqual(result.hits[0].source_position["page_no"], 3)
        self.assertEqual(embedding_service.requests[0].logical_model, "embedding_query_default")
        self.assertEqual(embedding_service.requests[0].items[0].text, "alpha question")
        self.assertEqual(vector_service.requests[0].filters["tenant_id"], "tenant-a")
        self.assertEqual(vector_service.requests[0].filters["app_id"], "app-a")
        self.assertEqual(vector_service.requests[0].filters["knowledge_base_id"], "kb-a")
        self.assertEqual(vector_service.requests[0].filters["document_id"], ["doc-1"])
        self.assertEqual(vector_service.requests[0].filters["tag"], "finance")
        self.assertEqual(recorder.records[-1].status, "success")
        self.assertEqual(recorder.records[-1].candidate_count, 1)

    def test_retrieve_applies_threshold_dedup_and_include_flags(self) -> None:
        embedding_service = FakeEmbeddingGatewayService(
            result=EmbeddingBatchResult(
                trace_id="embedding-trace",
                logical_model="embedding_query_default",
                final_channel="litellm_proxy",
                final_provider="litellm_proxy",
                final_model="text-embedding-3-small",
                dimension=2,
                items=[
                    EmbeddedChunk(
                        chunk_id="query:1",
                        text="alpha question",
                        vector=[1.0, 0.0],
                        dimension=2,
                    )
                ],
                latency_ms=10,
            )
        )
        vector_service = FakeVectorStoreService(
            result=VectorQueryResult(
                trace_id="vector-trace",
                provider="local_file",
                collection_name="kb_tenant-a__app-a__kb-a__main__v1",
                total_hits=3,
                hits=[
                    VectorHit(
                        chunk_id="chunk-1",
                        document_id="doc-1",
                        score=0.95,
                        text="alpha answer",
                        metadata={
                            "tag": "finance",
                            "source_position": {"page_no": 3},
                        },
                    ),
                    VectorHit(
                        chunk_id="chunk-1",
                        document_id="doc-1",
                        score=0.90,
                        text="duplicate answer",
                        metadata={"tag": "finance"},
                    ),
                    VectorHit(
                        chunk_id="chunk-2",
                        document_id="doc-2",
                        score=0.40,
                        text="low score",
                        metadata={"tag": "legal", "source_position": {"page_no": 9}},
                    ),
                ],
                latency_ms=15,
            )
        )
        service = RetrieverService(
            settings=self.settings,
            embedding_service=embedding_service,
            vector_store_service=vector_service,
        )

        result = service.retrieve(
            RetrievalRequest(
                tenant_id="tenant-a",
                app_id="app-a",
                knowledge_base_id="kb-a",
                query="alpha question",
                score_threshold=0.6,
                include_text=False,
                include_positions=False,
            )
        )

        self.assertEqual(result.total_hits, 1)
        self.assertIsNone(result.hits[0].text)
        self.assertEqual(result.hits[0].metadata["tag"], "finance")
        self.assertEqual(result.hits[0].source_position, {})
        self.assertEqual(result.debug_info["below_threshold_count"], 1)
        self.assertEqual(result.debug_info["deduped_count"], 1)

    def test_retrieve_clamps_top_k_to_configured_max(self) -> None:
        embedding_service = FakeEmbeddingGatewayService(
            result=EmbeddingBatchResult(
                trace_id="embedding-trace",
                logical_model="embedding_query_default",
                final_channel="litellm_proxy",
                final_provider="litellm_proxy",
                final_model="text-embedding-3-small",
                dimension=2,
                items=[
                    EmbeddedChunk(
                        chunk_id="query:1",
                        text="alpha question",
                        vector=[1.0, 0.0],
                        dimension=2,
                    )
                ],
                latency_ms=10,
            )
        )
        vector_service = FakeVectorStoreService(
            result=VectorQueryResult(
                trace_id="vector-trace",
                provider="local_file",
                collection_name="kb_tenant-a__app-a__kb-a__main__v1",
                total_hits=0,
                hits=[],
                latency_ms=15,
            )
        )
        service = RetrieverService(
            settings=self.settings,
            embedding_service=embedding_service,
            vector_store_service=vector_service,
        )

        service.retrieve(
            RetrievalRequest(
                tenant_id="tenant-a",
                app_id="app-a",
                knowledge_base_id="kb-a",
                query="alpha question",
                top_k=99,
            )
        )

        self.assertEqual(vector_service.requests[0].top_k, 5)

    def test_retrieve_rejects_empty_query(self) -> None:
        service = RetrieverService(
            settings=self.settings,
            embedding_service=FakeEmbeddingGatewayService(),
            vector_store_service=FakeVectorStoreService(),
        )

        with self.assertRaises(RetrievalQueryEmptyError):
            service.retrieve(
                RetrievalRequest(
                    tenant_id="tenant-a",
                    app_id="app-a",
                    knowledge_base_id="kb-a",
                    query="   ",
                )
            )

    def test_retrieve_maps_embedding_failures_and_records_error(self) -> None:
        recorder = InMemoryRetrievalCallRecorder()
        service = RetrieverService(
            settings=self.settings,
            embedding_service=FakeEmbeddingGatewayService(
                error=EmbeddingTimeoutError("embedding timeout")
            ),
            vector_store_service=FakeVectorStoreService(),
            recorder=recorder,
        )

        with self.assertRaises(RetrievalEmbeddingError):
            service.retrieve(
                RetrievalRequest(
                    tenant_id="tenant-a",
                    app_id="app-a",
                    knowledge_base_id="kb-a",
                    query="alpha question",
                )
            )

        self.assertEqual(recorder.records[-1].status, "error")
        self.assertEqual(recorder.records[-1].error_code, "retrieval_embedding_error")

    def test_retrieve_rejects_conflicting_scoped_filters(self) -> None:
        service = RetrieverService(
            settings=self.settings,
            embedding_service=FakeEmbeddingGatewayService(),
            vector_store_service=FakeVectorStoreService(),
        )

        with self.assertRaises(RetrievalFilterError):
            service.retrieve(
                RetrievalRequest(
                    tenant_id="tenant-a",
                    app_id="app-a",
                    knowledge_base_id="kb-a",
                    query="alpha question",
                    filters={"tenant_id": "tenant-b"},
                )
            )


if __name__ == "__main__":
    unittest.main()
