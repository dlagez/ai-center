from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.modules.document_center.schemas import (
    DocumentLocation,
    DocumentParseRequest,
    DocumentParseResult,
    NormalizedDocumentAsset,
)
from app.runtime.tools.schemas import OCRPage


class BaseDocumentParser(ABC):
    parser_name: str
    parser_version: str = "v1"
    supported_file_types: tuple[str, ...] = ()

    def supports(self, asset: NormalizedDocumentAsset) -> bool:
        return asset.file_type in self.supported_file_types

    @abstractmethod
    def parse(
        self,
        request: DocumentParseRequest,
        asset: NormalizedDocumentAsset,
        *,
        trace_id: str,
        cache_key: str | None = None,
    ) -> DocumentParseResult:
        raise NotImplementedError

    def build_result(
        self,
        *,
        trace_id: str,
        asset: NormalizedDocumentAsset,
        text: str,
        pages: list[OCRPage] | None = None,
        tables: list[dict[str, Any]] | None = None,
        locations: list[DocumentLocation] | None = None,
        metadata: dict[str, Any] | None = None,
        provider: str | None = None,
        model: str | None = None,
        raw_response: dict[str, Any] | None = None,
    ) -> DocumentParseResult:
        return DocumentParseResult(
            trace_id=trace_id,
            asset_hash=asset.asset_hash,
            cache_key="",
            parser_name=self.parser_name,
            parser_version=self.parser_version,
            source_type=asset.source_type,
            source_value=asset.source_value,
            file_name=asset.file_name,
            file_type=asset.file_type,
            text=text,
            pages=pages or [],
            tables=tables or [],
            locations=locations or [],
            metadata=metadata or {},
            provider=provider,
            model=model,
            cache_hit=False,
            latency_ms=0,
            raw_response=raw_response,
        )


def decode_text_bytes(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("latin-1", errors="replace")


def normalize_text(value: str) -> str:
    lines = [line.strip() for line in value.replace("\r\n", "\n").split("\n")]
    collapsed: list[str] = []
    previous_blank = False
    for line in lines:
        if not line:
            if not previous_blank:
                collapsed.append("")
            previous_blank = True
            continue
        collapsed.append(line)
        previous_blank = False
    return "\n".join(collapsed).strip()
