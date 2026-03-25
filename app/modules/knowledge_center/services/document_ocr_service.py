from __future__ import annotations

from pathlib import Path

from app.core.config import OCRSettings
from app.runtime.tools import OCRTool, OCRToolRequest, OCRToolResult, ToolExecutor
from app.runtime.tools.ocr_tool import build_default_tool_executor

OCR_ELIGIBLE_EXTENSIONS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}


class DocumentOCRService:
    def __init__(
        self,
        executor: ToolExecutor,
        *,
        tool_name: str = OCRTool.name,
    ) -> None:
        self._executor = executor
        self._tool_name = tool_name

    def should_run_ocr(
        self,
        *,
        source_type: str,
        source_value: str,
        file_type: str | None = None,
    ) -> bool:
        if file_type in {"image", "pdf"}:
            return True
        if source_type != "file_path":
            return True
        return Path(source_value).suffix.lower() in OCR_ELIGIBLE_EXTENSIONS

    def extract_document(
        self,
        *,
        tenant_id: str,
        app_id: str,
        source_type: str,
        source_value: str,
        scene: str = "knowledge_ingest",
        file_type: str | None = None,
        provider: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> OCRToolResult:
        request = OCRToolRequest(
            tenant_id=tenant_id,
            app_id=app_id,
            scene=scene,
            source_type=source_type,
            source_value=source_value,
            file_type=file_type,
            provider=provider,
            metadata=dict(metadata or {}),
        )
        result = self._executor.execute(self._tool_name, request)
        return result

    def extract_text_for_ingest(
        self,
        *,
        tenant_id: str,
        app_id: str,
        source_type: str,
        source_value: str,
        scene: str = "knowledge_ingest",
        file_type: str | None = None,
        provider: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> str:
        result = self.extract_document(
            tenant_id=tenant_id,
            app_id=app_id,
            source_type=source_type,
            source_value=source_value,
            scene=scene,
            file_type=file_type,
            provider=provider,
            metadata=metadata,
        )
        return result.text


def build_document_ocr_service(
    settings: OCRSettings | None = None,
    *,
    executor: ToolExecutor | None = None,
) -> DocumentOCRService:
    executor = executor or build_default_tool_executor(settings)
    return DocumentOCRService(executor)
