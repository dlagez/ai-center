from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core.config import LangSmithSettings


def infer_pipeline_kind(
    *,
    scene: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> str:
    normalized_scene = (scene or "").strip().lower()
    normalized_metadata = metadata or {}

    pipeline = normalized_metadata.get("langsmith_pipeline")
    if pipeline in {"rag", "ingest", "eval", "default"}:
        return str(pipeline)

    if (
        "knowledge_index_trace_id" in normalized_metadata
        or normalized_scene in {"knowledge_ingest", "knowledge_index"}
    ):
        return "ingest"

    if (
        "rag_trace_id" in normalized_metadata
        or "retrieval_trace_id" in normalized_metadata
        or normalized_scene in {"knowledge_qa", "knowledge_retrieval"}
    ):
        return "rag"

    if normalized_scene.startswith("eval") or "reference_example_id" in normalized_metadata:
        return "eval"

    return "default"


def resolve_project_name(
    settings: LangSmithSettings,
    *,
    pipeline_kind: str,
) -> str:
    if pipeline_kind == "rag":
        return settings.app_langsmith_project_rag
    if pipeline_kind == "ingest":
        return settings.app_langsmith_project_ingest
    if pipeline_kind == "eval":
        return settings.app_langsmith_project_eval
    return settings.langsmith_project
