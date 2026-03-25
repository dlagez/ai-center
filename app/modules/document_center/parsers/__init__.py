"""Document parsers."""

from app.modules.document_center.parsers.base import BaseDocumentParser
from app.modules.document_center.parsers.csv_parser import CSVDocumentParser
from app.modules.document_center.parsers.docx_parser import DOCXDocumentParser
from app.modules.document_center.parsers.html_parser import HTMLDocumentParser
from app.modules.document_center.parsers.image_parser import ImageDocumentParser
from app.modules.document_center.parsers.pdf_parser import PDFDocumentParser
from app.modules.document_center.parsers.pptx_parser import PPTXDocumentParser
from app.modules.document_center.parsers.text_parser import TextDocumentParser
from app.modules.document_center.parsers.xlsx_parser import XLSXDocumentParser

__all__ = [
    "BaseDocumentParser",
    "CSVDocumentParser",
    "DOCXDocumentParser",
    "HTMLDocumentParser",
    "ImageDocumentParser",
    "PDFDocumentParser",
    "PPTXDocumentParser",
    "TextDocumentParser",
    "XLSXDocumentParser",
]
