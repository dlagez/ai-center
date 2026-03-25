from __future__ import annotations

import hashlib
import json
import threading
from contextlib import contextmanager
from typing import Iterator

from app.core.config import DocumentParseSettings
from app.modules.document_center.repositories import ParseCacheRepository
from app.modules.document_center.schemas import (
    DocumentParseRequest,
    DocumentParseResult,
    NormalizedDocumentAsset,
)


class ParseCacheService:
    def __init__(
        self,
        repository: ParseCacheRepository,
        *,
        settings: DocumentParseSettings,
    ) -> None:
        self._repository = repository
        self._settings = settings
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def build_cache_key(
        self,
        *,
        asset: NormalizedDocumentAsset,
        request: DocumentParseRequest,
        parser_name: str,
        parser_version: str,
    ) -> str:
        payload = {
            "asset_hash": asset.asset_hash,
            "file_type": asset.file_type,
            "parse_mode": request.parse_mode,
            "parser_name": parser_name,
            "parser_version": parser_version,
            "provider": request.provider,
            "language_hints": list(request.language_hints),
            "enable_layout": request.enable_layout,
            "page_range": request.page_range,
        }
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        )
        return digest.hexdigest()

    def get(self, cache_key: str) -> DocumentParseResult | None:
        if not self._settings.document_parse_enable_cache:
            return None
        return self._repository.get(cache_key)

    def save(self, cache_key: str, result: DocumentParseResult) -> None:
        if not self._settings.document_parse_enable_cache:
            return
        self._repository.save(cache_key, result)

    @contextmanager
    def acquire(self, cache_key: str) -> Iterator[None]:
        with self._locks_guard:
            lock = self._locks.setdefault(cache_key, threading.Lock())
        lock.acquire()
        try:
            yield
        finally:
            lock.release()
