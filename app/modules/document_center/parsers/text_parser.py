from __future__ import annotations

from app.modules.document_center.parsers.base import (
    BaseDocumentParser,
    decode_text_bytes,
    normalize_text,
)
from app.modules.document_center.schemas import DocumentParseRequest, NormalizedDocumentAsset


class TextDocumentParser(BaseDocumentParser):
    parser_name = "text_document_parser"
    supported_file_types = ("txt", "md")

    def parse(
        self,
        request: DocumentParseRequest,
        asset: NormalizedDocumentAsset,
        *,
        trace_id: str,
        cache_key: str | None = None,
    ):
        del cache_key
        text = normalize_text(decode_text_bytes(asset.content_bytes))
        return self.build_result(trace_id=trace_id, asset=asset, text=text)
