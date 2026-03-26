from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.modules.document_center import (  # noqa: E402
    DocumentParseRequest,
    build_document_parse_service,
)
from app.modules.document_center.repositories.pdf_ocr_checkpoint_repository import (  # noqa: E402
    PDFOCRCheckpointRepository,
)
from app.observability.tracing import get_default_langsmith_tracer  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Smoke-test document parsing and report whether PDF OCR used batch mode.",
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--file",
        help="Local file path to parse, for example D:\\docs\\sample.pdf",
    )
    source_group.add_argument(
        "--url",
        help="HTTP or HTTPS document URL to parse.",
    )
    source_group.add_argument(
        "--base64",
        help="Base64-encoded file content to parse directly.",
    )

    parser.add_argument("--tenant-id", default="demo-tenant")
    parser.add_argument("--app-id", default="demo-app")
    parser.add_argument("--scene", default="knowledge_ingest")
    parser.add_argument("--provider", help="Optional OCR provider override.")
    parser.add_argument("--file-name", help="Optional override for the file name.")
    parser.add_argument("--file-type", help="Optional override for the file type.")
    parser.add_argument(
        "--parse-mode",
        default="text",
        choices=["text", "structured", "preview"],
    )
    parser.add_argument(
        "--page-range",
        help="Optional page range list such as 1,2,3 or 11-20.",
    )
    parser.add_argument(
        "--enable-layout",
        action="store_true",
        help="Force enable OCR layout parsing.",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Delete the final parse cache and partial checkpoint directory before parsing.",
    )
    parser.add_argument(
        "--show-text-chars",
        type=int,
        default=400,
        help="Number of parsed text characters to preview in non-JSON mode.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the parse result and checkpoint summary as JSON.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        payload = run_smoke(args)
    except Exception as exc:
        print(f"Document parse smoke run failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print_summary(
        payload["result"],
        payload["checkpoint"],
        show_text_chars=args.show_text_chars,
    )
    return 0


def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    service = build_document_parse_service()
    try:
        request = build_request(args)
        asset = service._file_identity_service.normalize(request)
        parser = service._parser_router_service.resolve(asset)
        cache_key = service._parse_cache_service.build_cache_key(
            asset=asset,
            request=request,
            parser_name=parser.parser_name,
            parser_version=parser.parser_version,
        )

        checkpoint_repository = PDFOCRCheckpointRepository(
            service._parse_cache_service._settings.document_parse_cache_dir
        )

        if args.clear_cache:
            clear_parse_cache(
                cache_dir=Path(service._parse_cache_service._settings.document_parse_cache_dir),
                cache_key=cache_key,
                checkpoint_repository=checkpoint_repository,
            )

        result = service.parse(request)
        checkpoint_summary = collect_checkpoint_summary(
            cache_dir=Path(service._parse_cache_service._settings.document_parse_cache_dir),
            cache_key=cache_key,
            checkpoint_repository=checkpoint_repository,
        )
        return {
            "request": request.model_dump(mode="json"),
            "result": result.model_dump(mode="json"),
            "checkpoint": checkpoint_summary,
        }
    finally:
        get_default_langsmith_tracer().flush()


def build_request(args: argparse.Namespace) -> DocumentParseRequest:
    source_type, source_value, inferred_file_name = resolve_source(args)
    return DocumentParseRequest(
        tenant_id=args.tenant_id,
        app_id=args.app_id,
        scene=args.scene,
        source_type=source_type,
        source_value=source_value,
        file_name=args.file_name or inferred_file_name,
        file_type=args.file_type,
        parse_mode=args.parse_mode,
        provider=args.provider,
        enable_layout=True if args.enable_layout else None,
        page_range=parse_page_range(args.page_range),
    )


def resolve_source(args: argparse.Namespace) -> tuple[str, str, str | None]:
    if args.file:
        path = Path(args.file).expanduser().resolve()
        return "file_path", str(path), path.name
    if args.url:
        url_path = Path(args.url.split("?", 1)[0])
        inferred_name = url_path.name or None
        return "url", args.url, inferred_name
    return "base64", args.base64, args.file_name


def parse_page_range(raw_value: str | None) -> list[int] | None:
    if not raw_value:
        return None
    pages: list[int] = []
    for part in raw_value.split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            start = int(start_text.strip())
            end = int(end_text.strip())
            if end < start:
                start, end = end, start
            pages.extend(range(start, end + 1))
        else:
            pages.append(int(token))
    normalized = sorted({page for page in pages if page > 0})
    return normalized or None


def clear_parse_cache(
    *,
    cache_dir: Path,
    cache_key: str,
    checkpoint_repository: PDFOCRCheckpointRepository,
) -> None:
    final_cache_path = cache_dir / f"{cache_key}.json"
    if final_cache_path.exists():
        final_cache_path.unlink()
    partial_dir = checkpoint_repository.partial_dir(cache_key)
    if partial_dir.exists():
        shutil.rmtree(partial_dir, ignore_errors=True)


def collect_checkpoint_summary(
    *,
    cache_dir: Path,
    cache_key: str,
    checkpoint_repository: PDFOCRCheckpointRepository,
) -> dict[str, Any]:
    final_cache_path = cache_dir / f"{cache_key}.json"
    partial_dir = checkpoint_repository.partial_dir(cache_key)
    manifest = checkpoint_repository.load_manifest(cache_key)
    progress = checkpoint_repository.load_progress(cache_key)
    batch_dir = checkpoint_repository.batches_dir(cache_key)
    batch_files = sorted(path.name for path in batch_dir.glob("*.json")) if batch_dir.exists() else []

    return {
        "cache_key": cache_key,
        "cache_dir": str(cache_dir),
        "final_cache_path": str(final_cache_path),
        "final_cache_exists": final_cache_path.exists(),
        "partial_dir": str(partial_dir),
        "partial_dir_exists": partial_dir.exists(),
        "manifest_exists": manifest is not None,
        "manifest": manifest.model_dump(mode="json") if manifest is not None else None,
        "progress_exists": progress is not None,
        "progress": progress.model_dump(mode="json") if progress is not None else None,
        "batch_json_count": len(batch_files),
        "batch_json_files": batch_files,
    }


def print_summary(
    result: dict[str, Any],
    checkpoint: dict[str, Any],
    *,
    show_text_chars: int,
) -> None:
    metadata = result.get("metadata") or {}
    pages = result.get("pages") or []
    text = result.get("text") or ""

    print("Parse")
    print(f"  parser: {result.get('parser_name')}@{result.get('parser_version')}")
    print(f"  file_name: {result.get('file_name')}")
    print(f"  file_type: {result.get('file_type')}")
    print(f"  cache_key: {result.get('cache_key')}")
    print(f"  cache_hit: {result.get('cache_hit')}")
    print(f"  latency_ms: {result.get('latency_ms')}")
    print(f"  strategy: {metadata.get('strategy')}")
    print(f"  provider: {result.get('provider')}")
    print(f"  model: {result.get('model')}")
    print(f"  page_count: {len(pages)}")
    print(f"  location_count: {len(result.get('locations') or [])}")
    print(f"  text_length: {len(text)}")

    if metadata.get("strategy") == "ocr":
        print("OCR")
        print(f"  mode: {metadata.get('ocr_mode')}")
        print(f"  batch_count: {metadata.get('ocr_batch_count')}")
        print(f"  total_pages: {metadata.get('ocr_total_pages')}")
        print(f"  retry_count: {metadata.get('ocr_retry_count')}")
        print(f"  retried_batch_count: {metadata.get('ocr_retried_batch_count')}")
        print(f"  resumed_batch_count: {metadata.get('ocr_resumed_batch_count')}")

    print("Checkpoint")
    print(f"  final_cache_exists: {checkpoint.get('final_cache_exists')}")
    print(f"  partial_dir_exists: {checkpoint.get('partial_dir_exists')}")
    print(f"  manifest_exists: {checkpoint.get('manifest_exists')}")
    print(f"  progress_exists: {checkpoint.get('progress_exists')}")
    print(f"  batch_json_count: {checkpoint.get('batch_json_count')}")

    progress = checkpoint.get("progress") or {}
    if progress:
        print(
            "  progress: "
            f"{progress.get('completed_batches')}/{progress.get('total_batches')} "
            f"state={progress.get('state')}"
        )

    preview = text[: max(show_text_chars, 0)].strip()
    print("Text Preview")
    if preview:
        print(preview)
        if len(text) > len(preview):
            print("...")
    else:
        print("(empty)")


if __name__ == "__main__":
    raise SystemExit(main())

# PowerShell example:
# .\.venv\Scripts\python.exe .\scripts\smoke_document_parse.py `
#   --file "D:\code-ai\ai-center\data\uploads\pdf\附件三：投标文件（已压缩）汉阳上传最终11.18-副本_.pdf" `
#   --clear-cache
