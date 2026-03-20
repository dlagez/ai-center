from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from app.runtime.llm.schemas import (
    LLMInvokeRequest,
    LLMStreamChunk,
    ProviderInvokeResponse,
    ResolvedInvocationPlan,
)


class BaseModelProviderAdapter(ABC):
    @abstractmethod
    def invoke(
        self,
        *,
        plan: ResolvedInvocationPlan,
        request: LLMInvokeRequest,
        trace_id: str,
    ) -> ProviderInvokeResponse:
        raise NotImplementedError

    @abstractmethod
    def stream(
        self,
        *,
        plan: ResolvedInvocationPlan,
        request: LLMInvokeRequest,
        trace_id: str,
    ) -> Iterator[LLMStreamChunk]:
        raise NotImplementedError
