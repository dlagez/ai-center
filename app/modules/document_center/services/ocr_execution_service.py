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

    def extract_text(
        self,
        *,
        request: DocumentParseRequest,
        asset: NormalizedDocumentAsset,
        trace_id: str,
        file_type: str,
    ) -> OCRProviderResponse:
        provider_name = request.provider or self._settings.ocr_default_provider
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
            source_type=request.source_type,
            source_value=request.source_value,
            file_type=file_type,
            provider=provider_name,
            language_hints=list(request.language_hints),
            enable_layout=enable_layout,
            page_range=request.page_range,
            metadata=dict(request.metadata),
        )
        return adapter.extract_text(ocr_request, trace_id=trace_id)
