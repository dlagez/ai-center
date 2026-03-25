from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.config import OCRSettings
from app.core.exceptions import OCRToolConfigurationError, OCRToolUnsupportedFileTypeError
from app.integrations.ocr_providers.base import BaseOCRProviderAdapter
from app.modules.agent_center.services import AgentToolService
from app.modules.knowledge_center.services import DocumentOCRService
from app.runtime.tools import (
    OCRPage,
    OCRProviderResponse,
    OCRTool,
    OCRToolRequest,
    ToolExecutor,
    ToolRegistry,
)


class FakeOCRAdapter(BaseOCRProviderAdapter):
    provider_name = "fake_ocr"

    def __init__(self, response: OCRProviderResponse) -> None:
        self.response = response
        self.last_request: OCRToolRequest | None = None

    def extract_text(self, request: OCRToolRequest, *, trace_id: str) -> OCRProviderResponse:
        self.last_request = request
        return self.response


class OCRToolTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = OCRSettings(
            ocr_default_provider="fake_ocr",
            ocr_timeout_ms=60000,
            ocr_enable_layout=False,
            aliyun_ocr_base_url=None,
            aliyun_ocr_api_key=None,
            aliyun_ocr_app_code=None,
            internal_ocr_base_url=None,
            internal_ocr_api_key=None,
        )
        self.adapter = FakeOCRAdapter(
            OCRProviderResponse(
                provider="fake_ocr",
                model="ocr-v1",
                text="line one\nline two",
                pages=[OCRPage(page_no=1, text="line one\nline two")],
            )
        )
        self.tool = OCRTool(settings=self.settings, adapters={"fake_ocr": self.adapter})

    def test_ocr_tool_executes_with_default_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "sample.png"
            file_path.write_bytes(b"fake-image-content")

            result = self.tool.execute(
                OCRToolRequest(
                    tenant_id="tenant-a",
                    app_id="app-a",
                    scene="knowledge_ingest",
                    source_type="file_path",
                    source_value=str(file_path),
                )
            )

        self.assertEqual(result.provider, "fake_ocr")
        self.assertEqual(result.model, "ocr-v1")
        self.assertEqual(result.text, "line one\nline two")
        self.assertEqual(len(result.pages), 1)
        self.assertIsNotNone(self.adapter.last_request)
        self.assertEqual(self.adapter.last_request.file_type, "image")
        self.assertFalse(self.adapter.last_request.enable_layout)

    def test_ocr_tool_rejects_unsupported_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "sample.docx"
            file_path.write_bytes(b"not-supported")

            with self.assertRaises(OCRToolUnsupportedFileTypeError):
                self.tool.execute(
                    OCRToolRequest(
                        tenant_id="tenant-a",
                        app_id="app-a",
                        scene="knowledge_ingest",
                        source_type="file_path",
                        source_value=str(file_path),
                    )
                )

    def test_registry_and_executor_support_dict_payloads(self) -> None:
        registry = ToolRegistry()
        registry.register(self.tool)
        executor = ToolExecutor(registry)

        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "sample.png"
            file_path.write_bytes(b"fake-image-content")

            result = executor.execute(
                OCRTool.name,
                {
                    "tenant_id": "tenant-a",
                    "app_id": "app-a",
                    "scene": "agent",
                    "source_type": "file_path",
                    "source_value": str(file_path),
                },
            )

        self.assertEqual(result.provider, "fake_ocr")
        self.assertEqual(len(executor.list_tool_specs()), 1)

    def test_registry_rejects_duplicate_names(self) -> None:
        registry = ToolRegistry()
        registry.register(self.tool)
        with self.assertRaises(OCRToolConfigurationError):
            registry.register(self.tool)

    def test_knowledge_and_agent_services_reuse_executor(self) -> None:
        registry = ToolRegistry([self.tool])
        executor = ToolExecutor(registry)
        knowledge_service = DocumentOCRService(executor)
        agent_service = AgentToolService(executor)

        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "sample.pdf"
            file_path.write_bytes(b"%PDF-fake")

            text = knowledge_service.extract_text_for_ingest(
                tenant_id="tenant-a",
                app_id="app-a",
                source_type="file_path",
                source_value=str(file_path),
            )
            result = agent_service.execute_tool(
                OCRTool.name,
                {
                    "tenant_id": "tenant-a",
                    "app_id": "app-a",
                    "scene": "agent",
                    "source_type": "file_path",
                    "source_value": str(file_path),
                },
            )

        self.assertEqual(text, "line one\nline two")
        self.assertEqual(result.provider, "fake_ocr")
        self.assertEqual(len(agent_service.list_tool_specs()), 1)
