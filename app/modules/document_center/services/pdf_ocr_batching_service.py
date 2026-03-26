from __future__ import annotations

import re
import time
from dataclasses import dataclass
from numbers import Number
from typing import Any

from app.core.config import OCRSettings
from app.core.exceptions import OCRToolError
from app.modules.document_center.schemas import DocumentParseRequest, NormalizedDocumentAsset
from app.modules.document_center.services.ocr_execution_service import OCRExecutionService
from app.observability.tracing import LangSmithTracer, get_default_langsmith_tracer
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
    retry_count: int = 0
    retried_batch_count: int = 0


class PDFOCRBatchingService:
    def __init__(
        self,
        settings: OCRSettings,
        *,
        tracer: LangSmithTracer | None = None,
    ) -> None:
        self._settings = settings
        self._tracer = tracer or get_default_langsmith_tracer()

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
        provider_name = request.provider or ocr_service._settings.ocr_default_provider
        with self._tracer.trace(
            name="pdf.ocr",
            run_type="chain",
            pipeline_kind="ingest",
            scene=request.scene,
            inputs={
                "source_type": request.source_type,
                "file_name": asset.file_name,
                "file_type": asset.file_type,
                "requested_page_range": list(request.page_range)
                if request.page_range
                else None,
                "target_page_count": len(target_pages) or None,
                "batching_enabled": self._settings.ocr_pdf_batch_enabled,
                "batch_size": self._settings.ocr_pdf_batch_pages,
                "max_retries": self._settings.ocr_pdf_batch_max_retries,
            },
            metadata={
                "document_parse_trace_id": trace_id,
                "provider": provider_name,
                "file_name": asset.file_name,
            },
        ) as root_run:
            try:
                if not self._should_batch(target_pages):
                    response = ocr_service.extract_text(
                        request=request,
                        asset=asset,
                        trace_id=trace_id,
                        file_type="pdf",
                    )
                    root_run.end(
                        outputs={
                            "mode": "single",
                            "batch_count": 1,
                            "retry_count": 0,
                            "total_pages": len(target_pages) or None,
                        }
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
                batch_responses: list[tuple[list[int], OCRProviderResponse, int]] = []
                total_retry_count = 0
                retried_batch_count = 0
                for index, page_range in enumerate(batch_page_ranges, start=1):
                    batch_request = request.model_copy(update={"page_range": page_range})
                    batch_response, retry_count = self._execute_batch_with_retry(
                        request=batch_request,
                        asset=asset,
                        trace_id=trace_id,
                        ocr_service=ocr_service,
                        batch_index=index,
                        batch_count=len(batch_page_ranges),
                        page_range=page_range,
                        provider_name=provider_name,
                    )
                    batch_responses.append((page_range, batch_response, retry_count))
                    total_retry_count += retry_count
                    if retry_count > 0:
                        retried_batch_count += 1

                merged_response = self._merge_batch_responses(
                    batch_responses,
                    batch_size=self._settings.ocr_pdf_batch_pages,
                )
                root_run.end(
                    outputs={
                        "mode": "batched",
                        "batch_count": len(batch_page_ranges),
                        "retry_count": total_retry_count,
                        "retried_batch_count": retried_batch_count,
                        "total_pages": len(target_pages),
                    }
                )
                return PDFOCRExecutionResult(
                    response=merged_response,
                    mode="batched",
                    total_pages=len(target_pages),
                    batch_count=len(batch_page_ranges),
                    batch_page_ranges=batch_page_ranges,
                    retry_count=total_retry_count,
                    retried_batch_count=retried_batch_count,
                )
            except Exception as exc:
                root_run.metadata["error_code"] = getattr(exc, "code", "unknown_error")
                root_run.end(error=exc)
                raise

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

    def _execute_batch_with_retry(
        self,
        *,
        request: DocumentParseRequest,
        asset: NormalizedDocumentAsset,
        trace_id: str,
        ocr_service: OCRExecutionService,
        batch_index: int,
        batch_count: int,
        page_range: list[int],
        provider_name: str,
    ) -> tuple[OCRProviderResponse, int]:
        max_attempts = max(1, self._settings.ocr_pdf_batch_max_retries + 1)
        delay_seconds = max(0, self._settings.ocr_pdf_batch_retry_delay_ms) / 1000
        retry_count = 0
        started_at = time.perf_counter()

        with self._tracer.trace(
            name="pdf.ocr.batch",
            run_type="tool",
            pipeline_kind="ingest",
            scene=request.scene,
            inputs={
                "batch_index": batch_index,
                "batch_count": batch_count,
                "page_range": list(page_range),
                "page_count": len(page_range),
                "provider": provider_name,
                "max_attempts": max_attempts,
            },
            metadata={
                "document_parse_trace_id": trace_id,
                "batch_index": batch_index,
                "batch_count": batch_count,
                "page_range": list(page_range),
                "provider": provider_name,
            },
        ) as batch_run:
            last_error: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    response = ocr_service.extract_text(
                        request=request,
                        asset=asset,
                        trace_id=f"{trace_id}:batch:{batch_index}:attempt:{attempt}",
                        file_type="pdf",
                    )
                    batch_run.metadata.update(
                        {
                            "attempt_count": attempt,
                            "retry_count": retry_count,
                        }
                    )
                    batch_run.end(
                        outputs={
                            "batch_index": batch_index,
                            "page_range": list(page_range),
                            "attempt_count": attempt,
                            "retry_count": retry_count,
                            "page_count": len(page_range),
                            "provider": response.provider,
                            "model": response.model,
                            "latency_ms": int(
                                (time.perf_counter() - started_at) * 1000
                            ),
                        }
                    )
                    return response, retry_count
                except Exception as exc:
                    last_error = exc
                    is_retryable = getattr(exc, "retryable", False)
                    if attempt >= max_attempts or not is_retryable:
                        batch_run.metadata.update(
                            {
                                "attempt_count": attempt,
                                "retry_count": retry_count,
                                "error_code": getattr(exc, "code", "unknown_error"),
                            }
                        )
                        batch_run.end(error=exc)
                        raise
                    retry_count += 1
                    batch_run.metadata["retry_count"] = retry_count
                    if delay_seconds > 0:
                        time.sleep(delay_seconds)

            if last_error is not None:
                raise last_error
            raise OCRToolError("PDF OCR batch failed without an explicit error.")

    def _merge_batch_responses(
        self,
        batch_responses: list[tuple[list[int], OCRProviderResponse, int]],
        *,
        batch_size: int,
    ) -> OCRProviderResponse:
        providers = [
            response.provider
            for _, response, _ in batch_responses
            if response.provider
        ]
        models = [response.model for _, response, _ in batch_responses if response.model]

        merged_pages: list[OCRPage] = []
        merged_text_parts: list[str] = []
        merged_usage: dict[str, Any] = {}
        raw_batches: list[dict[str, Any]] = []

        for batch_index, (page_range, response, retry_count) in enumerate(
            batch_responses,
            start=1,
        ):
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
                    "retry_count": retry_count,
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
