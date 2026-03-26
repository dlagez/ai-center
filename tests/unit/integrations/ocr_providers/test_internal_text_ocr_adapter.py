from __future__ import annotations

import unittest
from unittest.mock import patch

from app.core.config import OCRSettings
from app.integrations.ocr_providers.internal_text_ocr_adapter import (
    InternalTextOCRAdapter,
)
from app.runtime.tools.schemas import OCRToolRequest


class InternalTextOCRAdapterTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = OCRSettings(
            ocr_default_provider="internal_text_ocr",
            ocr_timeout_ms=60000,
            ocr_enable_layout=False,
            aliyun_ocr_base_url=None,
            aliyun_ocr_api_key=None,
            aliyun_ocr_app_code=None,
            internal_ocr_base_url=None,
            internal_ocr_api_key=None,
            internal_text_ocr_base_url="https://prod-ocr.hysz.co:9443/ocr",
            internal_text_ocr_api_key="secret-key",
            internal_text_ocr_model="paddleocr_v5",
        )

    def test_extract_text_uses_text_ocr_contract(self) -> None:
        adapter = InternalTextOCRAdapter(self.settings)
        provider_body = {
            "result": {
                "ocrResults": [
                    {"prunedResult": {"rec_texts": ["first", "page"]}},
                    {"prunedResult": {"rec_texts": ["second", "page"]}},
                ]
            }
        }
        request = OCRToolRequest(
            tenant_id="tenant-a",
            app_id="app-a",
            scene="knowledge_ingest",
            source_type="base64",
            source_value="ZmFrZS1wZGY=",
            file_type="pdf",
        )

        with patch.object(
            InternalTextOCRAdapter,
            "post_json",
            return_value=provider_body,
        ) as mock_post:
            result = adapter.extract_text(request, trace_id="trace-1")

        self.assertEqual(result.provider, "internal_text_ocr")
        self.assertEqual(result.model, "paddleocr_v5")
        self.assertEqual(result.text, "first page\n\nsecond page")
        self.assertEqual([page.page_no for page in result.pages], [1, 2])
        self.assertEqual(result.pages[0].text, "first page")
        self.assertEqual(result.pages[1].text, "second page")

        call_kwargs = mock_post.call_args.kwargs
        self.assertEqual(call_kwargs["url"], "https://prod-ocr.hysz.co:9443/ocr")
        self.assertEqual(
            call_kwargs["headers"]["Authorization"],
            "Bearer secret-key",
        )
        self.assertEqual(call_kwargs["payload"]["fileType"], 0)
        self.assertFalse(call_kwargs["payload"]["visualize"])
        self.assertFalse(call_kwargs["payload"]["use_textline_orientation"])
        self.assertFalse(call_kwargs["payload"]["use_doc_unwarping"])
        self.assertFalse(call_kwargs["payload"]["use_doc_orientation_classify"])
        self.assertEqual(call_kwargs["payload"]["file"], "ZmFrZS1wZGY=")


if __name__ == "__main__":
    unittest.main()
