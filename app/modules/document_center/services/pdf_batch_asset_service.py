from __future__ import annotations

import base64
import hashlib
import re
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from app.modules.document_center.schemas import NormalizedDocumentAsset

_PAGE_COUNT_PATTERN = re.compile(br"/Count\s+(\d+)")
_PAGE_OBJECT_PATTERN = re.compile(br"/Type\s*/Page\b")


class PDFBatchAssetService:
    def infer_total_pages(self, content: bytes) -> int | None:
        try:
            reader = PdfReader(BytesIO(content))
            return len(reader.pages)
        except Exception:
            count_candidates = [
                int(match.group(1))
                for match in _PAGE_COUNT_PATTERN.finditer(content)
                if int(match.group(1)) > 0
            ]
            if count_candidates:
                return max(count_candidates)
            page_object_count = len(_PAGE_OBJECT_PATTERN.findall(content))
            return page_object_count or None

    def can_split(self, content: bytes) -> bool:
        try:
            PdfReader(BytesIO(content))
            return True
        except Exception:
            return False

    def build_batch_asset(
        self,
        *,
        asset: NormalizedDocumentAsset,
        page_range: list[int],
        batch_index: int,
    ) -> NormalizedDocumentAsset:
        reader = PdfReader(BytesIO(asset.content_bytes))
        writer = PdfWriter()
        for page_no in page_range:
            writer.add_page(reader.pages[page_no - 1])

        buffer = BytesIO()
        writer.write(buffer)
        batch_bytes = buffer.getvalue()
        encoded = base64.b64encode(batch_bytes).decode("ascii")
        stem = Path(asset.file_name).stem or "document"
        file_name = (
            f"{stem}-batch-{batch_index:04d}-pages-{page_range[0]}-{page_range[-1]}.pdf"
        )
        return NormalizedDocumentAsset(
            source_type="base64",
            source_value=encoded,
            file_name=file_name,
            file_type="pdf",
            content_bytes=batch_bytes,
            asset_hash=hashlib.sha256(batch_bytes).hexdigest(),
        )
