from __future__ import annotations

from app.core.config import ChunkingSettings
from app.runtime.retrieval.chunking.schemas import ChunkingPolicyConfig


def build_default_chunking_policy(
    settings: ChunkingSettings | None = None,
) -> ChunkingPolicyConfig:
    settings = settings or ChunkingSettings.from_env()
    return ChunkingPolicyConfig(
        policy_name=settings.chunking_default_policy_name,
        max_chars=settings.chunking_max_chars,
        overlap_chars=settings.chunking_overlap_chars,
        split_by_heading=settings.chunking_split_by_heading,
        split_by_paragraph=settings.chunking_split_by_paragraph,
        keep_heading_prefix=settings.chunking_keep_heading_prefix,
    )


def resolve_chunking_policy(
    policy: ChunkingPolicyConfig | None,
    *,
    settings: ChunkingSettings | None = None,
) -> ChunkingPolicyConfig:
    return policy or build_default_chunking_policy(settings)
