from __future__ import annotations

import unittest
from contextlib import contextmanager
from io import BytesIO
from tempfile import TemporaryDirectory

from pypdf import PdfWriter

from app.core.config import OCRSettings
from app.modules.document_center.repositories.pdf_ocr_checkpoint_repository import (
    PDFOCRCheckpointRepository,
)
from app.modules.document_center.schemas import DocumentParseRequest, NormalizedDocumentAsset
from app.modules.document_center.services.ocr_execution_service import OCRExecutionService
from app.modules.document_center.services.pdf_batch_asset_service import (
    PDFBatchAssetService,
)
from app.modules.document_center.services.pdf_ocr_batching_service import (
    PDFOCRBatchingService,
)
from app.observability.tracing import LangSmithTracer
from app.runtime.tools.schemas import OCRPage, OCRProviderResponse


class FakeClient:
    def flush(self) -> None:
        return None


class FakeRun:
    def __init__(self, metadata: dict) -> None:
        self.metadata = dict(metadata)
        self.outputs: dict = {}

    def end(self, *, outputs=None, error=None) -> None:
        if outputs:
            self.outputs.update(outputs)
        if error is not None:
            self.metadata["error"] = str(error)


class FakeTraceFactory:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.runs: list[FakeRun] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)

        @contextmanager
        def manager():
            run = FakeRun(kwargs.get("metadata") or {})
            self.runs.append(run)
            yield run

        return manager()


class FakeTracingContextFactory:
    def __call__(self, **kwargs):
        @contextmanager
        def manager():
            yield

        return manager()


class FakeOCRExecutionService:
    def __init__(self) -> None:
        self._settings = OCRSettings(
            ocr_default_provider="fake_ocr",
            ocr_timeout_ms=60000,
            ocr_enable_layout=False,
            aliyun_ocr_base_url=None,
            aliyun_ocr_api_key=None,
            aliyun_ocr_app_code=None,
            internal_ocr_base_url=None,
            internal_ocr_api_key=None,
        )
        self.calls: list[list[int] | None] = []

    def extract_text(
        self,
        *,
        request: DocumentParseRequest,
        asset: NormalizedDocumentAsset,
        trace_id: str,
        file_type: str,
    ) -> OCRProviderResponse:
        del asset, trace_id, file_type
        page_range = request.metadata.get("pdf_batch_page_range") or [1]
        self.calls.append(list(page_range))
        pages = [
            OCRPage(page_no=index, text=f"page {page_no}")
            for index, page_no in enumerate(page_range, start=1)
        ]
        return OCRProviderResponse(
            provider="fake_ocr",
            model="ocr-v1",
            text="\n\n".join(page.text for page in pages),
            pages=pages,
            usage={"pages": len(page_range), "requests": 1},
        )


class PDFOCRBatchingServiceTestCase(unittest.TestCase):
    def test_batched_pdf_ocr_emits_root_and_batch_langsmith_traces(self) -> None:
        trace_factory = FakeTraceFactory()
        tracer = LangSmithTracer(
            settings=self._build_langsmith_settings(),
            client=FakeClient(),
            trace_factory=trace_factory,
            tracing_context_factory=FakeTracingContextFactory(),
        )
        with TemporaryDirectory() as temp_dir:
            service = PDFOCRBatchingService(
                OCRSettings(
                    ocr_default_provider="fake_ocr",
                    ocr_timeout_ms=60000,
                    ocr_enable_layout=False,
                    aliyun_ocr_base_url=None,
                    aliyun_ocr_api_key=None,
                    aliyun_ocr_app_code=None,
                    internal_ocr_base_url=None,
                    internal_ocr_api_key=None,
                    ocr_pdf_batch_enabled=True,
                    ocr_pdf_batch_pages=10,
                    ocr_pdf_batch_min_total_pages=11,
                    ocr_pdf_batch_max_retries=2,
                    ocr_pdf_batch_retry_delay_ms=0,
                ),
                checkpoint_repository=PDFOCRCheckpointRepository(temp_dir),
                batch_asset_service=PDFBatchAssetService(),
                tracer=tracer,
            )
            ocr_service = FakeOCRExecutionService()

            result = service.extract_text(
                request=DocumentParseRequest(
                    tenant_id="tenant-a",
                    app_id="app-a",
                    scene="knowledge_ingest",
                    source_type="file_path",
                    source_value=r"D:\fake\sample.pdf",
                ),
                asset=NormalizedDocumentAsset(
                    source_type="file_path",
                    source_value=r"D:\fake\sample.pdf",
                    file_name="sample.pdf",
                    file_type="pdf",
                    content_bytes=self._build_scanned_pdf_bytes(page_count=12),
                    asset_hash="hash-1",
                ),
                trace_id="parse-trace-1",
                ocr_service=ocr_service,  # type: ignore[arg-type]
                cache_key="cache-key-1",
                parser_name="pdf_document_parser",
                parser_version="v3",
            )

        self.assertEqual(result.mode, "batched")
        self.assertEqual(result.batch_count, 2)
        self.assertEqual(ocr_service.calls, [list(range(1, 11)), [11, 12]])
        self.assertEqual(
            [call["name"] for call in trace_factory.calls],
            ["pdf.ocr", "pdf.ocr.batch", "pdf.ocr.batch"],
        )
        self.assertEqual(trace_factory.calls[0]["project_name"], "ingest-project")
        self.assertEqual(trace_factory.calls[1]["metadata"]["batch_index"], 1)
        self.assertEqual(trace_factory.calls[2]["metadata"]["batch_index"], 2)
        self.assertEqual(trace_factory.runs[1].outputs["retry_count"], 0)
        self.assertEqual(trace_factory.runs[2].outputs["retry_count"], 0)

    @staticmethod
    def _build_langsmith_settings():
        from app.core.config import LangSmithSettings

        return LangSmithSettings(
            langsmith_tracing=True,
            langsmith_api_key="test-key",
            langsmith_endpoint="https://api.smith.langchain.com",
            langsmith_project="default",
            langsmith_workspace_id=None,
            app_langsmith_enabled=True,
            app_langsmith_project_rag="rag-project",
            app_langsmith_project_ingest="ingest-project",
            app_langsmith_project_eval="eval-project",
            app_langsmith_sample_rate=1.0,
            app_langsmith_max_text_chars=200,
            app_langsmith_capture_retrieved_text=True,
            app_langsmith_capture_prompts=True,
            app_langsmith_redact_pii=False,
            app_langsmith_otel_enabled=False,
            app_langsmith_otel_only=False,
        )

    @staticmethod
    def _build_scanned_pdf_bytes(page_count: int) -> bytes:
        writer = PdfWriter()
        for _ in range(page_count):
            writer.add_blank_page(width=612, height=792)
        buffer = BytesIO()
        writer.write(buffer)
        return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
