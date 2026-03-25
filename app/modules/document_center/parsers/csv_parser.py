from __future__ import annotations

import csv
from io import StringIO

from app.modules.document_center.parsers.base import BaseDocumentParser, decode_text_bytes
from app.modules.document_center.schemas import (
    DocumentLocation,
    DocumentParseRequest,
    NormalizedDocumentAsset,
)


class CSVDocumentParser(BaseDocumentParser):
    parser_name = "csv_document_parser"
    supported_file_types = ("csv",)

    def parse(
        self,
        request: DocumentParseRequest,
        asset: NormalizedDocumentAsset,
        *,
        trace_id: str,
    ):
        text_content = decode_text_bytes(asset.content_bytes)
        reader = csv.reader(StringIO(text_content))
        row_payloads: list[dict[str, object]] = []
        row_texts: list[str] = []
        locations: list[DocumentLocation] = []

        for row_index, row in enumerate(reader, start=1):
            normalized_cells = [cell.strip() for cell in row]
            row_text = " | ".join(cell for cell in normalized_cells if cell)
            row_payloads.append(
                {
                    "row_index": row_index,
                    "cells": normalized_cells,
                    "text": row_text,
                }
            )
            if row_text:
                row_texts.append(row_text)
                locations.append(DocumentLocation(row_index=row_index))

        return self.build_result(
            trace_id=trace_id,
            asset=asset,
            text="\n".join(row_texts).strip(),
            tables=[{"sheet_name": "Sheet1", "rows": row_payloads}],
            locations=locations,
        )
