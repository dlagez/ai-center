from __future__ import annotations

import time
import uuid

from app.core.config import ChunkingSettings
from app.core.exceptions import (
    ChunkingBadDocumentError,
    ChunkingEmptyInputError,
    ChunkingPolicyError,
)
from app.runtime.retrieval.chunking.document_chunker import DocumentChunker
from app.runtime.retrieval.chunking.policies import resolve_chunking_policy
from app.runtime.retrieval.chunking.schemas import ChunkingRequest, ChunkingResult
from app.runtime.retrieval.chunking.text_chunker import TextChunker


class ChunkingService:
    def __init__(
        self,
        *,
        settings: ChunkingSettings | None = None,
        document_chunker: DocumentChunker | None = None,
        text_chunker: TextChunker | None = None,
    ) -> None:
        self._settings = settings or ChunkingSettings.from_env()
        self._text_chunker = text_chunker or TextChunker()
        self._document_chunker = document_chunker or DocumentChunker(self._text_chunker)

    def chunk_document(self, request: ChunkingRequest) -> ChunkingResult:
        start_time = time.perf_counter()
        try:
            policy = resolve_chunking_policy(request.policy, settings=self._settings)
        except ValueError as exc:
            raise ChunkingPolicyError(str(exc)) from exc

        if request.parsed_document is not None:
            parsed_document = request.parsed_document
            if not parsed_document.text.strip():
                raise ChunkingBadDocumentError("Parsed document text is empty.")
            chunks = self._document_chunker.chunk(
                document_id=request.document_id,
                policy=policy,
                parsed_document=parsed_document,
                metadata=self._build_chunk_metadata(request),
            )
            source_type = parsed_document.source_type
            file_name = parsed_document.file_name
            file_type = parsed_document.file_type
            input_length = len(parsed_document.text)
        elif (request.raw_text or "").strip():
            raw_text = request.raw_text or ""
            chunks = self._text_chunker.chunk(
                document_id=request.document_id,
                policy=policy,
                raw_text=raw_text,
                metadata=self._build_chunk_metadata(request),
            )
            source_type = "raw_text"
            file_name = request.file_name
            file_type = request.file_type
            input_length = len(raw_text)
        else:
            raise ChunkingEmptyInputError("Chunking input is empty.")

        latency_ms = int((time.perf_counter() - start_time) * 1000)
        chunk_lengths = [len(chunk.text) for chunk in chunks]
        return ChunkingResult(
            trace_id=uuid.uuid4().hex,
            document_id=request.document_id,
            total_chunks=len(chunks),
            chunks=chunks,
            policy_name=policy.policy_name,
            source_type=source_type,
            file_name=file_name,
            file_type=file_type,
            metadata={
                **request.metadata,
                "input_length": input_length,
                "avg_chunk_length": int(sum(chunk_lengths) / len(chunk_lengths))
                if chunk_lengths
                else 0,
                "max_chunk_length": max(chunk_lengths) if chunk_lengths else 0,
            },
            latency_ms=latency_ms,
        )

    def _build_chunk_metadata(self, request: ChunkingRequest) -> dict[str, object]:
        return {
            "tenant_id": request.tenant_id,
            "app_id": request.app_id,
            "scene": request.scene,
            **request.metadata,
        }


def build_default_chunking_service(
    settings: ChunkingSettings | None = None,
) -> ChunkingService:
    return ChunkingService(settings=settings)
