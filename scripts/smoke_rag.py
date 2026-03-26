from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.modules.knowledge_center import (  # noqa: E402
    KnowledgeIndexSourceRequest,
    KnowledgeIndexTextRequest,
    RAGAskRequest,
    build_knowledge_index_service,
    build_simple_rag_service,
)
from app.modules.document_center import (  # noqa: E402
    DocumentParseRequest,
    build_document_parse_service,
)
from app.modules.document_center.repositories.pdf_ocr_checkpoint_repository import (  # noqa: E402
    PDFOCRCheckpointRepository,
)
from app.observability.tracing import get_default_langsmith_tracer  # noqa: E402
from app.runtime.retrieval import build_default_retriever_service  # noqa: E402
from app.runtime.retrieval.vector_store.service import (  # noqa: E402
    build_default_vector_store_service,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Smoke-test the minimal RAG flow: ingest content, then ask a question.",
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--file",
        help="Local file path to ingest, for example D:\\docs\\sample.pdf",
    )
    source_group.add_argument(
        "--url",
        help="HTTP or HTTPS document URL to ingest.",
    )
    source_group.add_argument(
        "--text",
        help="Raw text to ingest directly without document parsing.",
    )

    parser.add_argument("--question", required=True, help="Question to ask after ingest.")
    parser.add_argument("--tenant-id", default="demo-tenant")
    parser.add_argument("--app-id", default="demo-app")
    parser.add_argument("--knowledge-base-id", default="kb-demo")
    parser.add_argument("--document-id", help="Optional stable document id override.")
    parser.add_argument("--index-name", default="main")
    parser.add_argument("--index-version", default="v1")
    parser.add_argument("--file-name", help="Optional override for the document file name.")
    parser.add_argument("--file-type", help="Optional override for the document file type.")
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of chunks to retrieve for answering.",
    )
    parser.add_argument(
        "--score-threshold",
        type=float,
        help="Optional retrieval score threshold.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        help="Optional timeout in milliseconds for ingest embedding and RAG ask.",
    )
    parser.add_argument(
        "--embedding-logical-model",
        help="Optional logical embedding model used for document indexing.",
    )
    parser.add_argument(
        "--query-logical-model",
        help="Optional logical embedding model used for retrieval query embedding.",
    )
    parser.add_argument(
        "--llm-logical-model",
        help="Optional logical LLM model used for answer generation.",
    )
    parser.add_argument(
        "--system-prompt",
        help="Optional custom system prompt for the answer step.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full ingest and ask results as JSON.",
    )
    parser.add_argument(
        "--clear-parse-cache",
        action="store_true",
        help="Delete the document parse cache and OCR checkpoint files for this source before ingest.",
    )
    parser.add_argument(
        "--show-hit-text-chars",
        type=int,
        default=280,
        help="Number of retrieved chunk text characters to preview in non-JSON mode.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        ingest_result, rag_result = run_smoke(args)
    except Exception as exc:
        print(f"RAG smoke run failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(
            json.dumps(
                {
                    "ingest": ingest_result.model_dump(mode="json"),
                    "ask": rag_result.model_dump(mode="json"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print("Ingest")
    print(f"  document_id: {ingest_result.document_id}")
    print(f"  collection: {ingest_result.collection_name}")
    print(f"  chunks: {ingest_result.total_chunks}")
    print(f"  embedded: {ingest_result.embedded_count}")
    print(f"  success_count: {ingest_result.success_count}")
    print_parse_summary(ingest_result.model_dump(mode="json"))
    print()
    print("Retrieval")
    print(f"  requested_top_k: {args.top_k}")
    print(f"  score_threshold: {args.score_threshold}")
    print(f"  returned_hits: {len(rag_result.citations)}")
    print(f"  retrieval_total_hits: {rag_result.metadata.get('retrieval_total_hits')}")
    print()
    print("Answer")
    print(rag_result.answer)
    print()
    print("Citations")
    if not rag_result.citations:
        print("  (none)")
    else:
        for index, citation in enumerate(rag_result.citations, start=1):
            metadata = citation.metadata or {}
            print(
                f"  [{index}] "
                f"document_id={citation.document_id} "
                f"chunk_id={citation.chunk_id} "
                f"score={citation.score:.4f}"
            )
            if metadata.get("page_range"):
                print(f"      page_range={metadata.get('page_range')}")
            if metadata.get("title_path"):
                print(f"      title_path={metadata.get('title_path')}")
            if citation.source_position:
                print(f"      source_position={citation.source_position}")
            preview = build_preview(citation.text, args.show_hit_text_chars)
            if preview:
                print(f"      text={preview}")
    return 0


def run_smoke(args: argparse.Namespace) -> tuple[Any, Any]:
    if args.clear_parse_cache and args.text is None:
        clear_parse_cache_for_source(args)

    vector_store_service = build_default_vector_store_service()
    try:
        index_service = build_knowledge_index_service(
            vector_store_service=vector_store_service
        )
        retriever_service = build_default_retriever_service(
            vector_store_service=vector_store_service
        )
        rag_service = build_simple_rag_service(retriever_service=retriever_service)

        document_id = args.document_id or infer_document_id(args)

        if args.text is not None:
            ingest_result = index_service.ingest_raw_text(
                KnowledgeIndexTextRequest(
                    tenant_id=args.tenant_id,
                    app_id=args.app_id,
                    knowledge_base_id=args.knowledge_base_id,
                    document_id=document_id,
                    raw_text=args.text,
                    index_name=args.index_name,
                    index_version=args.index_version,
                    file_name=args.file_name,
                    file_type=args.file_type,
                    logical_model=args.embedding_logical_model,
                    timeout_ms=args.timeout_ms,
                )
            )
        else:
            source_type, source_value, file_name = resolve_source(args)
            ingest_result = index_service.ingest_source(
                KnowledgeIndexSourceRequest(
                    tenant_id=args.tenant_id,
                    app_id=args.app_id,
                    knowledge_base_id=args.knowledge_base_id,
                    document_id=document_id,
                    source_type=source_type,
                    source_value=source_value,
                    file_name=args.file_name or file_name,
                    file_type=args.file_type,
                    index_name=args.index_name,
                    index_version=args.index_version,
                    logical_model=args.embedding_logical_model,
                    timeout_ms=args.timeout_ms,
                )
            )

        rag_result = rag_service.answer(
            RAGAskRequest(
                tenant_id=args.tenant_id,
                app_id=args.app_id,
                knowledge_base_id=args.knowledge_base_id,
                index_name=args.index_name,
                index_version=args.index_version,
                question=args.question,
                top_k=args.top_k,
                score_threshold=args.score_threshold,
                query_logical_model=args.query_logical_model,
                logical_model=args.llm_logical_model,
                timeout_ms=args.timeout_ms,
                system_prompt=args.system_prompt,
            )
        )
        return ingest_result, rag_result
    finally:
        vector_store_service.close()
        get_default_langsmith_tracer().flush()


def resolve_source(args: argparse.Namespace) -> tuple[str, str, str | None]:
    if args.file:
        path = Path(args.file).expanduser().resolve()
        return "file_path", str(path), path.name
    if args.url:
        url_path = Path(args.url.split("?", 1)[0])
        inferred_name = url_path.name or None
        return "url", args.url, inferred_name
    raise ValueError("Either --file, --url, or --text must be provided.")


def clear_parse_cache_for_source(args: argparse.Namespace) -> None:
    parse_service = build_document_parse_service()
    request = build_parse_request(args)
    asset = parse_service._file_identity_service.normalize(request)
    parser = parse_service._parser_router_service.resolve(asset)
    cache_key = parse_service._parse_cache_service.build_cache_key(
        asset=asset,
        request=request,
        parser_name=parser.parser_name,
        parser_version=parser.parser_version,
    )
    cache_dir = Path(parse_service._parse_cache_service._settings.document_parse_cache_dir)
    checkpoint_repository = PDFOCRCheckpointRepository(cache_dir)
    final_cache_path = cache_dir / f"{cache_key}.json"
    if final_cache_path.exists():
        final_cache_path.unlink()
    partial_dir = checkpoint_repository.partial_dir(cache_key)
    if partial_dir.exists():
        shutil.rmtree(partial_dir, ignore_errors=True)


def build_parse_request(args: argparse.Namespace) -> DocumentParseRequest:
    source_type, source_value, inferred_file_name = resolve_source(args)
    return DocumentParseRequest(
        tenant_id=args.tenant_id,
        app_id=args.app_id,
        scene="knowledge_ingest",
        source_type=source_type,
        source_value=source_value,
        file_name=args.file_name or inferred_file_name,
        file_type=args.file_type,
        parse_mode="text",
    )


def print_parse_summary(ingest_result: dict[str, Any]) -> None:
    metadata = ingest_result.get("metadata") or {}
    if "document_parse_cache_hit" not in metadata:
        return

    strategy = metadata.get("document_parse_strategy")
    cache_hit = metadata.get("document_parse_cache_hit")
    if cache_hit:
        execution = "cache"
    elif strategy == "ocr":
        execution = "direct_ocr"
    else:
        execution = "direct_parse"

    print("Parse")
    print(f"  execution: {execution}")
    print(f"  cache_hit: {cache_hit}")
    print(f"  cache_key: {metadata.get('document_parse_cache_key')}")
    print(
        "  parser: "
        f"{metadata.get('document_parse_parser_name')}"
        f"@{metadata.get('document_parse_parser_version')}"
    )
    print(f"  latency_ms: {metadata.get('document_parse_latency_ms')}")
    print(f"  strategy: {strategy}")
    print(f"  provider: {metadata.get('document_parse_provider')}")
    print(f"  model: {metadata.get('document_parse_model')}")
    print(f"  page_count: {metadata.get('document_parse_page_count')}")
    if strategy == "ocr":
        print(f"  ocr_mode: {metadata.get('document_parse_ocr_mode')}")
        print(f"  ocr_batch_count: {metadata.get('document_parse_ocr_batch_count')}")
        print(f"  ocr_total_pages: {metadata.get('document_parse_ocr_total_pages')}")
        print(f"  ocr_retry_count: {metadata.get('document_parse_ocr_retry_count')}")
        print(
            "  ocr_resumed_batch_count: "
            f"{metadata.get('document_parse_ocr_resumed_batch_count')}"
        )


def build_preview(text: str | None, max_chars: int) -> str:
    if not text or max_chars <= 0:
        return ""
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[:max_chars].rstrip() + "..."


def infer_document_id(args: argparse.Namespace) -> str:
    if args.file:
        stem = Path(args.file).stem
    elif args.url:
        stem = Path(args.url.split("?", 1)[0]).stem or "document"
    else:
        stem = "raw-text"
    normalized = re.sub(r"[^0-9A-Za-z_-]+", "-", stem.strip()).strip("-")
    return normalized or "document"


if __name__ == "__main__":
    raise SystemExit(main())

# .\.venv\Scripts\python.exe .\scripts\smoke_rag.py `
#   --file "D:\code-ai\ai-center\data\uploads\doc\关于清明节机房安全巡检工作部署.docx" `
#   --question "这份文件主要讲了什么？"
