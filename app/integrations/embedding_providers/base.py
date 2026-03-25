from __future__ import annotations

from abc import ABC, abstractmethod

from app.runtime.embedding.schemas import (
    EmbeddingBatchRequest,
    ProviderEmbeddingResponse,
    ResolvedEmbeddingPlan,
)


class BaseEmbeddingProviderAdapter(ABC):
    @abstractmethod
    def embed(
        self,
        *,
        plan: ResolvedEmbeddingPlan,
        request: EmbeddingBatchRequest,
        trace_id: str,
    ) -> ProviderEmbeddingResponse:
        raise NotImplementedError
