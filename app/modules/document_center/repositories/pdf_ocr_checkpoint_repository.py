from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from app.core.exceptions import DocumentParseCacheError
from app.modules.document_center.schemas import (
    PDFOCRBatchCheckpoint,
    PDFOCRBatchProgress,
    PDFOCRCheckpointManifest,
)

ModelT = TypeVar("ModelT", bound=BaseModel)


class PDFOCRCheckpointRepository:
    def __init__(self, cache_dir: str | Path) -> None:
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def reset(self, cache_key: str) -> None:
        partial_dir = self.partial_dir(cache_key)
        if partial_dir.exists():
            shutil.rmtree(partial_dir, ignore_errors=True)

    def partial_dir(self, cache_key: str) -> Path:
        return self._cache_dir / f"{cache_key}.partial"

    def manifest_path(self, cache_key: str) -> Path:
        return self.partial_dir(cache_key) / "manifest.json"

    def progress_path(self, cache_key: str) -> Path:
        return self.partial_dir(cache_key) / "progress.json"

    def batches_dir(self, cache_key: str) -> Path:
        return self.partial_dir(cache_key) / "batches"

    def build_batch_output_file(self, batch_index: int, page_range: list[int]) -> str:
        return (
            f"batch-{batch_index:04d}-pages-{page_range[0]}-{page_range[-1]}.json"
        )

    def load_manifest(self, cache_key: str) -> PDFOCRCheckpointManifest | None:
        return self._read_model(self.manifest_path(cache_key), PDFOCRCheckpointManifest)

    def save_manifest(
        self,
        cache_key: str,
        manifest: PDFOCRCheckpointManifest,
    ) -> None:
        self._write_model(self.manifest_path(cache_key), manifest)

    def load_progress(self, cache_key: str) -> PDFOCRBatchProgress | None:
        return self._read_model(self.progress_path(cache_key), PDFOCRBatchProgress)

    def save_progress(self, cache_key: str, progress: PDFOCRBatchProgress) -> None:
        self._write_model(self.progress_path(cache_key), progress)

    def load_batch(
        self,
        cache_key: str,
        output_file: str,
    ) -> PDFOCRBatchCheckpoint | None:
        return self._read_model(
            self.batches_dir(cache_key) / output_file,
            PDFOCRBatchCheckpoint,
        )

    def save_batch(
        self,
        cache_key: str,
        output_file: str,
        batch: PDFOCRBatchCheckpoint,
    ) -> None:
        self._write_model(self.batches_dir(cache_key) / output_file, batch)

    def _read_model(self, path: Path, model_type: type[ModelT]) -> ModelT | None:
        if not path.exists():
            return None
        try:
            return model_type.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _write_model(self, path: Path, payload: BaseModel) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        try:
            serialized = json.dumps(
                payload.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            )
            tmp_path.write_text(serialized, encoding="utf-8")
            tmp_path.replace(path)
        except OSError as exc:
            raise DocumentParseCacheError(
                f"Failed to write PDF OCR checkpoint '{path.name}'."
            ) from exc
