from __future__ import annotations

import tempfile
import unittest
import zlib
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from pypdf import PdfWriter

from app.core.config import DocumentParseSettings, OCRSettings
from app.core.exceptions import OCRToolTimeoutError
from app.integrations.ocr_providers.base import BaseOCRProviderAdapter
from app.modules.document_center import DocumentParseRequest, build_document_parse_service
from app.modules.document_center.repositories import (
    PDFOCRCheckpointRepository,
    ParseCacheRepository,
)
from app.modules.document_center.schemas import (
    PDFOCRBatchCheckpoint,
    PDFOCRBatchManifestEntry,
    PDFOCRCheckpointManifest,
)
from app.runtime.tools.schemas import OCRPage, OCRProviderResponse, OCRToolRequest


class FakeOCRAdapter(BaseOCRProviderAdapter):
    provider_name = "fake_ocr"

    def __init__(
        self,
        response: OCRProviderResponse | None = None,
        *,
        response_builder=None,
    ) -> None:
        self.response = response
        self.response_builder = response_builder
        self.calls = 0
        self.last_request: OCRToolRequest | None = None
        self.requests: list[OCRToolRequest] = []

    def extract_text(self, request: OCRToolRequest, *, trace_id: str) -> OCRProviderResponse:
        self.calls += 1
        self.last_request = request
        self.requests.append(request)
        if self.response_builder is not None:
            return self.response_builder(request)
        if self.response is None:
            raise AssertionError("FakeOCRAdapter requires a response or response_builder.")
        return self.response


class DocumentParseServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.ocr_settings = OCRSettings(
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
        )
        self.fake_ocr = FakeOCRAdapter(
            OCRProviderResponse(
                provider="fake_ocr",
                model="ocr-v1",
                text="ocr result",
                pages=[OCRPage(page_no=1, text="ocr result")],
                usage={"pages": 1},
            )
        )

    def test_document_parse_service_caches_text_documents_by_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._build_service(temp_dir)
            text_path = Path(temp_dir) / "sample.txt"
            text_path.write_text("hello world", encoding="utf-8")

            request = DocumentParseRequest(
                tenant_id="tenant-a",
                app_id="app-a",
                scene="knowledge_ingest",
                source_type="file_path",
                source_value=str(text_path),
            )

            first = service.parse(request)
            second = service.parse(request)

        self.assertEqual(first.text, "hello world")
        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)
        self.assertEqual(first.asset_hash, second.asset_hash)
        self.assertEqual(self.fake_ocr.calls, 0)

    def test_document_parse_service_extracts_pdf_text_layer_before_ocr(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._build_service(temp_dir)
            pdf_path = Path(temp_dir) / "sample.pdf"
            pdf_path.write_bytes(self._build_pdf_bytes("Hello PDF"))

            result = service.parse(
                DocumentParseRequest(
                    tenant_id="tenant-a",
                    app_id="app-a",
                    scene="agent",
                    source_type="file_path",
                    source_value=str(pdf_path),
                )
            )

        self.assertEqual(result.text, "Hello PDF")
        self.assertEqual(result.metadata["strategy"], "text_layer")
        self.assertEqual([location.page_no for location in result.locations], [1])
        self.assertEqual(self.fake_ocr.calls, 0)

    def test_document_parse_service_falls_back_to_ocr_for_garbled_pdf_text_layer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._build_service(temp_dir)
            pdf_path = Path(temp_dir) / "garbled.pdf"
            pdf_path.write_bytes(
                self._build_pdf_bytes(
                    "\x9c\xe8\xd4a\xcfS\xd4\xdd>\x1e57\xdc\xa2\x00\xb6\xbbin!0"
                )
            )

            result = service.parse(
                DocumentParseRequest(
                    tenant_id="tenant-a",
                    app_id="app-a",
                    scene="knowledge_ingest",
                    source_type="file_path",
                    source_value=str(pdf_path),
                )
            )

        self.assertEqual(result.text, "ocr result")
        self.assertEqual(result.metadata["strategy"], "ocr")
        self.assertEqual(result.provider, "fake_ocr")
        self.assertEqual(self.fake_ocr.calls, 1)

    def test_document_parse_service_falls_back_to_ocr_for_images(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._build_service(temp_dir)
            image_path = Path(temp_dir) / "sample.png"
            image_path.write_bytes(b"fake-image")

            result = service.parse(
                DocumentParseRequest(
                    tenant_id="tenant-a",
                    app_id="app-a",
                    scene="agent",
                    source_type="file_path",
                    source_value=str(image_path),
                )
            )

        self.assertEqual(result.text, "ocr result")
        self.assertEqual(result.provider, "fake_ocr")
        self.assertEqual([location.page_no for location in result.locations], [1])
        self.assertEqual(self.fake_ocr.calls, 1)

    def test_document_parse_service_batches_large_scanned_pdf_ocr_requests(self) -> None:
        self.fake_ocr = FakeOCRAdapter(response_builder=self._build_dynamic_pdf_ocr_response)
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._build_service(temp_dir)
            pdf_path = Path(temp_dir) / "scanned.pdf"
            pdf_path.write_bytes(self._build_scanned_pdf_bytes(page_count=23))

            result = service.parse(
                DocumentParseRequest(
                    tenant_id="tenant-a",
                    app_id="app-a",
                    scene="knowledge_ingest",
                    source_type="file_path",
                    source_value=str(pdf_path),
                )
            )

        self.assertEqual(self.fake_ocr.calls, 3)
        self.assertEqual(
            [
                request.metadata.get("pdf_batch_page_range")
                for request in self.fake_ocr.requests
            ],
            [
                list(range(1, 11)),
                list(range(11, 21)),
                [21, 22, 23],
            ],
        )
        self.assertTrue(all(request.page_range is None for request in self.fake_ocr.requests))
        self.assertTrue(
            all(request.source_type == "base64" for request in self.fake_ocr.requests)
        )
        self.assertEqual(result.metadata["strategy"], "ocr")
        self.assertEqual(result.metadata["ocr_mode"], "batched")
        self.assertEqual(result.metadata["ocr_batch_count"], 3)
        self.assertEqual(result.metadata["ocr_total_pages"], 23)
        self.assertEqual(
            [page.page_no for page in result.pages],
            list(range(1, 24)),
        )
        self.assertEqual(
            [location.page_no for location in result.locations],
            list(range(1, 24)),
        )
        self.assertIn("page 1", result.text)
        self.assertIn("page 23", result.text)

    def test_document_parse_service_retries_retryable_pdf_batches(self) -> None:
        attempts_by_batch: dict[tuple[int, ...], int] = {}

        def flaky_response_builder(request: OCRToolRequest) -> OCRProviderResponse:
            page_range = tuple(
                request.metadata.get("pdf_batch_page_range") or [1]
            )
            attempts_by_batch[page_range] = attempts_by_batch.get(page_range, 0) + 1
            if page_range == tuple(range(1, 11)) and attempts_by_batch[page_range] == 1:
                raise OCRToolTimeoutError("temporary timeout")
            return self._build_dynamic_pdf_ocr_response(request)

        self.fake_ocr = FakeOCRAdapter(response_builder=flaky_response_builder)
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._build_service(temp_dir)
            pdf_path = Path(temp_dir) / "retry.pdf"
            pdf_path.write_bytes(self._build_scanned_pdf_bytes(page_count=12))

            result = service.parse(
                DocumentParseRequest(
                    tenant_id="tenant-a",
                    app_id="app-a",
                    scene="knowledge_ingest",
                    source_type="file_path",
                    source_value=str(pdf_path),
                )
            )

        self.assertEqual(self.fake_ocr.calls, 3)
        self.assertEqual(
            [
                request.metadata.get("pdf_batch_page_range")
                for request in self.fake_ocr.requests
            ],
            [
                list(range(1, 11)),
                list(range(1, 11)),
                [11, 12],
            ],
        )
        self.assertTrue(all(request.page_range is None for request in self.fake_ocr.requests))
        self.assertEqual(result.metadata["ocr_mode"], "batched")
        self.assertEqual(result.metadata["ocr_retry_count"], 1)
        self.assertEqual(result.metadata["ocr_retried_batch_count"], 1)
        self.assertIn("page 12", result.text)

    def test_document_parse_service_resumes_pdf_ocr_from_saved_batch_json(self) -> None:
        self.fake_ocr = FakeOCRAdapter(response_builder=self._build_dynamic_pdf_ocr_response)
        with tempfile.TemporaryDirectory() as temp_dir:
            parse_settings = DocumentParseSettings(
                document_parse_cache_dir=str(Path(temp_dir) / "cache"),
                document_parse_enable_cache=True,
                document_parse_download_timeout_ms=1000,
            )
            repository = ParseCacheRepository(parse_settings.document_parse_cache_dir)
            service = build_document_parse_service(
                ocr_settings=self.ocr_settings,
                document_parse_settings=parse_settings,
                adapters={"fake_ocr": self.fake_ocr},
                repository=repository,
            )
            pdf_path = Path(temp_dir) / "resume.pdf"
            pdf_path.write_bytes(self._build_scanned_pdf_bytes(page_count=23))
            request = DocumentParseRequest(
                tenant_id="tenant-a",
                app_id="app-a",
                scene="knowledge_ingest",
                source_type="file_path",
                source_value=str(pdf_path),
            )

            asset = service._file_identity_service.normalize(request)
            parser = service._parser_router_service.resolve(asset)
            cache_key = service._parse_cache_service.build_cache_key(
                asset=asset,
                request=request,
                parser_name=parser.parser_name,
                parser_version=parser.parser_version,
            )
            checkpoint_repository = PDFOCRCheckpointRepository(
                parse_settings.document_parse_cache_dir
            )
            now = "2026-03-26T00:00:00+00:00"
            manifest = PDFOCRCheckpointManifest(
                cache_key=cache_key,
                state="running",
                parser_name=parser.parser_name,
                parser_version=parser.parser_version,
                provider="fake_ocr",
                file_name=asset.file_name,
                file_type=asset.file_type,
                asset_hash=asset.asset_hash,
                requested_page_range=None,
                target_pages=list(range(1, 24)),
                batch_size=10,
                batch_count=3,
                completed_batch_count=1,
                created_at=now,
                updated_at=now,
                batches=[
                    PDFOCRBatchManifestEntry(
                        batch_index=1,
                        page_range=list(range(1, 11)),
                        output_file="batch-0001-pages-1-10.json",
                        status="completed",
                        attempt_count=1,
                    ),
                    PDFOCRBatchManifestEntry(
                        batch_index=2,
                        page_range=list(range(11, 21)),
                        output_file="batch-0002-pages-11-20.json",
                    ),
                    PDFOCRBatchManifestEntry(
                        batch_index=3,
                        page_range=[21, 22, 23],
                        output_file="batch-0003-pages-21-23.json",
                    ),
                ],
            )
            checkpoint_repository.save_manifest(cache_key, manifest)
            checkpoint_repository.save_batch(
                cache_key,
                "batch-0001-pages-1-10.json",
                PDFOCRBatchCheckpoint(
                    batch_index=1,
                    page_range=list(range(1, 11)),
                    provider="fake_ocr",
                    model="ocr-v1",
                    attempt_count=1,
                    started_at=now,
                    finished_at=now,
                    pages=[
                        OCRPage(page_no=page_no, text=f"page {page_no}")
                        for page_no in range(1, 11)
                    ],
                    text="\n\n".join(f"page {page_no}" for page_no in range(1, 11)),
                    usage={"pages": 10, "requests": 1},
                ),
            )

            result = service.parse(request)

        self.assertEqual(self.fake_ocr.calls, 2)
        self.assertEqual(
            [
                request.metadata.get("pdf_batch_page_range")
                for request in self.fake_ocr.requests
            ],
            [
                list(range(11, 21)),
                [21, 22, 23],
            ],
        )
        self.assertEqual(result.metadata["ocr_resumed_batch_count"], 1)
        self.assertIn("page 1", result.text)
        self.assertIn("page 23", result.text)

    def test_document_parse_service_parses_docx_pptx_and_xlsx_locations(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._build_service(temp_dir)
            docx_path = Path(temp_dir) / "sample.docx"
            docx_path.write_bytes(self._build_docx_bytes(["Hello", "World"]))

            pptx_path = Path(temp_dir) / "sample.pptx"
            pptx_path.write_bytes(self._build_pptx_bytes(["Slide One", "Slide Two"]))

            xlsx_path = Path(temp_dir) / "sample.xlsx"
            xlsx_path.write_bytes(
                self._build_xlsx_bytes(
                    [
                        ["Name", "Value"],
                        ["Alice", "42"],
                    ]
                )
            )

            docx_result = service.parse(
                DocumentParseRequest(
                    tenant_id="tenant-a",
                    app_id="app-a",
                    scene="knowledge_ingest",
                    source_type="file_path",
                    source_value=str(docx_path),
                )
            )
            pptx_result = service.parse(
                DocumentParseRequest(
                    tenant_id="tenant-a",
                    app_id="app-a",
                    scene="knowledge_ingest",
                    source_type="file_path",
                    source_value=str(pptx_path),
                )
            )
            xlsx_result = service.parse(
                DocumentParseRequest(
                    tenant_id="tenant-a",
                    app_id="app-a",
                    scene="knowledge_ingest",
                    source_type="file_path",
                    source_value=str(xlsx_path),
                )
            )

        self.assertEqual(docx_result.text, "Hello\nWorld")
        self.assertEqual([page.page_no for page in pptx_result.pages], [1, 2])
        self.assertEqual([location.page_no for location in pptx_result.locations], [1, 2])
        self.assertEqual(
            [location.row_index for location in xlsx_result.locations],
            [1, 2],
        )
        self.assertIn("[Sheet1] Name | Value", xlsx_result.text)
        self.assertIn("[Sheet1] Alice | 42", xlsx_result.text)

    def _build_service(self, temp_dir: str):
        parse_settings = DocumentParseSettings(
            document_parse_cache_dir=str(Path(temp_dir) / "cache"),
            document_parse_enable_cache=True,
            document_parse_download_timeout_ms=1000,
        )
        repository = ParseCacheRepository(parse_settings.document_parse_cache_dir)
        return build_document_parse_service(
            ocr_settings=self.ocr_settings,
            document_parse_settings=parse_settings,
            adapters={"fake_ocr": self.fake_ocr},
            repository=repository,
        )

    @staticmethod
    def _build_dynamic_pdf_ocr_response(request: OCRToolRequest) -> OCRProviderResponse:
        page_range = request.metadata.get("pdf_batch_page_range") or request.page_range or [1]
        pages = [
            OCRPage(
                page_no=index,
                text=f"page {page_no}",
            )
            for index, page_no in enumerate(page_range, start=1)
        ]
        return OCRProviderResponse(
            provider="fake_ocr",
            model="ocr-v1",
            text="\n\n".join(page.text for page in pages),
            pages=pages,
            usage={"pages": len(page_range), "requests": 1},
        )

    @staticmethod
    def _build_pdf_bytes(text: str) -> bytes:
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
        compressed = zlib.compress(stream)
        return (
            b"%PDF-1.4\n"
            b"1 0 obj\n"
            + f"<< /Length {len(compressed)} /Filter /FlateDecode >>\n".encode("ascii")
            + b"stream\n"
            + compressed
            + b"\nendstream\nendobj\n%%EOF"
        )

    @staticmethod
    def _build_scanned_pdf_bytes(page_count: int) -> bytes:
        writer = PdfWriter()
        for _ in range(page_count):
            writer.add_blank_page(width=612, height=792)
        buffer = BytesIO()
        writer.write(buffer)
        return buffer.getvalue()

    @staticmethod
    def _build_docx_bytes(paragraphs: list[str]) -> bytes:
        buffer = BytesIO()
        document_xml = (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body>"
            + "".join(
                f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>"
                for paragraph in paragraphs
            )
            + "</w:body></w:document>"
        )
        with ZipFile(buffer, "w") as archive:
            archive.writestr("word/document.xml", document_xml)
        return buffer.getvalue()

    @staticmethod
    def _build_pptx_bytes(slides: list[str]) -> bytes:
        buffer = BytesIO()
        with ZipFile(buffer, "w") as archive:
            for index, slide_text in enumerate(slides, start=1):
                slide_xml = (
                    '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                    f"<p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>{slide_text}</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld>"
                    "</p:sld>"
                )
                archive.writestr(f"ppt/slides/slide{index}.xml", slide_xml)
        return buffer.getvalue()

    @staticmethod
    def _build_xlsx_bytes(rows: list[list[str]]) -> bytes:
        buffer = BytesIO()
        workbook_xml = (
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>'
            "</workbook>"
        )
        rels_xml = (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/>'
            "</Relationships>"
        )
        sheet_rows = []
        for row_index, row in enumerate(rows, start=1):
            cell_xml = "".join(
                f'<c r="{chr(64 + col_index)}{row_index}" t="inlineStr"><is><t>{value}</t></is></c>'
                for col_index, value in enumerate(row, start=1)
            )
            sheet_rows.append(f'<row r="{row_index}">{cell_xml}</row>')
        sheet_xml = (
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f"<sheetData>{''.join(sheet_rows)}</sheetData>"
            "</worksheet>"
        )
        with ZipFile(buffer, "w") as archive:
            archive.writestr("xl/workbook.xml", workbook_xml)
            archive.writestr("xl/_rels/workbook.xml.rels", rels_xml)
            archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        return buffer.getvalue()
