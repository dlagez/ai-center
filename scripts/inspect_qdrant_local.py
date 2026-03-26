from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import VectorStoreSettings

try:
    from qdrant_client import QdrantClient
    from qdrant_client import models
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "The 'qdrant-client' package is required. Run: "
        ".\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt"
    ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect embedded Qdrant local data.",
    )
    parser.add_argument(
        "--path",
        help="Path to local Qdrant data directory. Defaults to QDRANT_LOCAL_PATH from .env.",
    )
    parser.add_argument(
        "--collection",
        help="Inspect a single collection. If omitted, list all collections.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of sample points to print or export. Default: 5.",
    )
    parser.add_argument(
        "--show-vectors",
        action="store_true",
        help="Include vector preview in output.",
    )
    parser.add_argument(
        "--vector-dims",
        type=int,
        default=8,
        help="How many vector dimensions to print when --show-vectors is used. Default: 8.",
    )
    parser.add_argument(
        "--export-jsonl",
        help="Export selected collection points to a JSONL file.",
    )
    parser.add_argument(
        "--filter-json",
        help="Optional filter JSON, e.g. '{\"document_id\":\"doc-1\"}'.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    settings = VectorStoreSettings.from_env()
    local_path = resolve_local_path(args.path, settings)
    if not local_path.exists():
        raise SystemExit(f"Qdrant local path does not exist: {local_path}")

    client = QdrantClient(path=str(local_path))
    try:
        if args.collection:
            inspect_collection(
                client,
                collection_name=args.collection,
                limit=max(1, args.limit),
                show_vectors=args.show_vectors,
                vector_dims=max(1, args.vector_dims),
                export_jsonl=args.export_jsonl,
                filter_json=args.filter_json,
            )
        else:
            list_collections(
                client,
                limit=max(1, args.limit),
            )
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def resolve_local_path(raw_path: str | None, settings: VectorStoreSettings) -> Path:
    target = Path(raw_path or settings.qdrant_local_path or "")
    if not target.is_absolute():
        project_root = Path(__file__).resolve().parents[1]
        target = project_root / target
    return target


def list_collections(client: QdrantClient, *, limit: int) -> None:
    collections = client.get_collections().collections
    print(f"collection_count = {len(collections)}")
    if not collections:
        print("No collections found.")
        return

    for item in collections:
        info = client.get_collection(item.name)
        print("")
        print(f"collection = {item.name}")
        print(f"points_count = {info.points_count}")
        print(f"vectors_count = {info.vectors_count}")
        print(f"payload_schema_keys = {sorted((info.payload_schema or {}).keys())}")
        records, _ = client.scroll(
            item.name,
            limit=min(limit, 3),
            with_payload=True,
            with_vectors=False,
        )
        for index, record in enumerate(records, 1):
            payload = summarize_payload(dict(record.payload or {}))
            print(f"  sample_{index}: id={record.id} payload={json.dumps(payload, ensure_ascii=False)}")


def inspect_collection(
    client: QdrantClient,
    *,
    collection_name: str,
    limit: int,
    show_vectors: bool,
    vector_dims: int,
    export_jsonl: str | None,
    filter_json: str | None,
) -> None:
    info = client.get_collection(collection_name)
    query_filter = build_filter(filter_json)

    print(f"collection = {collection_name}")
    print(f"points_count = {info.points_count}")
    print(f"vectors_count = {info.vectors_count}")
    print(f"payload_schema_keys = {sorted((info.payload_schema or {}).keys())}")

    records, _ = client.scroll(
        collection_name,
        scroll_filter=query_filter,
        limit=limit,
        with_payload=True,
        with_vectors=show_vectors,
    )

    print(f"sample_count = {len(records)}")
    for index, record in enumerate(records, 1):
        payload = summarize_payload(dict(record.payload or {}))
        printable: dict[str, Any] = {
            "id": str(record.id),
            "payload": payload,
        }
        if show_vectors:
            vector = normalize_vector(record.vector)
            printable["vector_dim"] = len(vector)
            printable["vector_preview"] = vector[:vector_dims]
        print("")
        print(f"sample_{index}")
        print(json.dumps(printable, ensure_ascii=False, indent=2))

    if export_jsonl:
        export_records(records, export_jsonl, show_vectors=show_vectors)
        print("")
        print(f"exported_jsonl = {Path(export_jsonl).resolve()}")


def build_filter(filter_json: str | None) -> models.Filter | None:
    if not filter_json:
        return None
    raw = json.loads(filter_json)
    if not isinstance(raw, dict):
        raise SystemExit("--filter-json must be a JSON object.")

    conditions = []
    for key, expected in raw.items():
        if isinstance(expected, list):
            if not expected:
                continue
            if len(expected) == 1:
                conditions.append(
                    models.FieldCondition(
                        key=key,
                        match=models.MatchValue(value=expected[0]),
                    )
                )
            else:
                conditions.append(
                    models.FieldCondition(
                        key=key,
                        match=models.MatchAny(any=expected),
                    )
                )
            continue
        if isinstance(expected, (str, int, bool)):
            conditions.append(
                models.FieldCondition(
                    key=key,
                    match=models.MatchValue(value=expected),
                )
            )
            continue
        raise SystemExit(f"Unsupported filter value type for '{key}'.")

    return models.Filter(must=conditions) if conditions else None


def summarize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if "text" in payload and isinstance(payload["text"], str) and len(payload["text"]) > 120:
        payload["text"] = payload["text"][:120] + "..."
    return payload


def normalize_vector(vector: Any) -> list[float]:
    if vector is None:
        return []
    if isinstance(vector, dict):
        # Named vectors are not used in current project, but keep it safe.
        first_value = next(iter(vector.values()), [])
        return [float(value) for value in first_value]
    return [float(value) for value in vector]


def export_records(records: list[Any], output_path: str, *, show_vectors: bool) -> None:
    target = Path(output_path)
    if not target.is_absolute():
        target = Path.cwd() / target
    target.parent.mkdir(parents=True, exist_ok=True)

    with target.open("w", encoding="utf-8") as handle:
        for record in records:
            payload = dict(record.payload or {})
            item: dict[str, Any] = {
                "id": str(record.id),
                "payload": payload,
            }
            if show_vectors:
                item["vector"] = normalize_vector(record.vector)
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()

# 列出所有 collections 和样本点
# .\.venv\Scripts\python.exe scripts/inspect_qdrant_local.py

# 看某个 collection 的前 5 条
# .\.venv\Scripts\python.exe scripts/inspect_qdrant_local.py --collection kb_xxx --limit 5

# 顺便看向量前 8 维
# .\.venv\Scripts\python.exe scripts/inspect_qdrant_local.py --collection kb_xxx --show-vectors

# 按 document_id 过滤
# .\.venv\Scripts\python.exe scripts/inspect_qdrant_local.py --collection kb_xxx --filter-json "{\"document_id\":\"doc-1\"}"

# 导出成 JSONL，方便用 VS Code / Excel 再看
# .\.venv\Scripts\python.exe scripts/inspect_qdrant_local.py --collection kb_xxx --limit 100 --export-jsonl tmp\kb_xxx.jsonl
