from __future__ import annotations

from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from app.core.exceptions import DocumentParseBadResponseError
from app.modules.document_center.parsers.base import BaseDocumentParser
from app.modules.document_center.schemas import (
    DocumentLocation,
    DocumentParseRequest,
    NormalizedDocumentAsset,
)

SHEET_NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
PACKAGE_REL_NS = {"p": "http://schemas.openxmlformats.org/package/2006/relationships"}


class XLSXDocumentParser(BaseDocumentParser):
    parser_name = "xlsx_document_parser"
    supported_file_types = ("xlsx",)

    def parse(
        self,
        request: DocumentParseRequest,
        asset: NormalizedDocumentAsset,
        *,
        trace_id: str,
    ):
        try:
            with ZipFile(self._to_buffer(asset.content_bytes)) as archive:
                shared_strings = self._load_shared_strings(archive)
                sheet_entries = self._load_sheet_entries(archive)
                tables: list[dict[str, object]] = []
                row_texts: list[str] = []
                locations: list[DocumentLocation] = []

                for sheet_name, sheet_path in sheet_entries:
                    rows = self._load_rows(
                        archive,
                        sheet_path=sheet_path,
                        shared_strings=shared_strings,
                    )
                    tables.append({"sheet_name": sheet_name, "rows": rows})
                    for row in rows:
                        row_text = row["text"]
                        if not isinstance(row_text, str) or not row_text:
                            continue
                        row_texts.append(f"[{sheet_name}] {row_text}")
                        locations.append(
                            DocumentLocation(row_index=int(row["row_index"]))
                        )
        except (BadZipFile, OSError, ET.ParseError, KeyError, ValueError) as exc:
            raise DocumentParseBadResponseError("Invalid XLSX document.") from exc

        return self.build_result(
            trace_id=trace_id,
            asset=asset,
            text="\n".join(row_texts).strip(),
            tables=tables,
            locations=locations,
        )

    def _load_shared_strings(self, archive: ZipFile) -> list[str]:
        try:
            xml_bytes = archive.read("xl/sharedStrings.xml")
        except KeyError:
            return []
        root = ET.fromstring(xml_bytes)
        strings: list[str] = []
        for item in root.findall(".//s:si", SHEET_NS):
            texts = [node.text or "" for node in item.findall(".//s:t", SHEET_NS)]
            strings.append("".join(texts))
        return strings

    def _load_sheet_entries(self, archive: ZipFile) -> list[tuple[str, str]]:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))

        rels: dict[str, str] = {}
        for rel in rels_root.findall(".//p:Relationship", PACKAGE_REL_NS):
            rel_id = rel.get("Id")
            target = rel.get("Target")
            if rel_id and target:
                rels[rel_id] = target

        entries: list[tuple[str, str]] = []
        for sheet in workbook.findall(".//s:sheet", SHEET_NS):
            name = sheet.get("name") or "Sheet"
            rel_id = sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            if rel_id and rel_id in rels:
                entries.append((name, f"xl/{rels[rel_id]}"))
        return entries

    def _load_rows(
        self,
        archive: ZipFile,
        *,
        sheet_path: str,
        shared_strings: list[str],
    ) -> list[dict[str, object]]:
        root = ET.fromstring(archive.read(sheet_path))
        rows: list[dict[str, object]] = []
        for row in root.findall(".//s:row", SHEET_NS):
            row_index = int(row.get("r") or len(rows) + 1)
            cells: list[str] = []
            for cell in row.findall("s:c", SHEET_NS):
                cells.append(self._parse_cell(cell, shared_strings))
            row_text = " | ".join(cell for cell in cells if cell)
            rows.append(
                {
                    "row_index": row_index,
                    "cells": cells,
                    "text": row_text,
                }
            )
        return rows

    def _parse_cell(self, cell: ET.Element, shared_strings: list[str]) -> str:
        cell_type = cell.get("t")
        if cell_type == "inlineStr":
            texts = [node.text or "" for node in cell.findall(".//s:t", SHEET_NS)]
            return "".join(texts).strip()

        value = cell.find("s:v", SHEET_NS)
        raw_value = (value.text or "").strip() if value is not None and value.text else ""
        if cell_type == "s" and raw_value:
            index = int(raw_value)
            if 0 <= index < len(shared_strings):
                return shared_strings[index].strip()
        return raw_value

    @staticmethod
    def _to_buffer(content: bytes):
        from io import BytesIO

        return BytesIO(content)
