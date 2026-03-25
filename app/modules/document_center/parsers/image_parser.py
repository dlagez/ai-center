from __future__ import annotations

from app.modules.document_center.parsers.base import BaseDocumentParser
from app.modules.document_center.schemas import (
    DocumentLocation,
    DocumentParseRequest,
    NormalizedDocumentAsset,
)
from app.modules.document_center.services.ocr_execution_service import OCRExecutionService


class ImageDocumentParser(BaseDocumentParser):
    parser_name = "image_ocr_parser"
    supported_file_types = ("image",)

    def __init__(self, ocr_service: OCRExecutionService) -> None:
        self._ocr_service = ocr_service

    def parse(
        self,
        request: DocumentParseRequest,
        asset: NormalizedDocumentAsset,
        *,
        trace_id: str,
    ):
        response = self._ocr_service.extract_text(
            request=request,
            asset=asset,
            trace_id=trace_id,
            file_type="image",
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
