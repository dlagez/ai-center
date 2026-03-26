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


class PDFOCRBatchManifestEntry(BaseModel):
    batch_index: int
    page_range: list[int] = Field(default_factory=list)
    output_file: str
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    attempt_count: int = 0
    error_code: str | None = None


class PDFOCRCheckpointManifest(BaseModel):
    cache_key: str
    state: Literal["running", "completed", "failed"] = "running"
    parser_name: str
    parser_version: str
    provider: str | None = None
    file_name: str
    file_type: str
    asset_hash: str
    requested_page_range: list[int] | None = None
    target_pages: list[int] = Field(default_factory=list)
    batch_size: int
    batch_count: int
    completed_batch_count: int = 0
    created_at: str
    updated_at: str
    batches: list[PDFOCRBatchManifestEntry] = Field(default_factory=list)


class PDFOCRBatchProgress(BaseModel):
    state: Literal["running", "completed", "failed"] = "running"
    total_batches: int
    completed_batches: int = 0
    failed_batches: int = 0
    current_batch_index: int | None = None
    current_page_range: list[int] | None = None
    percent: float = 0.0
    updated_at: str


class PDFOCRBatchCheckpoint(BaseModel):
    batch_index: int
    page_range: list[int] = Field(default_factory=list)
    provider: str
    model: str | None = None
    attempt_count: int = 1
    started_at: str
    finished_at: str
    pages: list[OCRPage] = Field(default_factory=list)
    text: str
    usage: dict[str, Any] = Field(default_factory=dict)
    raw_response: dict[str, Any] | None = None


@dataclass(frozen=True)
class NormalizedDocumentAsset:
    source_type: str
    source_value: str
    file_name: str
    file_type: str
    content_bytes: bytes
    asset_hash: str
