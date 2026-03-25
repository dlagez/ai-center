from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.modules.document_center.schemas import DocumentParseResult


class ChunkSourcePosition(BaseModel):
    page_no: int | None = None
    row_index: int | None = None
    block_id: str | None = None
    paragraph_id: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChunkingPolicyConfig(BaseModel):
    policy_name: str = "default"
    max_chars: int = 1200
    overlap_chars: int = 150
    split_by_heading: bool = True
    split_by_paragraph: bool = True
    keep_heading_prefix: bool = True

    @model_validator(mode="after")
    def validate_policy(self) -> "ChunkingPolicyConfig":
        if self.max_chars <= 0:
            raise ValueError("max_chars must be greater than 0.")
        if self.overlap_chars < 0:
            raise ValueError("overlap_chars must be at least 0.")
        if self.overlap_chars >= self.max_chars:
            raise ValueError("overlap_chars must be smaller than max_chars.")
        return self


class ChunkingRequest(BaseModel):
    tenant_id: str
    app_id: str
    document_id: str
    scene: str
    parsed_document: DocumentParseResult | None = None
    raw_text: str | None = None
    file_name: str | None = None
    file_type: str | None = None
    policy: ChunkingPolicyConfig | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_input(self) -> "ChunkingRequest":
        if self.parsed_document is None and not (self.raw_text or "").strip():
            raise ValueError("Either parsed_document or raw_text must be provided.")
        return self


class ChunkDocument(BaseModel):
    chunk_id: str
    document_id: str
    chunk_index: int
    text: str
    title_path: list[str] = Field(default_factory=list)
    page_range: list[int] = Field(default_factory=list)
    source_block_ids: list[str] = Field(default_factory=list)
    source_positions: list[ChunkSourcePosition] = Field(default_factory=list)
    policy_name: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChunkingResult(BaseModel):
    trace_id: str
    document_id: str
    total_chunks: int
    chunks: list[ChunkDocument] = Field(default_factory=list)
    policy_name: str
    source_type: str | None = None
    file_name: str | None = None
    file_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int
