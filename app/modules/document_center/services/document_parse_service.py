from __future__ import annotations

import time
import uuid

from app.core.config import DocumentParseSettings, OCRSettings
from app.integrations.ocr_providers.base import BaseOCRProviderAdapter
from app.modules.document_center.parsers import (
    CSVDocumentParser,
    DOCXDocumentParser,
    HTMLDocumentParser,
    ImageDocumentParser,
    PDFDocumentParser,
    PPTXDocumentParser,
    TextDocumentParser,
    XLSXDocumentParser,
)
from app.modules.document_center.repositories import ParseCacheRepository
from app.modules.document_center.schemas import DocumentParseRequest, DocumentParseResult
from app.modules.document_center.services.file_identity_service import FileIdentityService
from app.modules.document_center.services.ocr_execution_service import OCRExecutionService
from app.modules.document_center.services.parse_cache_service import ParseCacheService
from app.modules.document_center.services.pdf_ocr_batching_service import (
    PDFOCRBatchingService,
)
from app.modules.document_center.services.parser_router_service import ParserRouterService


class DocumentParseService:
    def __init__(
        self,
        *,
        file_identity_service: FileIdentityService,
        parse_cache_service: ParseCacheService,
        parser_router_service: ParserRouterService,
    ) -> None:
        self._file_identity_service = file_identity_service
        self._parse_cache_service = parse_cache_service
        self._parser_router_service = parser_router_service

    def parse(self, request: DocumentParseRequest) -> DocumentParseResult:
        asset = self._file_identity_service.normalize(request)
        parser = self._parser_router_service.resolve(asset)
        cache_key = self._parse_cache_service.build_cache_key(
            asset=asset,
            request=request,
            parser_name=parser.parser_name,
            parser_version=parser.parser_version,
        )

        start_time = time.perf_counter()
        cached = self._parse_cache_service.get(cache_key)
        if cached is not None:
            return cached.model_copy(
                update={
                    "cache_hit": True,
                    "latency_ms": int((time.perf_counter() - start_time) * 1000),
                }
            )

        with self._parse_cache_service.acquire(cache_key):
            cached = self._parse_cache_service.get(cache_key)
            if cached is not None:
                return cached.model_copy(
                    update={
                        "cache_hit": True,
                        "latency_ms": int((time.perf_counter() - start_time) * 1000),
                    }
                )

            trace_id = uuid.uuid4().hex
            parsed = parser.parse(request, asset, trace_id=trace_id)
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            result = parsed.model_copy(
                update={
                    "trace_id": trace_id,
                    "cache_key": cache_key,
                    "cache_hit": False,
                    "latency_ms": latency_ms,
                }
            )
            self._parse_cache_service.save(cache_key, result)
            return result


def build_document_parse_service(
    ocr_settings: OCRSettings | None = None,
    document_parse_settings: DocumentParseSettings | None = None,
    *,
    adapters: dict[str, BaseOCRProviderAdapter] | None = None,
    repository: ParseCacheRepository | None = None,
) -> DocumentParseService:
    from app.runtime.tools.ocr_tool import build_default_ocr_adapters

    ocr_settings = ocr_settings or OCRSettings.from_env()
    document_parse_settings = document_parse_settings or DocumentParseSettings.from_env()
    adapters = adapters or build_default_ocr_adapters(ocr_settings)
    repository = repository or ParseCacheRepository(
        document_parse_settings.document_parse_cache_dir
    )

    file_identity_service = FileIdentityService(document_parse_settings)
    parse_cache_service = ParseCacheService(
        repository,
        settings=document_parse_settings,
    )
    ocr_service = OCRExecutionService(settings=ocr_settings, adapters=adapters)
    pdf_ocr_batching_service = PDFOCRBatchingService(ocr_settings)
    parser_router_service = ParserRouterService(
        [
            PDFDocumentParser(
                ocr_service,
                pdf_ocr_batching_service=pdf_ocr_batching_service,
            ),
            ImageDocumentParser(ocr_service),
            DOCXDocumentParser(),
            XLSXDocumentParser(),
            PPTXDocumentParser(),
            CSVDocumentParser(),
            HTMLDocumentParser(),
            TextDocumentParser(),
        ]
    )
    return DocumentParseService(
        file_identity_service=file_identity_service,
        parse_cache_service=parse_cache_service,
        parser_router_service=parser_router_service,
    )
