from __future__ import annotations

import json
from pathlib import Path

from app.core.exceptions import DocumentParseCacheError
from app.modules.document_center.schemas import DocumentParseResult


class ParseCacheRepository:
    def __init__(self, cache_dir: str | Path) -> None:
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, cache_key: str) -> DocumentParseResult | None:
        path = self._cache_path(cache_key)
        if not path.exists():
            return None

        try:
            return DocumentParseResult.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise DocumentParseCacheError(
                f"Failed to read document parse cache '{cache_key}'."
            ) from exc

    def save(self, cache_key: str, result: DocumentParseResult) -> None:
        path = self._cache_path(cache_key)
        tmp_path = path.with_suffix(".tmp")
        try:
            payload = json.dumps(
                result.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            )
            tmp_path.write_text(payload, encoding="utf-8")
            tmp_path.replace(path)
        except OSError as exc:
            raise DocumentParseCacheError(
                f"Failed to write document parse cache '{cache_key}'."
            ) from exc

    def _cache_path(self, cache_key: str) -> Path:
        return self._cache_dir / f"{cache_key}.json"
