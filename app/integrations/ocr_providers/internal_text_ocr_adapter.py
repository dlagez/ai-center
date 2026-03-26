from __future__ import annotations

from typing import Any

from app.core.config import OCRSettings
from app.core.exceptions import OCRToolConfigurationError
from app.integrations.ocr_providers.base import BaseOCRProviderAdapter
from app.runtime.tools.schemas import OCRPage, OCRProviderResponse, OCRToolRequest


class InternalTextOCRAdapter(BaseOCRProviderAdapter):
    provider_name = "internal_text_ocr"

    def __init__(self, settings: OCRSettings) -> None:
        self._settings = settings

    def extract_text(
        self,
        request: OCRToolRequest,
        *,
        trace_id: str,
    ) -> OCRProviderResponse:
        if not self._settings.internal_text_ocr_base_url:
            raise OCRToolConfigurationError(
                "Internal text OCR base URL is not configured."
            )

        headers = {
            "Content-Type": "application/json",
            "X-Trace-Id": trace_id,
        }
        if self._settings.internal_text_ocr_api_key:
            headers["Authorization"] = (
                f"Bearer {self._settings.internal_text_ocr_api_key}"
            )

        payload = self._build_text_ocr_payload(request)
        body = self.post_json(
            url=self._settings.internal_text_ocr_base_url,
            headers=headers,
            payload=payload,
            timeout_ms=self._settings.ocr_timeout_ms,
        )
        return self._parse_text_ocr_response(body)

    @staticmethod
    def _build_text_ocr_payload(request: OCRToolRequest) -> dict[str, Any]:
        source_payload = BaseOCRProviderAdapter.build_source_payload(request)
        file_value = source_payload.get("file_url") or source_payload.get("file_base64")
        if not isinstance(file_value, str) or not file_value:
            raise OCRToolConfigurationError(
                "Internal text OCR provider requires a URL or base64 file payload."
            )

        return {
            "file": file_value,
            "fileType": 0 if request.file_type == "pdf" else 1,
            "visualize": False,
            "use_textline_orientation": False,
            "use_doc_unwarping": False,
            "use_doc_orientation_classify": False,
        }

    def _parse_text_ocr_response(
        self,
        body: dict[str, Any],
    ) -> OCRProviderResponse:
        result = body.get("result")
        if not isinstance(result, dict):
            return self.parse_common_response(body, provider=self.provider_name)

        raw_items = result.get("ocrResults")
        if not isinstance(raw_items, list):
            return self.parse_common_response(body, provider=self.provider_name)

        pages: list[OCRPage] = []
        page_texts: list[str] = []
        for index, item in enumerate(raw_items, start=1):
            if not isinstance(item, dict):
                continue
            pruned_result = item.get("prunedResult")
            if not isinstance(pruned_result, dict):
                continue
            rec_texts = pruned_result.get("rec_texts")
            if not isinstance(rec_texts, list):
                continue
            texts = [str(text).strip() for text in rec_texts if str(text).strip()]
            if not texts:
                continue
            page_text = " ".join(texts).strip()
            if not page_text:
                continue
            pages.append(OCRPage(page_no=index, text=page_text))
            page_texts.append(page_text)

        if not page_texts:
            return self.parse_common_response(body, provider=self.provider_name)

        return OCRProviderResponse(
            provider=self.provider_name,
            model=self._settings.internal_text_ocr_model or "paddleocr_v5",
            text="\n\n".join(page_texts),
            pages=pages,
            usage={},
            raw_response=body,
        )
