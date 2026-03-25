"""Knowledge center services."""

from app.modules.knowledge_center.services.document_ocr_service import (
    DocumentOCRService,
    build_document_ocr_service,
)

__all__ = [
    "DocumentOCRService",
    "build_document_ocr_service",
]
