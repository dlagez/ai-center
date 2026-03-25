from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.config import OCRSettings
from app.integrations.ocr_providers.internal_ocr_adapter import InternalOCRAdapter
from app.runtime.tools.schemas import OCRToolRequest


class InternalOCRAdapterTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = OCRSettings(
            ocr_default_provider="internal_ocr",
            ocr_timeout_ms=60000,
            ocr_enable_layout=False,
            aliyun_ocr_base_url=None,
            aliyun_ocr_api_key=None,
            aliyun_ocr_app_code=None,
            internal_ocr_base_url="https://prod-ocr.hysz.co:1443/layout-parsing",
            internal_ocr_api_key=None,
        )

    def test_extract_text_uses_layout_parsing_contract(self) -> None:
        adapter = InternalOCRAdapter(self.settings)
        provider_body = {
            "result": {
                "layoutParsingResults": [
                    {"markdown": {"text": "first page"}},
                    {"markdown": {"text": "second page"}},
                ]
            }
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "sample.pdf"
            file_path.write_bytes(b"%PDF-fake")
            request = OCRToolRequest(
                tenant_id="tenant-a",
                app_id="app-a",
                scene="knowledge_ingest",
                source_type="file_path",
                source_value=str(file_path),
                file_type="pdf",
            )

            with patch.object(
                InternalOCRAdapter,
                "post_json",
                return_value=provider_body,
            ) as mock_post:
                result = adapter.extract_text(request, trace_id="trace-1")

        self.assertEqual(result.provider, "internal_ocr")
        self.assertEqual(result.model, "paddleocr_vl_layout_parsing")
        self.assertEqual(result.text, "first page\n\nsecond page")
        self.assertEqual(len(result.pages), 2)
        self.assertEqual(result.pages[0].page_no, 1)
        self.assertEqual(result.pages[1].text, "second page")

        call_kwargs = mock_post.call_args.kwargs
        self.assertEqual(
            call_kwargs["url"],
            "https://prod-ocr.hysz.co:1443/layout-parsing",
        )
        self.assertEqual(call_kwargs["payload"]["fileType"], 0)
        self.assertTrue(call_kwargs["payload"]["format_block_content"])
        self.assertTrue(call_kwargs["payload"]["use_seal_recognition"])
        self.assertTrue(call_kwargs["payload"]["use_ocr_for_image_block"])
        self.assertIn("file", call_kwargs["payload"])

    def test_extract_text_uses_image_file_type_for_non_pdf(self) -> None:
        adapter = InternalOCRAdapter(self.settings)
        request = OCRToolRequest(
            tenant_id="tenant-a",
            app_id="app-a",
            scene="agent",
            source_type="base64",
            source_value="ZmFrZS1iYXNlNjQ=",
            file_type="image",
        )

        with patch.object(
            InternalOCRAdapter,
            "post_json",
            return_value={"result": {"layoutParsingResults": [{"markdown": {"text": "image text"}}]}},
        ) as mock_post:
            result = adapter.extract_text(request, trace_id="trace-2")

        self.assertEqual(result.text, "image text")
        self.assertEqual(mock_post.call_args.kwargs["payload"]["fileType"], 1)


if __name__ == "__main__":
    unittest.main()
