from __future__ import annotations

import uuid
from typing import Any

from app.modules.knowledge_center.schemas import (
    KnowledgeDeleteRequest,
    KnowledgeDeleteResult,
    KnowledgeIndexResult,
    KnowledgeIndexSourceRequest,
    KnowledgeIndexTextRequest,
)
from app.modules.knowledge_center.services.document_chunk_service import (
    DocumentChunkService,
    build_document_chunk_service,
)
from app.runtime.embedding.gateway_service import (
    EmbeddingGatewayService,
    build_embedding_gateway_service,
)
from app.runtime.embedding.schemas import EmbeddingBatchRequest, EmbeddingInputItem
from app.runtime.retrieval import (
    VectorDeleteRequest,
    VectorRecord,
    VectorStoreService,
    VectorUpsertRequest,
    build_default_vector_store_service,
)
from app.runtime.retrieval.chunking import ChunkDocument, ChunkingResult

_EMBEDDING_SCENE = "knowledge_index"


class KnowledgeIndexService:
    def __init__(
        self,
        document_chunk_service: DocumentChunkService,
        *,
        embedding_service: EmbeddingGatewayService | None = None,
        vector_store_service: VectorStoreService | None = None,
    ) -> None:
        self._document_chunk_service = document_chunk_service
        self._embedding_service = embedding_service or build_embedding_gateway_service()
        self._vector_store_service = (
            vector_store_service or build_default_vector_store_service()
        )

    def ingest_source(
        self,
        request: KnowledgeIndexSourceRequest,
    ) -> KnowledgeIndexResult:
        trace_id = uuid.uuid4().hex
        chunk_result = self._document_chunk_service.parse_and_chunk(
            tenant_id=request.tenant_id,
            app_id=request.app_id,
            source_type=request.source_type,
            source_value=request.source_value,
            document_id=request.document_id,
            scene=request.scene,
            file_name=request.file_name,
            file_type=request.file_type,
            provider=request.provider,
            policy=request.policy,
            metadata=self._build_pipeline_metadata(
                request.metadata,
                trace_id=trace_id,
                knowledge_base_id=request.knowledge_base_id,
                index_name=request.index_name,
                index_version=request.index_version,
            ),
        )
        return self._index_chunks(
            tenant_id=request.tenant_id,
            app_id=request.app_id,
            knowledge_base_id=request.knowledge_base_id,
            index_name=request.index_name,
            index_version=request.index_version,
            logical_model=request.logical_model,
            timeout_ms=request.timeout_ms,
            request_metadata=request.metadata,
            chunk_result=chunk_result,
            trace_id=trace_id,
        )

    def ingest_raw_text(
        self,
        request: KnowledgeIndexTextRequest,
    ) -> KnowledgeIndexResult:
        trace_id = uuid.uuid4().hex
        chunk_result = self._document_chunk_service.chunk_raw_text(
            tenant_id=request.tenant_id,
            app_id=request.app_id,
            document_id=request.document_id,
            raw_text=request.raw_text,
            scene=request.scene,
            file_name=request.file_name,
            file_type=request.file_type,
            policy=request.policy,
            metadata=self._build_pipeline_metadata(
                request.metadata,
                trace_id=trace_id,
                knowledge_base_id=request.knowledge_base_id,
                index_name=request.index_name,
                index_version=request.index_version,
            ),
        )
        return self._index_chunks(
            tenant_id=request.tenant_id,
            app_id=request.app_id,
            knowledge_base_id=request.knowledge_base_id,
            index_name=request.index_name,
            index_version=request.index_version,
            logical_model=request.logical_model,
            timeout_ms=request.timeout_ms,
            request_metadata=request.metadata,
            chunk_result=chunk_result,
            trace_id=trace_id,
        )

    def delete_document(
        self,
        request: KnowledgeDeleteRequest,
    ) -> KnowledgeDeleteResult:
        trace_id = uuid.uuid4().hex
        vector_result = self._vector_store_service.delete_records(
            VectorDeleteRequest(
                tenant_id=request.tenant_id,
                app_id=request.app_id,
                knowledge_base_id=request.knowledge_base_id,
                index_name=request.index_name,
                index_version=request.index_version,
                document_ids=[request.document_id],
                metadata=self._build_pipeline_metadata(
                    request.metadata,
                    trace_id=trace_id,
                    knowledge_base_id=request.knowledge_base_id,
                    index_name=request.index_name,
                    index_version=request.index_version,
                ),
            )
        )
        return KnowledgeDeleteResult(
            trace_id=trace_id,
            document_id=request.document_id,
            knowledge_base_id=request.knowledge_base_id,
            index_name=request.index_name,
            index_version=request.index_version,
            collection_name=vector_result.collection_name,
            deleted_count=vector_result.deleted_count,
            vector_store_trace_id=vector_result.trace_id,
            metadata={
                **request.metadata,
                "vector_store_provider": vector_result.provider,
                "vector_store_latency_ms": vector_result.latency_ms,
            },
        )

    def _index_chunks(
        self,
        *,
        tenant_id: str,
        app_id: str,
        knowledge_base_id: str,
        index_name: str,
        index_version: str,
        logical_model: str | None,
        timeout_ms: int | None,
        request_metadata: dict[str, Any],
        chunk_result: ChunkingResult,
        trace_id: str,
    ) -> KnowledgeIndexResult:
        if not chunk_result.chunks:
            raise ValueError("Knowledge indexing produced no chunks.")

        embedding_result = self._embedding_service.embed(
            EmbeddingBatchRequest(
                tenant_id=tenant_id,
                app_id=app_id,
                scene=_EMBEDDING_SCENE,
                logical_model=logical_model,
                items=[
                    EmbeddingInputItem(
                        chunk_id=chunk.chunk_id,
                        text=chunk.text,
                        metadata={
                            "document_id": chunk.document_id,
                            "chunk_index": chunk.chunk_index,
                        },
                    )
                    for chunk in chunk_result.chunks
                ],
                timeout_ms=timeout_ms,
                metadata=self._build_pipeline_metadata(
                    request_metadata,
                    trace_id=trace_id,
                    knowledge_base_id=knowledge_base_id,
                    index_name=index_name,
                    index_version=index_version,
                ),
            )
        )

        vector_result = self._vector_store_service.upsert_records(
            VectorUpsertRequest(
                tenant_id=tenant_id,
                app_id=app_id,
                knowledge_base_id=knowledge_base_id,
                index_name=index_name,
                index_version=index_version,
                records=self._build_vector_records(
                    chunk_result.chunks,
                    embedding_result.items,
                    source_type=chunk_result.source_type,
                    file_name=chunk_result.file_name,
                    file_type=chunk_result.file_type,
                ),
                metadata=self._build_pipeline_metadata(
                    request_metadata,
                    trace_id=trace_id,
                    knowledge_base_id=knowledge_base_id,
                    index_name=index_name,
                    index_version=index_version,
                ),
            )
        )

        return KnowledgeIndexResult(
            trace_id=trace_id,
            document_id=chunk_result.document_id,
            knowledge_base_id=knowledge_base_id,
            index_name=index_name,
            index_version=index_version,
            collection_name=vector_result.collection_name,
            source_type=chunk_result.source_type,
            file_name=chunk_result.file_name,
            file_type=chunk_result.file_type,
            total_chunks=chunk_result.total_chunks,
            embedded_count=len(embedding_result.items),
            success_count=vector_result.success_count,
            failed_count=vector_result.failed_count,
            chunking_trace_id=chunk_result.trace_id,
            embedding_trace_id=embedding_result.trace_id,
            vector_store_trace_id=vector_result.trace_id,
            metadata={
                **request_metadata,
                "chunk_policy_name": chunk_result.policy_name,
                "embedding_provider": embedding_result.final_provider,
                "embedding_model": embedding_result.final_model,
                "embedding_latency_ms": embedding_result.latency_ms,
                "vector_store_provider": vector_result.provider,
                "vector_store_latency_ms": vector_result.latency_ms,
            },
        )

    @staticmethod
    def _build_pipeline_metadata(
        metadata: dict[str, Any],
        *,
        trace_id: str,
        knowledge_base_id: str,
        index_name: str,
        index_version: str,
    ) -> dict[str, Any]:
        return {
            **metadata,
            "knowledge_index_trace_id": trace_id,
            "knowledge_base_id": knowledge_base_id,
            "index_name": index_name,
            "index_version": index_version,
        }

    @staticmethod
    def _build_vector_records(
        chunks: list[ChunkDocument],
        embedded_items: list[Any],
        *,
        source_type: str | None,
        file_name: str | None,
        file_type: str | None,
    ) -> list[VectorRecord]:
        embedded_by_chunk_id = {
            getattr(item, "chunk_id"): item for item in embedded_items
        }
        missing_chunk_ids = [
            chunk.chunk_id for chunk in chunks if chunk.chunk_id not in embedded_by_chunk_id
        ]
        if missing_chunk_ids:
            raise ValueError(
                "Embedding result is missing vectors for chunk_ids: "
                + ", ".join(sorted(missing_chunk_ids))
            )

        records: list[VectorRecord] = []
        for chunk in chunks:
            source_positions = [
                position.model_dump(mode="json", exclude_none=True)
                for position in chunk.source_positions
            ]
            metadata = {
                **chunk.metadata,
                "chunk_index": chunk.chunk_index,
                "title_path": list(chunk.title_path),
                "page_range": list(chunk.page_range),
                "source_block_ids": list(chunk.source_block_ids),
                "source_positions": source_positions,
                "policy_name": chunk.policy_name,
                "source_type": source_type,
                "file_name": file_name,
                "file_type": file_type,
            }
            if source_positions:
                metadata["source_position"] = source_positions[0]

            embedded_item = embedded_by_chunk_id[chunk.chunk_id]
            records.append(
                VectorRecord(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    text=chunk.text,
                    vector=list(getattr(embedded_item, "vector")),
                    metadata=metadata,
                )
            )
        return records


def build_knowledge_index_service(
    *,
    document_chunk_service: DocumentChunkService | None = None,
    embedding_service: EmbeddingGatewayService | None = None,
    vector_store_service: VectorStoreService | None = None,
) -> KnowledgeIndexService:
    return KnowledgeIndexService(
        document_chunk_service or build_document_chunk_service(),
        embedding_service=embedding_service,
        vector_store_service=vector_store_service,
    )
