from __future__ import annotations

import re
from dataclasses import dataclass
from numbers import Number
from typing import Any

from app.core.config import OCRSettings
from app.modules.document_center.schemas import DocumentParseRequest, NormalizedDocumentAsset
from app.modules.document_center.services.ocr_execution_service import OCRExecutionService
from app.runtime.tools.schemas import OCRLine, OCRPage, OCRProviderResponse

_PAGE_COUNT_PATTERN = re.compile(br"/Count\s+(\d+)")
_PAGE_OBJECT_PATTERN = re.compile(br"/Type\s*/Page\b")


@dataclass(frozen=True)
class PDFOCRExecutionResult:
    response: OCRProviderResponse
    mode: str
    total_pages: int | None
    batch_count: int
    batch_page_ranges: list[list[int]]


class PDFOCRBatchingService:
    def __init__(self, settings: OCRSettings) -> None:
        self._settings = settings

    def extract_text(
        self,
        *,
        request: DocumentParseRequest,
        asset: NormalizedDocumentAsset,
        trace_id: str,
        ocr_service: OCRExecutionService,
    ) -> PDFOCRExecutionResult:
        target_pages = self._resolve_target_pages(
            asset.content_bytes,
            request.page_range,
        )
        if not self._should_batch(target_pages):
            response = ocr_service.extract_text(
                request=request,
                asset=asset,
                trace_id=trace_id,
                file_type="pdf",
            )
            return PDFOCRExecutionResult(
                response=response,
                mode="single",
                total_pages=len(target_pages) or None,
                batch_count=1,
                batch_page_ranges=[list(request.page_range)]
                if request.page_range
                else ([] if not target_pages else [target_pages]),
            )

        batch_page_ranges = self._build_batches(target_pages)
        batch_responses: list[tuple[list[int], OCRProviderResponse]] = []
        for index, page_range in enumerate(batch_page_ranges, start=1):
            batch_request = request.model_copy(update={"page_range": page_range})
            batch_response = ocr_service.extract_text(
                request=batch_request,
                asset=asset,
                trace_id=f"{trace_id}:batch:{index}",
                file_type="pdf",
            )
            batch_responses.append((page_range, batch_response))

        merged_response = self._merge_batch_responses(
            batch_responses,
            batch_size=self._settings.ocr_pdf_batch_pages,
        )
        return PDFOCRExecutionResult(
            response=merged_response,
            mode="batched",
            total_pages=len(target_pages),
            batch_count=len(batch_page_ranges),
            batch_page_ranges=batch_page_ranges,
        )

    def _resolve_target_pages(
        self,
        content: bytes,
        requested_page_range: list[int] | None,
    ) -> list[int]:
        total_pages = self._infer_total_pages(content)
        if requested_page_range:
            requested_pages = sorted(
                {int(page_no) for page_no in requested_page_range if int(page_no) > 0}
            )
            if total_pages is None:
                return requested_pages
            return [page_no for page_no in requested_pages if page_no <= total_pages]
        if total_pages is None:
            return []
        return list(range(1, total_pages + 1))

    def _infer_total_pages(self, content: bytes) -> int | None:
        count_candidates = [
            int(match.group(1))
            for match in _PAGE_COUNT_PATTERN.finditer(content)
            if int(match.group(1)) > 0
        ]
        if count_candidates:
            return max(count_candidates)

        page_object_count = len(_PAGE_OBJECT_PATTERN.findall(content))
        return page_object_count or None

    def _should_batch(self, target_pages: list[int]) -> bool:
        if not self._settings.ocr_pdf_batch_enabled:
            return False
        if self._settings.ocr_pdf_batch_pages <= 0:
            return False
        if len(target_pages) < self._settings.ocr_pdf_batch_min_total_pages:
            return False
        return len(target_pages) > self._settings.ocr_pdf_batch_pages

    def _build_batches(self, target_pages: list[int]) -> list[list[int]]:
        batch_size = self._settings.ocr_pdf_batch_pages
        return [
            target_pages[index : index + batch_size]
            for index in range(0, len(target_pages), batch_size)
        ]

    def _merge_batch_responses(
        self,
        batch_responses: list[tuple[list[int], OCRProviderResponse]],
        *,
        batch_size: int,
    ) -> OCRProviderResponse:
        providers = [response.provider for _, response in batch_responses if response.provider]
        models = [response.model for _, response in batch_responses if response.model]

        merged_pages: list[OCRPage] = []
        merged_text_parts: list[str] = []
        merged_usage: dict[str, Any] = {}
        raw_batches: list[dict[str, Any]] = []

        for batch_index, (page_range, response) in enumerate(batch_responses, start=1):
            normalized_pages = self._normalize_pages(page_range, response.pages)
            if normalized_pages:
                merged_pages.extend(normalized_pages)
            elif response.text.strip():
                merged_text_parts.append(response.text.strip())

            self._merge_usage(merged_usage, response.usage)
            raw_batches.append(
                {
                    "batch_index": batch_index,
                    "page_range": list(page_range),
                    "provider": response.provider,
                    "model": response.model,
                    "usage": dict(response.usage),
                    "raw_response": response.raw_response,
                }
            )

        merged_pages.sort(key=lambda page: page.page_no)
        text = "\n\n".join(page.text for page in merged_pages if page.text).strip()
        if not text:
            text = "\n\n".join(part for part in merged_text_parts if part).strip()

        return OCRProviderResponse(
            provider=providers[0] if providers else "",
            model=models[0] if models else None,
            text=text,
            pages=merged_pages,
            usage=merged_usage,
            raw_response={
                "mode": "batched_ocr",
                "batch_size": batch_size,
                "batches": raw_batches,
            },
        )

    def _normalize_pages(
        self,
        page_range: list[int],
        pages: list[OCRPage],
    ) -> list[OCRPage]:
        if not pages:
            return []

        returned_page_numbers = [page.page_no for page in pages]
        should_reindex_by_order = False
        if len(pages) == len(page_range):
            expected_relative = list(range(1, len(pages) + 1))
            if returned_page_numbers == expected_relative and returned_page_numbers != page_range:
                should_reindex_by_order = True
            elif any(page_no not in page_range for page_no in returned_page_numbers):
                should_reindex_by_order = True

        normalized_pages: list[OCRPage] = []
        for index, page in enumerate(pages):
            page_no = page.page_no
            if index < len(page_range) and (
                should_reindex_by_order or page_no not in page_range
            ):
                page_no = page_range[index]

            normalized_lines = [
                self._normalize_line_page_no(
                    line,
                    target_page_no=page_no,
                    requested_page_range=page_range,
                    force=should_reindex_by_order,
                )
                for line in page.lines
            ]
            normalized_pages.append(
                page.model_copy(
                    update={
                        "page_no": page_no,
                        "lines": normalized_lines,
                    }
                )
            )
        return normalized_pages

    @staticmethod
    def _normalize_line_page_no(
        line: OCRLine,
        *,
        target_page_no: int,
        requested_page_range: list[int],
        force: bool,
    ) -> OCRLine:
        if force or line.page_no is None or line.page_no not in requested_page_range:
            return line.model_copy(update={"page_no": target_page_no})
        return line

    @classmethod
    def _merge_usage(cls, merged_usage: dict[str, Any], usage: dict[str, Any]) -> None:
        for key, value in usage.items():
            current_value = merged_usage.get(key)
            if isinstance(value, dict):
                nested_target: dict[str, Any]
                if isinstance(current_value, dict):
                    nested_target = current_value
                else:
                    nested_target = {}
                    merged_usage[key] = nested_target
                cls._merge_usage(nested_target, value)
                continue
            if isinstance(value, Number) and not isinstance(value, bool):
                base_value = current_value if isinstance(current_value, Number) else 0
                merged_usage[key] = base_value + value
                continue
            if key not in merged_usage:
                merged_usage[key] = value
                continue
            if merged_usage[key] == value:
                continue
            existing = merged_usage[key]
            if isinstance(existing, list):
                if value not in existing:
                    existing.append(value)
                continue
            if existing != value:
                merged_usage[key] = [existing, value]
