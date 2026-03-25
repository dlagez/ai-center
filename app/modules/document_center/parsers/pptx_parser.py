from __future__ import annotations

import re
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from app.core.exceptions import DocumentParseBadResponseError
from app.modules.document_center.parsers.base import BaseDocumentParser, normalize_text
from app.modules.document_center.schemas import (
    DocumentLocation,
    DocumentParseRequest,
    NormalizedDocumentAsset,
)
from app.runtime.tools.schemas import OCRPage

DRAWING_NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}


class PPTXDocumentParser(BaseDocumentParser):
    parser_name = "pptx_document_parser"
    supported_file_types = ("pptx",)

    def parse(
        self,
        request: DocumentParseRequest,
        asset: NormalizedDocumentAsset,
        *,
        trace_id: str,
    ):
        try:
            with ZipFile(self._to_buffer(asset.content_bytes)) as archive:
                slide_names = sorted(
                    (
                        name
                        for name in archive.namelist()
                        if name.startswith("ppt/slides/slide") and name.endswith(".xml")
                    ),
                    key=self._slide_sort_key,
                )
                pages: list[OCRPage] = []
                for index, slide_name in enumerate(slide_names, start=1):
                    slide_xml = archive.read(slide_name)
                    root = ET.fromstring(slide_xml)
                    texts = [
                        node.text or ""
                        for node in root.findall(".//a:t", DRAWING_NS)
                        if node.text
                    ]
                    slide_text = normalize_text("\n".join(texts))
                    if slide_text:
                        pages.append(OCRPage(page_no=index, text=slide_text))
        except (BadZipFile, OSError, ET.ParseError) as exc:
            raise DocumentParseBadResponseError("Invalid PPTX document.") from exc

        text = "\n\n".join(page.text for page in pages if page.text)
        locations = [DocumentLocation(page_no=page.page_no) for page in pages]
        return self.build_result(
            trace_id=trace_id,
            asset=asset,
            text=text,
            pages=pages,
            locations=locations,
        )

    @staticmethod
    def _slide_sort_key(name: str) -> int:
        match = re.search(r"slide(\d+)\.xml$", name)
        return int(match.group(1)) if match else 0

    @staticmethod
    def _to_buffer(content: bytes):
        from io import BytesIO

        return BytesIO(content)
