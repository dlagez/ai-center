from __future__ import annotations

from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from app.core.exceptions import DocumentParseBadResponseError
from app.modules.document_center.parsers.base import BaseDocumentParser, normalize_text
from app.modules.document_center.schemas import DocumentParseRequest, NormalizedDocumentAsset

WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


class DOCXDocumentParser(BaseDocumentParser):
    parser_name = "docx_document_parser"
    supported_file_types = ("docx",)

    def parse(
        self,
        request: DocumentParseRequest,
        asset: NormalizedDocumentAsset,
        *,
        trace_id: str,
    ):
        try:
            with ZipFile(self._to_buffer(asset.content_bytes)) as archive:
                document_xml = archive.read("word/document.xml")
        except (KeyError, BadZipFile, OSError) as exc:
            raise DocumentParseBadResponseError("Invalid DOCX document.") from exc

        root = ET.fromstring(document_xml)
        paragraphs: list[str] = []
        for paragraph in root.findall(".//w:p", WORD_NS):
            runs = [node.text or "" for node in paragraph.findall(".//w:t", WORD_NS)]
            if runs:
                paragraphs.append("".join(runs))
        text = normalize_text("\n".join(paragraphs))
        return self.build_result(trace_id=trace_id, asset=asset, text=text)

    @staticmethod
    def _to_buffer(content: bytes):
        from io import BytesIO

        return BytesIO(content)
