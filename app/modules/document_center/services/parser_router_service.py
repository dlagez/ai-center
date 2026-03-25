from __future__ import annotations

from collections.abc import Iterable

from app.core.exceptions import DocumentParseUnsupportedFileTypeError
from app.modules.document_center.parsers import BaseDocumentParser
from app.modules.document_center.schemas import NormalizedDocumentAsset


class ParserRouterService:
    def __init__(self, parsers: Iterable[BaseDocumentParser]) -> None:
        self._parsers = list(parsers)

    def resolve(self, asset: NormalizedDocumentAsset) -> BaseDocumentParser:
        for parser in self._parsers:
            if parser.supports(asset):
                return parser
        raise DocumentParseUnsupportedFileTypeError(
            f"Unsupported document file type '{asset.file_type}'."
        )
