from __future__ import annotations

import sys
import unittest
from pathlib import Path

from app.core.config import OCRSettings
from app.runtime.tools import OCRTool, build_default_tool_executor


class OCRToolInternalIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.project_root = Path(__file__).resolve().parents[4]
        cls.image_path = (
            cls.project_root
            / "data"
            / "uploads"
            / "img"
            / "PixPin_2026-03-25_15-44-54.jpg"
        )
        cls.settings = OCRSettings.from_env()

    def setUp(self) -> None:
        if not self.settings.internal_ocr_base_url:
            self.skipTest("INTERNAL_OCR_BASE_URL is not configured.")
        if not self.image_path.exists():
            self.skipTest(f"OCR test image does not exist: {self.image_path}")
        self.executor = build_default_tool_executor(self.settings)

    def test_tool_specs_include_ocr_extract_text(self) -> None:
        tool_specs = self.executor.list_tool_specs()
        tool_names = {
            spec.get("function", {}).get("name")
            for spec in tool_specs
            if isinstance(spec, dict)
        }
        self.assertIn(OCRTool.name, tool_names)

    def test_execute_ocr_tool_with_local_image(self) -> None:
        result = self.executor.execute(
            OCRTool.name,
            {
                "tenant_id": "integration-tenant",
                "app_id": "integration-app",
                "scene": "ocr_tool_integration",
                "source_type": "file_path",
                "source_value": str(self.image_path),
                "provider": "internal_ocr",
            },
        )
        sys.stdout.buffer.write(b"\nOCR_TEXT_START\n")
        sys.stdout.buffer.write(result.text.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\nOCR_TEXT_END\n")
        sys.stdout.flush()

        self.assertEqual(result.provider, "internal_ocr")
        self.assertEqual(result.model, "paddleocr_vl_layout_parsing")
        self.assertTrue(result.text.strip())
        self.assertGreater(len(result.pages), 0)

        expected_keywords = ("LangChain", "LangGraph", "LangSmith")
        matched_keywords = [word for word in expected_keywords if word in result.text]
        self.assertGreaterEqual(
            len(matched_keywords),
            2,
            f"OCR result did not contain enough expected keywords: {matched_keywords}",
        )


if __name__ == "__main__":
    unittest.main()

# python -m unittest tests.integration.runtime.tools.test_ocr_tool_internal_integration
