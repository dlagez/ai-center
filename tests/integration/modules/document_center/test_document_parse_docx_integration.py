from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.core.config import DocumentParseSettings, OCRSettings
from app.modules.document_center import DocumentParseRequest, build_document_parse_service


class DocumentParseDOCXIntegrationTestCase(unittest.TestCase):
    def test_parse_real_docx_and_print_result(self) -> None:
        project_root = Path(__file__).resolve().parents[4]
        docx_path = project_root / "data" / "uploads" / "doc" / "关于清明节机房安全巡检工作部署.docx"
        self.assertTrue(docx_path.exists(), f"Document not found: {docx_path}")

        ocr_settings = OCRSettings(
            ocr_default_provider="internal_ocr",
            ocr_timeout_ms=60000,
            ocr_enable_layout=False,
            aliyun_ocr_base_url=None,
            aliyun_ocr_api_key=None,
            aliyun_ocr_app_code=None,
            internal_ocr_base_url=None,
            internal_ocr_api_key=None,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            parse_settings = DocumentParseSettings(
                document_parse_cache_dir=str(Path(temp_dir) / "cache"),
                document_parse_enable_cache=True,
                document_parse_download_timeout_ms=1000,
            )
            service = build_document_parse_service(
                ocr_settings=ocr_settings,
                document_parse_settings=parse_settings,
            )
            result = service.parse(
                DocumentParseRequest(
                    tenant_id="integration-tenant",
                    app_id="integration-app",
                    scene="integration_test",
                    source_type="file_path",
                    source_value=str(docx_path),
                )
            )

        print("\n=== Document Parse Result ===")
        print(
            json.dumps(
                result.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            )
        )
        print("=== End Document Parse Result ===")

        self.assertEqual(result.file_type, "docx")
        self.assertEqual(result.file_name, "关于清明节机房安全巡检工作部署.docx")
        self.assertGreater(len(result.text.strip()), 0)

# .\.venv\Scripts\python.exe -m unittest tests.integration.modules.document_center.test_document_parse_docx_integration