from __future__ import annotations

from html.parser import HTMLParser

from app.modules.document_center.parsers.base import (
    BaseDocumentParser,
    decode_text_bytes,
    normalize_text,
)
from app.modules.document_center.schemas import DocumentParseRequest, NormalizedDocumentAsset


class _HTMLTextExtractor(HTMLParser):
    _BLOCK_TAGS = {
        "article",
        "aside",
        "br",
        "div",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "li",
        "main",
        "p",
        "section",
        "table",
        "tr",
    }

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if data.strip():
            self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts)


class HTMLDocumentParser(BaseDocumentParser):
    parser_name = "html_document_parser"
    supported_file_types = ("html",)

    def parse(
        self,
        request: DocumentParseRequest,
        asset: NormalizedDocumentAsset,
        *,
        trace_id: str,
        cache_key: str | None = None,
    ):
        del cache_key
        extractor = _HTMLTextExtractor()
        extractor.feed(decode_text_bytes(asset.content_bytes))
        text = normalize_text(extractor.get_text())
        return self.build_result(trace_id=trace_id, asset=asset, text=text)
