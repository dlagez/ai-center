from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.config import DocumentParseSettings, OCRSettings
from app.integrations.ocr_providers.base import BaseOCRProviderAdapter
from app.modules.document_center import DocumentParseRequest
from app.modules.document_center.repositories import ParseCacheRepository
from app.modules.document_center.services import build_document_parse_service
from app.runtime.tools.document_parse_tool import DocumentParseTool
from app.runtime.tools.executor import ToolExecutor
from app.runtime.tools.registry import ToolRegistry
from app.runtime.tools.schemas import OCRProviderResponse, OCRToolRequest


class FakeOCRAdapter(BaseOCRProviderAdapter):
    provider_name = "fake_ocr"

    def extract_text(self, request: OCRToolRequest, *, trace_id: str) -> OCRProviderResponse:
        return OCRProviderResponse(provider="fake_ocr", text="ocr text")


class DocumentParseToolTestCase(unittest.TestCase):
    def test_document_parse_tool_executes_through_executor(self) -> None:
        ocr_settings = OCRSettings(
            ocr_default_provider="fake_ocr",
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
            repository = ParseCacheRepository(parse_settings.document_parse_cache_dir)
            service = build_document_parse_service(
                ocr_settings=ocr_settings,
                document_parse_settings=parse_settings,
                adapters={"fake_ocr": FakeOCRAdapter()},
                repository=repository,
            )
            text_path = Path(temp_dir) / "sample.md"
            text_path.write_text("# title", encoding="utf-8")

            registry = ToolRegistry([DocumentParseTool(service)])
            executor = ToolExecutor(registry)
            result = executor.execute(
                DocumentParseTool.name,
                DocumentParseRequest(
                    tenant_id="tenant-a",
                    app_id="app-a",
                    scene="agent",
                    source_type="file_path",
                    source_value=str(text_path),
                ),
            )

        self.assertEqual(result.text, "# title")
        self.assertEqual(result.file_type, "md")
