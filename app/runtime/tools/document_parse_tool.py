from __future__ import annotations

from app.modules.document_center.schemas import DocumentParseRequest, DocumentParseResult
from app.modules.document_center.services import (
    DocumentParseService,
    build_document_parse_service,
)
from app.runtime.tools.base import BaseRuntimeTool


class DocumentParseTool(BaseRuntimeTool):
    name = "document_parse_text"
    description = "Parse text content from common document sources."
    request_model = DocumentParseRequest
    result_model = DocumentParseResult

    def __init__(self, service: DocumentParseService) -> None:
        self._service = service

    def execute(self, request: DocumentParseRequest) -> DocumentParseResult:
        return self._service.parse(request)


def build_default_document_parse_tool() -> DocumentParseTool:
    return DocumentParseTool(build_document_parse_service())
