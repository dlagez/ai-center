from __future__ import annotations

import re
import zlib

from app.modules.document_center.parsers.base import BaseDocumentParser, normalize_text
from app.modules.document_center.schemas import (
    DocumentLocation,
    DocumentParseRequest,
    NormalizedDocumentAsset,
)
from app.modules.document_center.services.ocr_execution_service import OCRExecutionService
from app.modules.document_center.services.pdf_ocr_batching_service import (
    PDFOCRExecutionResult,
    PDFOCRBatchingService,
)
from app.runtime.tools.schemas import OCRPage

STREAM_PATTERN = re.compile(
    br"<<(?P<dict>.*?)>>\s*stream\r?\n(?P<stream>.*?)\r?\nendstream", re.S
)
TEXT_BLOCK_PATTERN = re.compile(r"BT(.*?)ET", re.S)
TEXT_TOKEN_PATTERN = re.compile(r"\((?:\\.|[^\\()])*\)\s*Tj")
TEXT_ARRAY_PATTERN = re.compile(r"\[(.*?)\]\s*TJ", re.S)
TEXT_LITERAL_PATTERN = re.compile(r"\((?:\\.|[^\\()])*\)")


class PDFDocumentParser(BaseDocumentParser):
    parser_name = "pdf_document_parser"
    parser_version = "v3"
    supported_file_types = ("pdf",)

    def __init__(
        self,
        ocr_service: OCRExecutionService,
        *,
        pdf_ocr_batching_service: PDFOCRBatchingService | None = None,
    ) -> None:
        self._ocr_service = ocr_service
        self._pdf_ocr_batching_service = pdf_ocr_batching_service

    def parse(
        self,
        request: DocumentParseRequest,
        asset: NormalizedDocumentAsset,
        *,
        trace_id: str,
        cache_key: str | None = None,
    ):
        pages = self._extract_text_pages(asset.content_bytes)
        if request.page_range:
            page_range = set(request.page_range)
            pages = [page for page in pages if page.page_no in page_range]
        pages = [page for page in pages if self._is_meaningful_text(page.text)]
        text = "\n\n".join(page.text for page in pages if page.text).strip()

        if text:
            return self.build_result(
                trace_id=trace_id,
                asset=asset,
                text=text,
                pages=pages,
                locations=[DocumentLocation(page_no=page.page_no) for page in pages],
                metadata={"strategy": "text_layer"},
            )

        execution = self._execute_pdf_ocr(
            request=request,
            asset=asset,
            trace_id=trace_id,
            cache_key=cache_key,
        )
        response = execution.response
        locations = [
            DocumentLocation(page_no=page.page_no)
            for page in response.pages
            if page.page_no is not None
        ]
        return self.build_result(
            trace_id=trace_id,
            asset=asset,
            text=response.text,
            pages=response.pages,
            locations=locations,
            metadata={
                "usage": response.usage,
                "strategy": "ocr",
                "ocr_mode": execution.mode,
                "ocr_batch_count": execution.batch_count,
                "ocr_batch_page_ranges": execution.batch_page_ranges,
                "ocr_total_pages": execution.total_pages,
                "ocr_retry_count": execution.retry_count,
                "ocr_retried_batch_count": execution.retried_batch_count,
                "ocr_resumed_batch_count": execution.resumed_batch_count,
            },
            provider=response.provider,
            model=response.model,
            raw_response=response.raw_response,
        )

    def _execute_pdf_ocr(
        self,
        *,
        request: DocumentParseRequest,
        asset: NormalizedDocumentAsset,
        trace_id: str,
        cache_key: str | None,
    ) -> PDFOCRExecutionResult:
        if self._pdf_ocr_batching_service is None:
            response = self._ocr_service.extract_text(
                request=request,
                asset=asset,
                trace_id=trace_id,
                file_type="pdf",
            )
            return PDFOCRExecutionResult(
                response=response,
                mode="single",
                total_pages=None,
                batch_count=1,
                batch_page_ranges=[list(request.page_range)] if request.page_range else [],
            )

        return self._pdf_ocr_batching_service.extract_text(
            request=request,
            asset=asset,
            trace_id=trace_id,
            ocr_service=self._ocr_service,
            cache_key=cache_key,
            parser_name=self.parser_name,
            parser_version=self.parser_version,
        )

    def _extract_text_pages(self, content: bytes) -> list[OCRPage]:
        pages: list[OCRPage] = []
        for index, match in enumerate(STREAM_PATTERN.finditer(content), start=1):
            dictionary = match.group("dict")
            stream = match.group("stream").lstrip(b"\r\n")
            if b"/Subtype /Image" in dictionary:
                continue

            decoded_stream = self._decode_stream(dictionary, stream)
            page_text = self._extract_text_from_stream(decoded_stream)
            if page_text:
                pages.append(OCRPage(page_no=len(pages) + 1, text=page_text))
        return pages

    def _decode_stream(self, dictionary: bytes, stream: bytes) -> bytes:
        if b"/FlateDecode" not in dictionary:
            return stream
        try:
            return zlib.decompress(stream)
        except zlib.error:
            return stream

    def _extract_text_from_stream(self, stream: bytes) -> str:
        text = stream.decode("latin-1", errors="ignore")
        segments: list[str] = []
        for block in TEXT_BLOCK_PATTERN.findall(text):
            block_parts: list[str] = []
            for token in TEXT_TOKEN_PATTERN.findall(block):
                literals = TEXT_LITERAL_PATTERN.findall(token)
                if literals:
                    block_parts.append(self._decode_pdf_literal(literals[0]))
            for token in TEXT_ARRAY_PATTERN.findall(block):
                nested = [
                    self._decode_pdf_literal(item)
                    for item in TEXT_LITERAL_PATTERN.findall(token)
                ]
                if nested:
                    block_parts.append("".join(nested))
            normalized = normalize_text("\n".join(part for part in block_parts if part))
            if normalized:
                segments.append(normalized)
        return "\n".join(segments).strip()

    def _decode_pdf_literal(self, token: str) -> str:
        value = token
        if value.startswith("(") and value.endswith(")"):
            value = value[1:-1]

        result: list[str] = []
        index = 0
        while index < len(value):
            char = value[index]
            if char != "\\":
                result.append(char)
                index += 1
                continue

            index += 1
            if index >= len(value):
                break
            escaped = value[index]
            mapping = {
                "n": "\n",
                "r": "\r",
                "t": "\t",
                "b": "\b",
                "f": "\f",
                "(": "(",
                ")": ")",
                "\\": "\\",
            }
            if escaped in mapping:
                result.append(mapping[escaped])
                index += 1
                continue

            octal = escaped
            index += 1
            for _ in range(2):
                if index < len(value) and value[index].isdigit():
                    octal += value[index]
                    index += 1
                else:
                    break
            try:
                result.append(chr(int(octal, 8)))
            except ValueError:
                result.append(octal)
        return "".join(result)

    def _is_meaningful_text(self, text: str) -> bool:
        normalized = normalize_text(text)
        if not normalized:
            return False

        meaningful_chars = 0
        suspicious_chars = 0
        content_chars = 0

        for char in normalized:
            if char.isspace():
                continue
            content_chars += 1
            code_point = ord(char)
            if self._is_suspicious_char(char, code_point):
                suspicious_chars += 1
                continue
            if self._is_meaningful_char(char, code_point):
                meaningful_chars += 1

        if content_chars == 0:
            return False
        if suspicious_chars > max(2, content_chars // 20):
            return False
        return meaningful_chars / content_chars >= 0.6

    @staticmethod
    def _is_suspicious_char(char: str, code_point: int) -> bool:
        if code_point < 32 and char not in {"\n", "\r", "\t"}:
            return True
        if 0x7F <= code_point <= 0x9F:
            return True
        return False

    @staticmethod
    def _is_meaningful_char(char: str, code_point: int) -> bool:
        if char.isascii():
            return char.isalnum() or char in {
                "#",
                "*",
                "-",
                "_",
                "|",
                ".",
                ",",
                ":",
                ";",
                "(",
                ")",
                "[",
                "]",
                "{",
                "}",
                "/",
                "\\",
                "'",
                '"',
                "!",
                "?",
                "@",
                "&",
                "%",
                "+",
                "=",
                "<",
                ">",
                "~",
                "`",
            }
        return (
            0x4E00 <= code_point <= 0x9FFF
            or 0x3400 <= code_point <= 0x4DBF
            or 0x3000 <= code_point <= 0x303F
            or 0xFF00 <= code_point <= 0xFFEF
        )
