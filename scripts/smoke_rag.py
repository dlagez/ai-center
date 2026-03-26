from __future__ import annotations

import argparse
import json
import re
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
    print()
    print("Answer")
    print(rag_result.answer)
    print()
    print("Citations")
    if not rag_result.citations:
        print("  (none)")
    else:
        for citation in rag_result.citations:
            print(
                "  "
                f"document_id={citation.document_id} "
                f"chunk_id={citation.chunk_id} "
                f"score={citation.score:.4f}"
            )
    return 0


def run_smoke(args: argparse.Namespace) -> tuple[Any, Any]:
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