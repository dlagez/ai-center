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
from app.runtime.retrieval.chunking.policies import resolve_chunking_policy


class DocumentChunkService:
    def __init__(
        self,
        chunking_service: ChunkingService,
        *,
        document_parse_service: DocumentParseService | None = None,
    ) -> None:
        self._chunking_service = chunking_service
        self._document_parse_service = document_parse_service

    def chunk_raw_text(
        self,
        *,
        tenant_id: str,
        app_id: str,
        document_id: str,
        raw_text: str,
        scene: str = "knowledge_ingest",
        file_name: str | None = None,
        file_type: str | None = None,
        policy: ChunkingPolicyConfig | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ChunkingResult:
        request = ChunkingRequest(
            tenant_id=tenant_id,
            app_id=app_id,
            document_id=document_id,
            scene=scene,
            raw_text=raw_text,
            file_name=file_name,
            file_type=file_type,
            policy=policy,
            metadata=dict(metadata or {}),
        )
        return self._chunking_service.chunk_document(request)

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
        chunk_result = self.chunk_parsed_document(
            tenant_id=tenant_id,
            app_id=app_id,
            document_id=resolved_document_id,
            parsed_document=parsed_document,
            scene=scene,
            policy=policy,
            metadata=metadata,
        )
        return chunk_result.model_copy(
            update={
                "metadata": {
                    **chunk_result.metadata,
                    **self._build_parse_metadata(parsed_document),
                }
            }
        )

    def inspect_source(
        self,
        *,
        tenant_id: str,
        app_id: str,
        source_type: str,
        source_value: str,
        scene: str = "knowledge_ingest",
        file_name: str | None = None,
        file_type: str | None = None,
        provider: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object]:
        if self._document_parse_service is None:
            raise ValueError("DocumentParseService is required for inspect_source().")

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
        asset = self._document_parse_service._file_identity_service.normalize(parse_request)
        parser = self._document_parse_service._parser_router_service.resolve(asset)
        cache_key = self._document_parse_service._parse_cache_service.build_cache_key(
            asset=asset,
            request=parse_request,
            parser_name=parser.parser_name,
            parser_version=parser.parser_version,
        )
        return {
            "asset_hash": asset.asset_hash,
            "file_name": asset.file_name,
            "file_type": asset.file_type,
            "document_parse_cache_key": cache_key,
            "document_parse_parser_name": parser.parser_name,
            "document_parse_parser_version": parser.parser_version,
        }

    def resolve_policy(
        self,
        policy: ChunkingPolicyConfig | None,
    ) -> ChunkingPolicyConfig:
        return resolve_chunking_policy(
            policy,
            settings=getattr(self._chunking_service, "_settings", None),
        )

    @staticmethod
    def _build_parse_metadata(
        parsed_document: DocumentParseResult,
    ) -> dict[str, object]:
        metadata = dict(parsed_document.metadata)
        return {
            "document_parse_cache_hit": parsed_document.cache_hit,
            "document_parse_cache_key": parsed_document.cache_key,
            "document_parse_parser_name": parsed_document.parser_name,
            "document_parse_parser_version": parsed_document.parser_version,
            "document_parse_latency_ms": parsed_document.latency_ms,
            "document_parse_provider": parsed_document.provider,
            "document_parse_model": parsed_document.model,
            "document_parse_page_count": len(parsed_document.pages),
            "document_parse_strategy": metadata.get("strategy"),
            "document_parse_ocr_mode": metadata.get("ocr_mode"),
            "document_parse_ocr_batch_count": metadata.get("ocr_batch_count"),
            "document_parse_ocr_total_pages": metadata.get("ocr_total_pages"),
            "document_parse_ocr_retry_count": metadata.get("ocr_retry_count"),
            "document_parse_ocr_retried_batch_count": metadata.get(
                "ocr_retried_batch_count"
            ),
            "document_parse_ocr_resumed_batch_count": metadata.get(
                "ocr_resumed_batch_count"
            ),
        }


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
