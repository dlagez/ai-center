from __future__ import annotations

from typing import Any

from app.core.exceptions import RetrievalFilterError
from app.runtime.retrieval.schemas import RetrievalRequest


class RetrievalFilterBuilder:
    _RESERVED_FILTER_KEYS = ("tenant_id", "app_id", "knowledge_base_id")

    def build(self, request: RetrievalRequest) -> dict[str, Any]:
        filters = dict(request.filters)

        for key, value in (
            ("tenant_id", request.tenant_id),
            ("app_id", request.app_id),
            ("knowledge_base_id", request.knowledge_base_id),
        ):
            existing = filters.get(key)
            if existing is not None and not self._matches_existing_filter(existing, value):
                raise RetrievalFilterError(
                    f"Filter '{key}' conflicts with the scoped retrieval request."
                )
            filters[key] = value

        document_filter = self._merge_document_filter(
            request.document_ids,
            filters.pop("document_id", None),
        )
        if document_filter is not None:
            filters["document_id"] = document_filter

        return filters

    @staticmethod
    def _matches_existing_filter(existing: Any, expected: str) -> bool:
        if isinstance(existing, list):
            return expected in existing
        return existing == expected

    @staticmethod
    def _merge_document_filter(
        request_document_ids: list[str],
        existing_filter: Any,
    ) -> list[str] | None:
        if not request_document_ids and existing_filter is None:
            return None

        request_values = set(request_document_ids)
        existing_values = RetrievalFilterBuilder._to_string_set(existing_filter)

        if request_values and existing_values:
            return sorted(request_values & existing_values)
        if request_values:
            return sorted(request_values)
        return sorted(existing_values)

    @staticmethod
    def _to_string_set(value: Any) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, list):
            return {str(item) for item in value}
        return {str(value)}
