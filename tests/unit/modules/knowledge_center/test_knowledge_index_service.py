from __future__ import annotations

import unittest

from app.modules.knowledge_center import (
    KnowledgeDeleteRequest,
    KnowledgeIndexSourceRequest,
    KnowledgeIndexTextRequest,
)
from app.modules.knowledge_center.schemas import KnowledgeIndexResult
from app.modules.knowledge_center.services.knowledge_index_service import (
    KnowledgeIndexService,
)
from app.runtime.embedding.schemas import (
    EmbeddedChunk,
    EmbeddingBatchResult,
    EmbeddingUsageInfo,
)
from app.runtime.retrieval import (
    VectorDeleteResult,
    VectorUpsertResult,
)
from app.runtime.retrieval.chunking import (
    ChunkDocument,
    ChunkSourcePosition,
    ChunkingResult,
)


class FakeDocumentChunkService:
    def __init__(self, chunk_result: ChunkingResult) -> None:
        self._chunk_result = chunk_result
        self.parse_calls: list[dict[str, object]] = []
        self.raw_calls: list[dict[str, object]] = []

    def parse_and_chunk(self, **kwargs: object) -> ChunkingResult:
        self.parse_calls.append(kwargs)
        return self._chunk_result

    def chunk_raw_text(self, **kwargs: object) -> ChunkingResult:
        self.raw_calls.append(kwargs)
        return self._chunk_result


class FakeEmbeddingService:
    def __init__(self, result: EmbeddingBatchResult) -> None:
        self._result = result
        self.requests: list[object] = []

    def embed(self, request: object) -> EmbeddingBatchResult:
        self.requests.append(request)
        return self._result


class FakeVectorStoreService:
    def __init__(self) -> None:
        self.upsert_requests: list[object] = []
        self.delete_requests: list[object] = []

    def upsert_records(self, request: object) -> VectorUpsertResult:
        self.upsert_requests.append(request)
        records = getattr(request, "records")
        return VectorUpsertResult(
            trace_id="vector-upsert-trace",
            provider="local_file",
            collection_name="kb_tenant-a__app-a__kb-a__main__v1",
            index_version=getattr(request, "index_version"),
            total_count=len(records),
            success_count=len(records),
            failed_count=0,
            latency_ms=5,
        )

    def delete_records(self, request: object) -> VectorDeleteResult:
        self.delete_requests.append(request)
        return VectorDeleteResult(
            trace_id="vector-delete-trace",
            provider="local_file",
            collection_name="kb_tenant-a__app-a__kb-a__main__v1",
            requested_count=len(getattr(request, "document_ids")),
            deleted_count=len(getattr(request, "document_ids")),
            latency_ms=3,
        )


class KnowledgeIndexServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.chunk_result = ChunkingResult(
            trace_id="chunk-trace",
            document_id="doc-1",
            total_chunks=1,
            chunks=[
                ChunkDocument(
                    chunk_id="chunk-1",
                    document_id="doc-1",
                    chunk_index=0,
                    text="alpha beta",
                    title_path=["Overview"],
                    page_range=[1],
                    source_block_ids=["page:1:segment:1"],
                    source_positions=[
                        ChunkSourcePosition(
                            page_no=1,
                            block_id="page:1:segment:1",
                            start_offset=0,
                            end_offset=10,
                        )
                    ],
                    policy_name="default",
                    metadata={
                        "scene": "knowledge_ingest",
                        "char_count": 10,
                    },
                )
            ],
            policy_name="default",
            source_type="file_path",
            file_name="sample.md",
            file_type="md",
            metadata={
                "document_parse_cache_hit": False,
                "document_parse_strategy": "ocr",
                "document_parse_ocr_mode": "batched",
                "document_parse_ocr_batch_count": 2,
            },
            latency_ms=1,
        )
        self.embedding_result = EmbeddingBatchResult(
            trace_id="embedding-trace",
            logical_model="embedding_default",
            final_channel="litellm_proxy",
            final_provider="litellm_proxy",
            final_model="text-embedding-3-small",
            dimension=2,
            items=[
                EmbeddedChunk(
                    chunk_id="chunk-1",
                    text="alpha beta",
                    vector=[0.1, 0.2],
                    dimension=2,
                )
            ],
            usage=EmbeddingUsageInfo(prompt_tokens=8, total_tokens=8),
            latency_ms=12,
        )
        self.chunk_service = FakeDocumentChunkService(self.chunk_result)
        self.embedding_service = FakeEmbeddingService(self.embedding_result)
        self.vector_store_service = FakeVectorStoreService()
        self.service = KnowledgeIndexService(
            self.chunk_service,
            embedding_service=self.embedding_service,
            vector_store_service=self.vector_store_service,
        )

    def test_ingest_source_upserts_enriched_vector_records(self) -> None:
        result = self.service.ingest_source(
            KnowledgeIndexSourceRequest(
                tenant_id="tenant-a",
                app_id="app-a",
                knowledge_base_id="kb-a",
                source_type="file_path",
                source_value="sample.md",
                document_id="doc-1",
                metadata={"batch_id": "batch-1"},
            )
        )

        self.assertIsInstance(result, KnowledgeIndexResult)
        self.assertEqual(result.document_id, "doc-1")
        self.assertEqual(result.success_count, 1)
        self.assertEqual(len(self.chunk_service.parse_calls), 1)
        self.assertEqual(self.embedding_service.requests[0].scene, "knowledge_index")
        self.assertEqual(
            self.embedding_service.requests[0].metadata["knowledge_index_trace_id"],
            result.trace_id,
        )

        upsert_request = self.vector_store_service.upsert_requests[0]
        self.assertEqual(upsert_request.knowledge_base_id, "kb-a")
        self.assertEqual(upsert_request.records[0].document_id, "doc-1")
        self.assertEqual(upsert_request.records[0].metadata["title_path"], ["Overview"])
        self.assertEqual(upsert_request.records[0].metadata["source_type"], "file_path")
        self.assertEqual(
            upsert_request.records[0].metadata["source_position"]["page_no"],
            1,
        )
        self.assertEqual(
            upsert_request.records[0].metadata["source_positions"][0]["block_id"],
            "page:1:segment:1",
        )
        self.assertFalse(result.metadata["document_parse_cache_hit"])
        self.assertEqual(result.metadata["document_parse_strategy"], "ocr")
        self.assertEqual(result.metadata["document_parse_ocr_mode"], "batched")

    def test_ingest_raw_text_uses_chunk_raw_text(self) -> None:
        result = self.service.ingest_raw_text(
            KnowledgeIndexTextRequest(
                tenant_id="tenant-a",
                app_id="app-a",
                knowledge_base_id="kb-a",
                document_id="doc-1",
                raw_text="alpha beta",
                metadata={"source": "manual"},
            )
        )

        self.assertEqual(result.total_chunks, 1)
        self.assertEqual(len(self.chunk_service.raw_calls), 1)
        self.assertEqual(len(self.chunk_service.parse_calls), 0)

    def test_delete_document_delegates_to_vector_store(self) -> None:
        result = self.service.delete_document(
            KnowledgeDeleteRequest(
                tenant_id="tenant-a",
                app_id="app-a",
                knowledge_base_id="kb-a",
                document_id="doc-1",
            )
        )

        self.assertEqual(result.deleted_count, 1)
        self.assertEqual(
            self.vector_store_service.delete_requests[0].document_ids,
            ["doc-1"],
        )
        self.assertEqual(result.vector_store_trace_id, "vector-delete-trace")


if __name__ == "__main__":
    unittest.main()
