from __future__ import annotations

from typing import Any

from app.core.config import OCRSettings
from app.core.exceptions import OCRToolConfigurationError
from app.integrations.ocr_providers.base import BaseOCRProviderAdapter
from app.runtime.tools.schemas import OCRPage, OCRProviderResponse, OCRToolRequest


class InternalOCRAdapter(BaseOCRProviderAdapter):
    provider_name = "internal_ocr"

    def __init__(self, settings: OCRSettings) -> None:
        self._settings = settings

    def extract_text(
        self,
        request: OCRToolRequest,
        *,
        trace_id: str,
    ) -> OCRProviderResponse:
        if not self._settings.internal_ocr_base_url:
            raise OCRToolConfigurationError(
                "Internal OCR base URL is not configured."
            )

        headers = {
            "Content-Type": "application/json",
            "X-Trace-Id": trace_id,
        }
        if self._settings.internal_ocr_api_key:
            headers["Authorization"] = f"Bearer {self._settings.internal_ocr_api_key}"

        payload = self._build_layout_parsing_payload(request)
        body = self.post_json(
            url=self._settings.internal_ocr_base_url,
            headers=headers,
            payload=payload,
            timeout_ms=self._settings.ocr_timeout_ms,
        )
        return self._parse_layout_parsing_response(body)

    @staticmethod
    def _build_layout_parsing_payload(request: OCRToolRequest) -> dict[str, Any]:
        source_payload = BaseOCRProviderAdapter.build_source_payload(request)
        file_value = source_payload.get("file_url") or source_payload.get("file_base64")
        if not isinstance(file_value, str) or not file_value:
            raise OCRToolConfigurationError(
                "Internal OCR provider requires a URL or base64 file payload."
            )

        payload = {
            "file": file_value,
            "fileType": 0 if request.file_type == "pdf" else 1,
            "format_block_content": True,
            "use_seal_recognition": True,
            "use_ocr_for_image_block": True,
        }
        if request.page_range:
            payload["pageRange"] = list(request.page_range)
        return payload

    def _parse_layout_parsing_response(
        self,
        body: dict[str, Any],
    ) -> OCRProviderResponse:
        result = body.get("result")
        if not isinstance(result, dict):
            return self.parse_common_response(body, provider=self.provider_name)

        raw_items = result.get("layoutParsingResults")
        if not isinstance(raw_items, list):
            return self.parse_common_response(body, provider=self.provider_name)

        pages: list[OCRPage] = []
        text_parts: list[str] = []
        for index, item in enumerate(raw_items, start=1):
            if not isinstance(item, dict):
                continue
            markdown = item.get("markdown")
            if not isinstance(markdown, dict):
                continue
            text = markdown.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            normalized_text = text.strip()
            text_parts.append(normalized_text)
            pages.append(OCRPage(page_no=index, text=normalized_text))

        if not text_parts:
            return self.parse_common_response(body, provider=self.provider_name)

        return OCRProviderResponse(
            provider=self.provider_name,
            model="paddleocr_vl_layout_parsing",
            text="\n\n".join(text_parts),
            pages=pages,
            usage={},
            raw_response=body,
        )
