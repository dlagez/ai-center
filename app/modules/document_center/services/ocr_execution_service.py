from __future__ import annotations

from app.core.config import OCRSettings
from app.core.exceptions import OCRToolConfigurationError
from app.integrations.ocr_providers.base import BaseOCRProviderAdapter
from app.modules.document_center.schemas import DocumentParseRequest, NormalizedDocumentAsset
from app.runtime.tools.schemas import OCRProviderResponse, OCRToolRequest


class OCRExecutionService:
    def __init__(
        self,
        *,
        settings: OCRSettings,
        adapters: dict[str, BaseOCRProviderAdapter],
    ) -> None:
        self._settings = settings
        self._adapters = adapters

    def supports_pdf_page_range(self, provider_name: str | None = None) -> bool:
        resolved_provider_name = provider_name or self._settings.ocr_default_provider
        adapter = self._adapters.get(resolved_provider_name)
        if adapter is None:
            return False
        return bool(getattr(adapter, "supports_pdf_page_range", False))

    def resolve_provider_name(self, request: DocumentParseRequest) -> str:
        if request.provider:
            return request.provider

        if request.enable_layout is True or request.parse_mode == "structured":
            return (
                self._settings.ocr_default_layout_provider
                or self._settings.ocr_default_provider
            )

        if request.parse_mode in {"text", "preview"}:
            return (
                self._settings.ocr_default_text_provider
                or self._settings.ocr_default_provider
            )

        return self._settings.ocr_default_provider

    def extract_text(
        self,
        *,
        request: DocumentParseRequest,
        asset: NormalizedDocumentAsset,
        trace_id: str,
        file_type: str,
    ) -> OCRProviderResponse:
        provider_name = self.resolve_provider_name(request)
        adapter = self._adapters.get(provider_name)
        if adapter is None:
            raise OCRToolConfigurationError(
                f"OCR provider '{provider_name}' is not configured."
            )

        enable_layout = (
            request.enable_layout
            if request.enable_layout is not None
            else self._settings.ocr_enable_layout
        )
        ocr_request = OCRToolRequest(
            tenant_id=request.tenant_id,
            app_id=request.app_id,
            scene=request.scene,
            source_type=asset.source_type,
            source_value=asset.source_value,
            file_type=file_type,
            provider=provider_name,
            language_hints=list(request.language_hints),
            enable_layout=enable_layout,
            page_range=request.page_range,
            metadata=dict(request.metadata),
        )
        return adapter.extract_text(ocr_request, trace_id=trace_id)
