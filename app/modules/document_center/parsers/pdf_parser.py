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
    supported_file_types = ("pdf",)

    def __init__(self, ocr_service: OCRExecutionService) -> None:
        self._ocr_service = ocr_service

    def parse(
        self,
        request: DocumentParseRequest,
        asset: NormalizedDocumentAsset,
        *,
        trace_id: str,
    ):
        pages = self._extract_text_pages(asset.content_bytes)
        if request.page_range:
            page_range = set(request.page_range)
            pages = [page for page in pages if page.page_no in page_range]
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

        response = self._ocr_service.extract_text(
            request=request,
            asset=asset,
            trace_id=trace_id,
            file_type="pdf",
        )
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
            metadata={"usage": response.usage, "strategy": "ocr"},
            provider=response.provider,
            model=response.model,
            raw_response=response.raw_response,
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
