from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class OCRLine(BaseModel):
    text: str
    page_no: int | None = None
    bbox: list[float] | None = None
    confidence: float | None = None


class OCRPage(BaseModel):
    page_no: int
    text: str
    lines: list[OCRLine] = Field(default_factory=list)


class OCRProviderResponse(BaseModel):
    provider: str
    model: str | None = None
    text: str
    pages: list[OCRPage] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)
    raw_response: dict[str, Any] | None = None


class OCRToolRequest(BaseModel):
    tenant_id: str
    app_id: str
    scene: str
    source_type: Literal["file_path", "url", "base64"]
    source_value: str
    file_type: Literal["image", "pdf"] | None = None
    provider: str | None = None
    language_hints: list[str] = Field(default_factory=list)
    enable_layout: bool | None = None
    page_range: list[int] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OCRToolResult(BaseModel):
    trace_id: str
    provider: str
    model: str | None = None
    source_type: str
    source_value: str
    text: str
    pages: list[OCRPage] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int
    raw_response: dict[str, Any] | None = None
