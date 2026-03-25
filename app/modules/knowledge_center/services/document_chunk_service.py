from __future__ import annotations

from app.core.config import ChunkingSettings, DocumentParseSettings, OCRSettings
from app.modules.document_center import (
    DocumentParseRequest,
    DocumentParseResult,
    DocumentParseService,
    build_document_parse_service,
)
from app.runtime.retrieval.chunking import (
    ChunkingPolicyConfig,
    ChunkingRequest,
    ChunkingResult,
    ChunkingService,
    build_default_chunking_service,
)


class DocumentChunkService:
    def __init__(
        self,
        chunking_service: ChunkingService,
        *,
        document_parse_service: DocumentParseService | None = None,
    ) -> None:
        self._chunking_service = chunking_service
        self._document_parse_service = document_parse_service

    def chunk_parsed_document(
        self,
        *,
        tenant_id: str,
        app_id: str,
        document_id: str,
        parsed_document: DocumentParseResult,
        scene: str = "knowledge_ingest",
        policy: ChunkingPolicyConfig | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ChunkingResult:
        request = ChunkingRequest(
            tenant_id=tenant_id,
            app_id=app_id,
            document_id=document_id,
            scene=scene,
            parsed_document=parsed_document,
            policy=policy,
            metadata=dict(metadata or {}),
        )
        return self._chunking_service.chunk_document(request)

    def parse_and_chunk(
        self,
        *,
        tenant_id: str,
        app_id: str,
        source_type: str,
        source_value: str,
        document_id: str | None = None,
        scene: str = "knowledge_ingest",
        file_name: str | None = None,
        file_type: str | None = None,
        provider: str | None = None,
        policy: ChunkingPolicyConfig | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ChunkingResult:
        if self._document_parse_service is None:
            raise ValueError("DocumentParseService is required for parse_and_chunk().")

        parse_request = DocumentParseRequest(
            tenant_id=tenant_id,
            app_id=app_id,
            scene=scene,
            source_type=source_type,
            source_value=source_value,
            file_name=file_name,
            file_type=file_type,
            provider=provider,
            metadata=dict(metadata or {}),
        )
        parsed_document = self._document_parse_service.parse(parse_request)
        resolved_document_id = document_id or parsed_document.asset_hash
        return self.chunk_parsed_document(
            tenant_id=tenant_id,
            app_id=app_id,
            document_id=resolved_document_id,
            parsed_document=parsed_document,
            scene=scene,
            policy=policy,
            metadata=metadata,
        )


def build_document_chunk_service(
    *,
    chunking_settings: ChunkingSettings | None = None,
    ocr_settings: OCRSettings | None = None,
    document_parse_settings: DocumentParseSettings | None = None,
    chunking_service: ChunkingService | None = None,
    document_parse_service: DocumentParseService | None = None,
) -> DocumentChunkService:
    chunking_service = chunking_service or build_default_chunking_service(
        chunking_settings
    )
    document_parse_service = document_parse_service or build_document_parse_service(
        ocr_settings=ocr_settings,
        document_parse_settings=document_parse_settings,
    )
    return DocumentChunkService(
        chunking_service,
        document_parse_service=document_parse_service,
    )
