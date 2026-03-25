from __future__ import annotations

from app.core.config import OCRSettings
from app.core.exceptions import OCRToolConfigurationError
from app.integrations.ocr_providers.base import BaseOCRProviderAdapter
from app.runtime.tools.schemas import OCRProviderResponse, OCRToolRequest


class AliyunOCRAdapter(BaseOCRProviderAdapter):
    provider_name = "aliyun_ocr"

    def __init__(self, settings: OCRSettings) -> None:
        self._settings = settings

    def extract_text(
        self,
        request: OCRToolRequest,
        *,
        trace_id: str,
    ) -> OCRProviderResponse:
        if not self._settings.aliyun_ocr_base_url:
            raise OCRToolConfigurationError(
                "Aliyun OCR base URL is not configured."
            )
        if not self._settings.aliyun_ocr_api_key and not self._settings.aliyun_ocr_app_code:
            raise OCRToolConfigurationError(
                "Aliyun OCR authentication is not configured."
            )

        headers = {
            "Content-Type": "application/json",
            "X-Trace-Id": trace_id,
        }
        if self._settings.aliyun_ocr_api_key:
            headers["Authorization"] = f"Bearer {self._settings.aliyun_ocr_api_key}"
        elif self._settings.aliyun_ocr_app_code:
            headers["Authorization"] = f"APPCODE {self._settings.aliyun_ocr_app_code}"

        payload = self.build_source_payload(request)
        payload["provider"] = self.provider_name
        body = self.post_json(
            url=self._settings.aliyun_ocr_base_url,
            headers=headers,
            payload=payload,
            timeout_ms=self._settings.ocr_timeout_ms,
        )
        return self.parse_common_response(body, provider=self.provider_name)
