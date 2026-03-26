from __future__ import annotations

import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from app.core.config import OCRSettings
from app.core.exceptions import (
    OCRToolConfigurationError,
    OCRToolUnsupportedFileTypeError,
    OCRToolValidationError,
)
from app.integrations.ocr_providers.aliyun_ocr_adapter import AliyunOCRAdapter
from app.integrations.ocr_providers.base import BaseOCRProviderAdapter
from app.integrations.ocr_providers.internal_ocr_adapter import InternalOCRAdapter
from app.integrations.ocr_providers.internal_text_ocr_adapter import (
    InternalTextOCRAdapter,
)
from app.modules.document_center.schemas import DocumentParseRequest
from app.modules.document_center.services import (
    DocumentParseService,
    build_document_parse_service,
)
from app.runtime.tools.base import BaseRuntimeTool
from app.runtime.tools.document_parse_tool import DocumentParseTool
from app.runtime.tools.executor import ToolExecutor
from app.runtime.tools.registry import ToolRegistry
from app.runtime.tools.schemas import OCRProviderResponse, OCRToolRequest, OCRToolResult

SUPPORTED_IMAGE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}
SUPPORTED_PDF_SUFFIXES = {".pdf"}


class OCRTool(BaseRuntimeTool):
    name = "ocr_extract_text"
    description = "Extract text content from image or PDF sources."
    request_model = OCRToolRequest
    result_model = OCRToolResult

    def __init__(
        self,
        *,
        settings: OCRSettings,
        adapters: dict[str, BaseOCRProviderAdapter],
        document_parse_service: DocumentParseService | None = None,
    ) -> None:
        self._settings = settings
        self._adapters = adapters
        self._document_parse_service = document_parse_service

    def execute(self, request: OCRToolRequest) -> OCRToolResult:
        normalized_request = self._normalize_request(request)
        if self._document_parse_service is not None:
            return self._execute_with_document_parse(normalized_request)

        return self._execute_with_provider(normalized_request)

    def _execute_with_provider(self, request: OCRToolRequest) -> OCRToolResult:
        provider_name = request.provider or self._settings.ocr_default_provider
        adapter = self._adapters.get(provider_name)
        if adapter is None:
            raise OCRToolConfigurationError(
                f"OCR provider '{provider_name}' is not configured."
            )

        trace_id = uuid.uuid4().hex
        start_time = time.perf_counter()
        response = adapter.extract_text(request, trace_id=trace_id)
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        return self._build_result(
            trace_id=trace_id,
            request=request,
            response=response,
            latency_ms=latency_ms,
        )

    def _execute_with_document_parse(self, request: OCRToolRequest) -> OCRToolResult:
        parse_request = DocumentParseRequest(
            tenant_id=request.tenant_id,
            app_id=request.app_id,
            scene=request.scene,
            source_type=request.source_type,
            source_value=request.source_value,
            file_type=request.file_type,
            provider=request.provider,
            language_hints=list(request.language_hints),
            enable_layout=request.enable_layout,
            page_range=request.page_range,
            metadata=dict(request.metadata),
        )
        result = self._document_parse_service.parse(parse_request)
        usage = result.metadata.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        return OCRToolResult(
            trace_id=result.trace_id,
            provider=result.provider or result.parser_name,
            model=result.model,
            source_type=result.source_type,
            source_value=result.source_value,
            text=result.text,
            pages=result.pages,
            usage=usage,
            latency_ms=result.latency_ms,
            raw_response=result.raw_response,
        )

    def _normalize_request(self, request: OCRToolRequest) -> OCRToolRequest:
        if request.source_type == "file_path":
            path = Path(request.source_value)
            if not path.exists():
                raise OCRToolValidationError(
                    f"File '{request.source_value}' does not exist."
                )
            if not path.is_file():
                raise OCRToolValidationError(
                    f"Source '{request.source_value}' is not a file."
                )
        elif request.source_type == "url":
            parsed = urlparse(request.source_value)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise OCRToolValidationError(
                    "OCR URL sources must use an absolute http or https URL."
                )
        elif request.source_type == "base64" and not request.source_value.strip():
            raise OCRToolValidationError("Base64 OCR input must not be empty.")

        file_type = request.file_type or self._infer_file_type(request)
        enable_layout = (
            request.enable_layout
            if request.enable_layout is not None
            else self._settings.ocr_enable_layout
        )
        return request.model_copy(update={"file_type": file_type, "enable_layout": enable_layout})

    def _infer_file_type(self, request: OCRToolRequest) -> str:
        if request.source_type == "base64":
            return "image"

        source_value = request.source_value
        if request.source_type == "url":
            source_value = urlparse(source_value).path

        suffix = Path(source_value).suffix.lower()
        if suffix in SUPPORTED_IMAGE_SUFFIXES:
            return "image"
        if suffix in SUPPORTED_PDF_SUFFIXES:
            return "pdf"
        raise OCRToolUnsupportedFileTypeError(
            f"Unsupported OCR file type for source '{request.source_value}'."
        )

    @staticmethod
    def _build_result(
        *,
        trace_id: str,
        request: OCRToolRequest,
        response: OCRProviderResponse,
        latency_ms: int,
    ) -> OCRToolResult:
        return OCRToolResult(
            trace_id=trace_id,
            provider=response.provider,
            model=response.model,
            source_type=request.source_type,
            source_value=request.source_value,
            text=response.text,
            pages=response.pages,
            usage=response.usage,
            latency_ms=latency_ms,
            raw_response=response.raw_response,
        )


def build_default_ocr_adapters(
    settings: OCRSettings | None = None,
    *,
    overrides: dict[str, BaseOCRProviderAdapter] | None = None,
) -> dict[str, BaseOCRProviderAdapter]:
    settings = settings or OCRSettings.from_env()
    adapters = dict(overrides or {})

    if settings.aliyun_ocr_base_url and "aliyun_ocr" not in adapters:
        adapters["aliyun_ocr"] = AliyunOCRAdapter(settings)
    if settings.internal_ocr_base_url and "internal_ocr" not in adapters:
        adapters["internal_ocr"] = InternalOCRAdapter(settings)
    if (
        settings.internal_text_ocr_base_url
        and "internal_text_ocr" not in adapters
    ):
        adapters["internal_text_ocr"] = InternalTextOCRAdapter(settings)
    return adapters


def build_default_tool_registry(
    settings: OCRSettings | None = None,
    *,
    adapters: dict[str, BaseOCRProviderAdapter] | None = None,
    registry: ToolRegistry | None = None,
) -> ToolRegistry:
    settings = settings or OCRSettings.from_env()
    registry = registry or ToolRegistry()
    adapters = adapters or build_default_ocr_adapters(settings)
    document_parse_service = build_document_parse_service(
        ocr_settings=settings,
        adapters=adapters,
    )
    if not registry.has(DocumentParseTool.name):
        registry.register(DocumentParseTool(document_parse_service))
    if not registry.has(OCRTool.name):
        registry.register(
            OCRTool(
                settings=settings,
                adapters=adapters,
                document_parse_service=document_parse_service,
            )
        )
    return registry


def build_default_tool_executor(
    settings: OCRSettings | None = None,
    *,
    adapters: dict[str, BaseOCRProviderAdapter] | None = None,
    registry: ToolRegistry | None = None,
) -> ToolExecutor:
    registry = build_default_tool_registry(
        settings=settings,
        adapters=adapters,
        registry=registry,
    )
    return ToolExecutor(registry)
