from __future__ import annotations

import unittest

from app.core.config import OCRSettings
from app.integrations.ocr_providers.base import BaseOCRProviderAdapter
from app.modules.document_center.schemas import DocumentParseRequest, NormalizedDocumentAsset
from app.modules.document_center.services.ocr_execution_service import OCRExecutionService
from app.runtime.tools.schemas import OCRProviderResponse, OCRToolRequest


class FakeAdapter(BaseOCRProviderAdapter):
    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name
        self.calls = 0

    def extract_text(
        self,
        request: OCRToolRequest,
        *,
        trace_id: str,
    ) -> OCRProviderResponse:
        del request, trace_id
        self.calls += 1
        return OCRProviderResponse(
            provider=self.provider_name,
            model=f"{self.provider_name}-model",
            text=f"{self.provider_name} text",
        )


class OCRExecutionServiceRoutingTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.layout_adapter = FakeAdapter("internal_ocr")
        self.text_adapter = FakeAdapter("internal_text_ocr")
        self.default_adapter = FakeAdapter("aliyun_ocr")
        self.service = OCRExecutionService(
            settings=OCRSettings(
                ocr_default_provider="aliyun_ocr",
                ocr_timeout_ms=60000,
                ocr_enable_layout=False,
                aliyun_ocr_base_url=None,
                aliyun_ocr_api_key=None,
                aliyun_ocr_app_code=None,
                internal_ocr_base_url=None,
                internal_ocr_api_key=None,
                internal_text_ocr_base_url=None,
                internal_text_ocr_api_key=None,
                internal_text_ocr_model="paddleocr_v5",
                ocr_default_layout_provider="internal_ocr",
                ocr_default_text_provider="internal_text_ocr",
            ),
            adapters={
                "aliyun_ocr": self.default_adapter,
                "internal_ocr": self.layout_adapter,
                "internal_text_ocr": self.text_adapter,
            },
        )
        self.asset = NormalizedDocumentAsset(
            source_type="base64",
            source_value="ZmFrZQ==",
            file_name="sample.pdf",
            file_type="pdf",
            content_bytes=b"fake",
            asset_hash="hash-1",
        )

    def test_explicit_provider_takes_priority(self) -> None:
        response = self.service.extract_text(
            request=DocumentParseRequest(
                tenant_id="tenant-a",
                app_id="app-a",
                scene="knowledge_ingest",
                source_type="file_path",
                source_value=r"D:\fake\sample.pdf",
                provider="internal_ocr",
                parse_mode="text",
            ),
            asset=self.asset,
            trace_id="trace-1",
            file_type="pdf",
        )

        self.assertEqual(response.provider, "internal_ocr")
        self.assertEqual(self.layout_adapter.calls, 1)
        self.assertEqual(self.text_adapter.calls, 0)

    def test_text_mode_routes_to_text_provider(self) -> None:
        response = self.service.extract_text(
            request=DocumentParseRequest(
                tenant_id="tenant-a",
                app_id="app-a",
                scene="knowledge_ingest",
                source_type="file_path",
                source_value=r"D:\fake\sample.pdf",
                parse_mode="text",
            ),
            asset=self.asset,
            trace_id="trace-2",
            file_type="pdf",
        )

        self.assertEqual(response.provider, "internal_text_ocr")
        self.assertEqual(self.text_adapter.calls, 1)

    def test_preview_mode_routes_to_text_provider(self) -> None:
        response = self.service.extract_text(
            request=DocumentParseRequest(
                tenant_id="tenant-a",
                app_id="app-a",
                scene="knowledge_ingest",
                source_type="file_path",
                source_value=r"D:\fake\sample.pdf",
                parse_mode="preview",
            ),
            asset=self.asset,
            trace_id="trace-3",
            file_type="pdf",
        )

        self.assertEqual(response.provider, "internal_text_ocr")
        self.assertEqual(self.text_adapter.calls, 1)

    def test_structured_mode_routes_to_layout_provider(self) -> None:
        response = self.service.extract_text(
            request=DocumentParseRequest(
                tenant_id="tenant-a",
                app_id="app-a",
                scene="knowledge_ingest",
                source_type="file_path",
                source_value=r"D:\fake\sample.pdf",
                parse_mode="structured",
            ),
            asset=self.asset,
            trace_id="trace-4",
            file_type="pdf",
        )

        self.assertEqual(response.provider, "internal_ocr")
        self.assertEqual(self.layout_adapter.calls, 1)

    def test_enable_layout_true_routes_to_layout_provider(self) -> None:
        response = self.service.extract_text(
            request=DocumentParseRequest(
                tenant_id="tenant-a",
                app_id="app-a",
                scene="knowledge_ingest",
                source_type="file_path",
                source_value=r"D:\fake\sample.pdf",
                parse_mode="text",
                enable_layout=True,
            ),
            asset=self.asset,
            trace_id="trace-5",
            file_type="pdf",
        )

        self.assertEqual(response.provider, "internal_ocr")
        self.assertEqual(self.layout_adapter.calls, 1)

    def test_falls_back_to_global_default_when_text_provider_not_configured(self) -> None:
        service = OCRExecutionService(
            settings=OCRSettings(
                ocr_default_provider="aliyun_ocr",
                ocr_timeout_ms=60000,
                ocr_enable_layout=False,
                aliyun_ocr_base_url=None,
                aliyun_ocr_api_key=None,
                aliyun_ocr_app_code=None,
                internal_ocr_base_url=None,
                internal_ocr_api_key=None,
                internal_text_ocr_base_url=None,
                internal_text_ocr_api_key=None,
                internal_text_ocr_model="paddleocr_v5",
                ocr_default_layout_provider=None,
                ocr_default_text_provider=None,
            ),
            adapters={
                "aliyun_ocr": self.default_adapter,
            },
        )

        response = service.extract_text(
            request=DocumentParseRequest(
                tenant_id="tenant-a",
                app_id="app-a",
                scene="knowledge_ingest",
                source_type="file_path",
                source_value=r"D:\fake\sample.pdf",
                parse_mode="text",
            ),
            asset=self.asset,
            trace_id="trace-6",
            file_type="pdf",
        )

        self.assertEqual(response.provider, "aliyun_ocr")


if __name__ == "__main__":
    unittest.main()
