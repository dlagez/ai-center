from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from numbers import Number
from typing import Any

from app.core.config import OCRSettings
from app.core.exceptions import OCRToolError
from app.modules.document_center.repositories.pdf_ocr_checkpoint_repository import (
    PDFOCRCheckpointRepository,
)
from app.modules.document_center.schemas import (
    DocumentParseRequest,
    NormalizedDocumentAsset,
    PDFOCRBatchCheckpoint,
    PDFOCRBatchManifestEntry,
    PDFOCRBatchProgress,
    PDFOCRCheckpointManifest,
)
from app.modules.document_center.services.ocr_execution_service import OCRExecutionService
from app.modules.document_center.services.pdf_batch_asset_service import (
    PDFBatchAssetService,
)
from app.observability.tracing import LangSmithTracer, get_default_langsmith_tracer
from app.runtime.tools.schemas import OCRLine, OCRPage, OCRProviderResponse


@dataclass(frozen=True)
class PDFOCRExecutionResult:
    response: OCRProviderResponse
    mode: str
    total_pages: int | None
    batch_count: int
    batch_page_ranges: list[list[int]]
    retry_count: int = 0
    retried_batch_count: int = 0
    resumed_batch_count: int = 0


class PDFOCRBatchingService:
    def __init__(
        self,
        settings: OCRSettings,
        *,
        checkpoint_repository: PDFOCRCheckpointRepository,
        batch_asset_service: PDFBatchAssetService,
        tracer: LangSmithTracer | None = None,
    ) -> None:
        self._settings = settings
        self._checkpoint_repository = checkpoint_repository
        self._batch_asset_service = batch_asset_service
        self._tracer = tracer or get_default_langsmith_tracer()

    def extract_text(
        self,
        *,
        request: DocumentParseRequest,
        asset: NormalizedDocumentAsset,
        trace_id: str,
        ocr_service: OCRExecutionService,
        cache_key: str | None,
        parser_name: str,
        parser_version: str,
    ) -> PDFOCRExecutionResult:
        target_pages = self._resolve_target_pages(
            asset.content_bytes,
            request.page_range,
        )
        provider_name = request.provider or ocr_service._settings.ocr_default_provider
        should_batch = self._should_use_batch_pipeline(
            target_pages=target_pages,
            requested_page_range=request.page_range,
            asset=asset,
            cache_key=cache_key,
        )
        manifest: PDFOCRCheckpointManifest | None = None
        batch_page_ranges: list[list[int]] = []

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
                "batching_enabled": should_batch,
                "batch_size": self._settings.ocr_pdf_batch_pages,
                "max_retries": self._settings.ocr_pdf_batch_max_retries,
            },
            metadata={
                "document_parse_trace_id": trace_id,
                "provider": provider_name,
                "file_name": asset.file_name,
                "cache_key": cache_key,
            },
        ) as root_run:
            try:
                if not should_batch:
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
                            "resumed_batch_count": 0,
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

                if not cache_key:
                    raise OCRToolError(
                        "PDF OCR batching requires a stable cache key for checkpointing."
                    )

                batch_page_ranges = self._build_batches(target_pages)
                manifest = self._prepare_manifest(
                    cache_key=cache_key,
                    parser_name=parser_name,
                    parser_version=parser_version,
                    provider_name=provider_name,
                    asset=asset,
                    requested_page_range=request.page_range,
                    target_pages=target_pages,
                    batch_page_ranges=batch_page_ranges,
                )
                self._save_progress(
                    cache_key=cache_key,
                    total_batches=len(batch_page_ranges),
                    completed_batches=manifest.completed_batch_count,
                    state=manifest.state,
                )

                recovered_batches = self._load_completed_batches(
                    cache_key=cache_key,
                    manifest=manifest,
                    provider_name=provider_name,
                )
                resumed_batch_count = len(recovered_batches)
                self._save_progress(
                    cache_key=cache_key,
                    total_batches=len(manifest.batches),
                    completed_batches=manifest.completed_batch_count,
                    state=manifest.state,
                )
                total_retry_count = 0
                retried_batch_count = 0

                for entry in manifest.batches:
                    if entry.batch_index in recovered_batches:
                        continue
                    checkpoint, retry_count = self._execute_batch_with_retry(
                        cache_key=cache_key,
                        request=request,
                        asset=asset,
                        trace_id=trace_id,
                        ocr_service=ocr_service,
                        batch_count=len(manifest.batches),
                        entry=entry,
                        provider_name=provider_name,
                    )
                    recovered_batches[entry.batch_index] = checkpoint
                    total_retry_count += retry_count
                    if retry_count > 0:
                        retried_batch_count += 1

                    entry.status = "completed"
                    entry.attempt_count = checkpoint.attempt_count
                    entry.error_code = None
                    manifest.completed_batch_count = len(recovered_batches)
                    manifest.updated_at = self._now_iso()
                    self._checkpoint_repository.save_manifest(cache_key, manifest)
                    self._save_progress(
                        cache_key=cache_key,
                        total_batches=len(manifest.batches),
                        completed_batches=manifest.completed_batch_count,
                        current_batch_index=entry.batch_index,
                        current_page_range=entry.page_range,
                    )

                merged_response = self._merge_checkpoint_batches(
                    [recovered_batches[index] for index in sorted(recovered_batches)]
                )
                manifest.state = "completed"
                manifest.completed_batch_count = len(recovered_batches)
                manifest.updated_at = self._now_iso()
                self._checkpoint_repository.save_manifest(cache_key, manifest)
                self._save_progress(
                    cache_key=cache_key,
                    total_batches=len(manifest.batches),
                    completed_batches=manifest.completed_batch_count,
                    state="completed",
                )
                root_run.end(
                    outputs={
                        "mode": "batched",
                        "batch_count": len(batch_page_ranges),
                        "retry_count": total_retry_count,
                        "retried_batch_count": retried_batch_count,
                        "resumed_batch_count": resumed_batch_count,
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
                    resumed_batch_count=resumed_batch_count,
                )
            except Exception as exc:
                if cache_key and manifest is not None:
                    manifest.state = "failed"
                    manifest.updated_at = self._now_iso()
                    self._checkpoint_repository.save_manifest(cache_key, manifest)
                if cache_key:
                    self._save_progress(
                        cache_key=cache_key,
                        total_batches=len(manifest.batches)
                        if manifest is not None
                        else len(batch_page_ranges),
                        completed_batches=manifest.completed_batch_count
                        if manifest is not None
                        else 0,
                        failed_batches=1,
                        state="failed",
                    )
                root_run.metadata["error_code"] = getattr(exc, "code", "unknown_error")
                root_run.end(error=exc)
                raise

    def _resolve_target_pages(
        self,
        content: bytes,
        requested_page_range: list[int] | None,
    ) -> list[int]:
        total_pages = self._batch_asset_service.infer_total_pages(content)
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

    def _should_use_batch_pipeline(
        self,
        *,
        target_pages: list[int],
        requested_page_range: list[int] | None,
        asset: NormalizedDocumentAsset,
        cache_key: str | None,
    ) -> bool:
        if not cache_key:
            return False
        if not target_pages:
            return False
        if not self._batch_asset_service.can_split(asset.content_bytes):
            return False
        if requested_page_range:
            return True
        if not self._settings.ocr_pdf_batch_enabled:
            return False
        if self._settings.ocr_pdf_batch_pages <= 0:
            return False
        if len(target_pages) < self._settings.ocr_pdf_batch_min_total_pages:
            return False
        return len(target_pages) > self._settings.ocr_pdf_batch_pages

    def _build_batches(self, target_pages: list[int]) -> list[list[int]]:
        batch_size = max(1, self._settings.ocr_pdf_batch_pages)
        return [
            target_pages[index : index + batch_size]
            for index in range(0, len(target_pages), batch_size)
        ]

    def _prepare_manifest(
        self,
        *,
        cache_key: str,
        parser_name: str,
        parser_version: str,
        provider_name: str,
        asset: NormalizedDocumentAsset,
        requested_page_range: list[int] | None,
        target_pages: list[int],
        batch_page_ranges: list[list[int]],
    ) -> PDFOCRCheckpointManifest:
        existing = self._checkpoint_repository.load_manifest(cache_key)
        if existing is not None and not self._is_manifest_compatible(
            existing=existing,
            parser_name=parser_name,
            parser_version=parser_version,
            provider_name=provider_name,
            asset=asset,
            requested_page_range=requested_page_range,
            target_pages=target_pages,
            batch_page_ranges=batch_page_ranges,
        ):
            self._checkpoint_repository.reset(cache_key)
            existing = None

        if existing is not None:
            existing.updated_at = self._now_iso()
            self._checkpoint_repository.save_manifest(cache_key, existing)
            return existing

        now = self._now_iso()
        manifest = PDFOCRCheckpointManifest(
            cache_key=cache_key,
            state="running",
            parser_name=parser_name,
            parser_version=parser_version,
            provider=provider_name,
            file_name=asset.file_name,
            file_type=asset.file_type,
            asset_hash=asset.asset_hash,
            requested_page_range=list(requested_page_range)
            if requested_page_range
            else None,
            target_pages=list(target_pages),
            batch_size=max(1, self._settings.ocr_pdf_batch_pages),
            batch_count=len(batch_page_ranges),
            completed_batch_count=0,
            created_at=now,
            updated_at=now,
            batches=[
                PDFOCRBatchManifestEntry(
                    batch_index=index,
                    page_range=list(page_range),
                    output_file=self._checkpoint_repository.build_batch_output_file(
                        index, page_range
                    ),
                )
                for index, page_range in enumerate(batch_page_ranges, start=1)
            ],
        )
        self._checkpoint_repository.save_manifest(cache_key, manifest)
        return manifest

    def _is_manifest_compatible(
        self,
        *,
        existing: PDFOCRCheckpointManifest,
        parser_name: str,
        parser_version: str,
        provider_name: str,
        asset: NormalizedDocumentAsset,
        requested_page_range: list[int] | None,
        target_pages: list[int],
        batch_page_ranges: list[list[int]],
    ) -> bool:
        if existing.parser_name != parser_name:
            return False
        if existing.parser_version != parser_version:
            return False
        if existing.provider != provider_name:
            return False
        if existing.asset_hash != asset.asset_hash:
            return False
        if existing.requested_page_range != (
            list(requested_page_range) if requested_page_range else None
        ):
            return False
        if existing.target_pages != list(target_pages):
            return False
        if existing.batch_size != max(1, self._settings.ocr_pdf_batch_pages):
            return False
        if existing.batch_count != len(batch_page_ranges):
            return False
        if len(existing.batches) != len(batch_page_ranges):
            return False
        return all(
            entry.page_range == list(page_range)
            for entry, page_range in zip(existing.batches, batch_page_ranges)
        )

    def _load_completed_batches(
        self,
        *,
        cache_key: str,
        manifest: PDFOCRCheckpointManifest,
        provider_name: str,
    ) -> dict[int, PDFOCRBatchCheckpoint]:
        recovered: dict[int, PDFOCRBatchCheckpoint] = {}
        for entry in manifest.batches:
            checkpoint = self._checkpoint_repository.load_batch(cache_key, entry.output_file)
            if not self._is_checkpoint_valid(
                checkpoint=checkpoint,
                page_range=entry.page_range,
                provider_name=provider_name,
            ):
                entry.status = "pending"
                continue
            entry.status = "completed"
            entry.attempt_count = checkpoint.attempt_count
            entry.error_code = None
            recovered[entry.batch_index] = checkpoint

        manifest.completed_batch_count = len(recovered)
        manifest.updated_at = self._now_iso()
        self._checkpoint_repository.save_manifest(cache_key, manifest)
        return recovered

    def _is_checkpoint_valid(
        self,
        *,
        checkpoint: PDFOCRBatchCheckpoint | None,
        page_range: list[int],
        provider_name: str,
    ) -> bool:
        if checkpoint is None:
            return False
        if checkpoint.page_range != list(page_range):
            return False
        if checkpoint.provider != provider_name:
            return False
        if not checkpoint.pages and not checkpoint.text.strip():
            return False
        return all(page.page_no in page_range for page in checkpoint.pages)

    def _execute_batch_with_retry(
        self,
        *,
        cache_key: str,
        request: DocumentParseRequest,
        asset: NormalizedDocumentAsset,
        trace_id: str,
        ocr_service: OCRExecutionService,
        batch_count: int,
        entry: PDFOCRBatchManifestEntry,
        provider_name: str,
    ) -> tuple[PDFOCRBatchCheckpoint, int]:
        max_attempts = max(1, self._settings.ocr_pdf_batch_max_retries + 1)
        delay_seconds = max(0, self._settings.ocr_pdf_batch_retry_delay_ms) / 1000
        retry_count = 0
        started_at_perf = time.perf_counter()
        started_at = self._now_iso()
        batch_request = request.model_copy(
            update={
                "page_range": None,
                "metadata": {
                    **request.metadata,
                    "pdf_batch_index": entry.batch_index,
                    "pdf_batch_page_range": list(entry.page_range),
                },
            }
        )
        batch_asset = self._batch_asset_service.build_batch_asset(
            asset=asset,
            page_range=entry.page_range,
            batch_index=entry.batch_index,
        )

        with self._tracer.trace(
            name="pdf.ocr.batch",
            run_type="tool",
            pipeline_kind="ingest",
            scene=request.scene,
            inputs={
                "batch_index": entry.batch_index,
                "batch_count": batch_count,
                "page_range": list(entry.page_range),
                "page_count": len(entry.page_range),
                "provider": provider_name,
                "max_attempts": max_attempts,
            },
            metadata={
                "document_parse_trace_id": trace_id,
                "batch_index": entry.batch_index,
                "batch_count": batch_count,
                "page_range": list(entry.page_range),
                "provider": provider_name,
            },
        ) as batch_run:
            last_error: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    response = ocr_service.extract_text(
                        request=batch_request,
                        asset=batch_asset,
                        trace_id=f"{trace_id}:batch:{entry.batch_index}:attempt:{attempt}",
                        file_type="pdf",
                    )
                    normalized_pages = self._normalize_pages(entry.page_range, response.pages)
                    normalized_text = (
                        "\n\n".join(page.text for page in normalized_pages if page.text).strip()
                        or response.text.strip()
                    )
                    checkpoint = PDFOCRBatchCheckpoint(
                        batch_index=entry.batch_index,
                        page_range=list(entry.page_range),
                        provider=response.provider,
                        model=response.model,
                        attempt_count=attempt,
                        started_at=started_at,
                        finished_at=self._now_iso(),
                        pages=normalized_pages,
                        text=normalized_text,
                        usage=dict(response.usage),
                        raw_response=response.raw_response,
                    )
                    self._checkpoint_repository.save_batch(
                        cache_key,
                        entry.output_file,
                        checkpoint,
                    )
                    batch_run.metadata.update(
                        {
                            "attempt_count": attempt,
                            "retry_count": retry_count,
                        }
                    )
                    batch_run.end(
                        outputs={
                            "batch_index": entry.batch_index,
                            "page_range": list(entry.page_range),
                            "attempt_count": attempt,
                            "retry_count": retry_count,
                            "page_count": len(entry.page_range),
                            "provider": response.provider,
                            "model": response.model,
                            "latency_ms": int(
                                (time.perf_counter() - started_at_perf) * 1000
                            ),
                        }
                    )
                    return checkpoint, retry_count
                except Exception as exc:
                    last_error = exc
                    entry.status = "failed"
                    entry.attempt_count = attempt
                    entry.error_code = getattr(exc, "code", "unknown_error")
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

    def _merge_checkpoint_batches(
        self,
        checkpoints: list[PDFOCRBatchCheckpoint],
    ) -> OCRProviderResponse:
        providers = [checkpoint.provider for checkpoint in checkpoints if checkpoint.provider]
        models = [checkpoint.model for checkpoint in checkpoints if checkpoint.model]

        merged_pages: list[OCRPage] = []
        merged_text_parts: list[str] = []
        merged_usage: dict[str, Any] = {}
        raw_batches: list[dict[str, Any]] = []

        for checkpoint in checkpoints:
            if checkpoint.pages:
                merged_pages.extend(checkpoint.pages)
            elif checkpoint.text.strip():
                merged_text_parts.append(checkpoint.text.strip())
            self._merge_usage(merged_usage, checkpoint.usage)
            raw_batches.append(
                {
                    "batch_index": checkpoint.batch_index,
                    "page_range": list(checkpoint.page_range),
                    "provider": checkpoint.provider,
                    "model": checkpoint.model,
                    "attempt_count": checkpoint.attempt_count,
                    "usage": dict(checkpoint.usage),
                    "raw_response": checkpoint.raw_response,
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
                "batch_size": max(1, self._settings.ocr_pdf_batch_pages),
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

    def _save_progress(
        self,
        *,
        cache_key: str,
        total_batches: int,
        completed_batches: int,
        failed_batches: int = 0,
        current_batch_index: int | None = None,
        current_page_range: list[int] | None = None,
        state: str = "running",
    ) -> None:
        progress = PDFOCRBatchProgress(
            state=state,  # type: ignore[arg-type]
            total_batches=total_batches,
            completed_batches=completed_batches,
            failed_batches=failed_batches,
            current_batch_index=current_batch_index,
            current_page_range=list(current_page_range)
            if current_page_range
            else None,
            percent=round((completed_batches / total_batches) * 100, 2)
            if total_batches > 0
            else 0.0,
            updated_at=self._now_iso(),
        )
        self._checkpoint_repository.save_progress(cache_key, progress)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
