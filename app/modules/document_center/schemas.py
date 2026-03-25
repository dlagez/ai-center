from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.runtime.tools.schemas import OCRPage


class DocumentLocation(BaseModel):
    page_no: int | None = None
    row_index: int | None = None


class DocumentParseRequest(BaseModel):
    tenant_id: str
    app_id: str
    scene: str
    source_type: Literal["file_path", "url", "base64"]
    source_value: str
    file_name: str | None = None
    file_type: str | None = None
    parse_mode: Literal["text", "structured", "preview"] = "text"
    provider: str | None = None
    language_hints: list[str] = Field(default_factory=list)
    enable_layout: bool | None = None
    page_range: list[int] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentParseResult(BaseModel):
    trace_id: str
    asset_hash: str
    cache_key: str
    parser_name: str
    parser_version: str
    source_type: str
    source_value: str
    file_name: str
    file_type: str
    text: str
    pages: list[OCRPage] = Field(default_factory=list)
    tables: list[dict[str, Any]] = Field(default_factory=list)
    locations: list[DocumentLocation] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    provider: str | None = None
    model: str | None = None
    cache_hit: bool
    latency_ms: int
    raw_response: dict[str, Any] | None = None


@dataclass(frozen=True)
class NormalizedDocumentAsset:
    source_type: str
    source_value: str
    file_name: str
    file_type: str
    content_bytes: bytes
    asset_hash: str
