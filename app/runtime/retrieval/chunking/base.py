from __future__ import annotations

from abc import ABC, abstractmethod

from app.runtime.retrieval.chunking.schemas import ChunkDocument, ChunkingPolicyConfig


class BaseChunker(ABC):
    @abstractmethod
    def chunk(
        self,
        *,
        document_id: str,
        policy: ChunkingPolicyConfig,
    ) -> list[ChunkDocument]:
        raise NotImplementedError
