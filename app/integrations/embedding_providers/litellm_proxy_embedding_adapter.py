from __future__ import annotations

from typing import Any

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - handled when dependency is absent
    OpenAI = None

from app.core.config import GatewaySettings
from app.core.exceptions import EmbeddingConfigurationError
from app.integrations.embedding_providers.base import BaseEmbeddingProviderAdapter
from app.runtime.embedding.schemas import (
    EmbeddedChunk,
    EmbeddingBatchRequest,
    EmbeddingUsageInfo,
    ProviderEmbeddingResponse,
    ResolvedEmbeddingPlan,
)


class LiteLLMProxyEmbeddingAdapter(BaseEmbeddingProviderAdapter):
    def __init__(self, settings: GatewaySettings) -> None:
        self._settings = settings

    def embed(
        self,
        *,
        plan: ResolvedEmbeddingPlan,
        request: EmbeddingBatchRequest,
        trace_id: str,
    ) -> ProviderEmbeddingResponse:
        client = self._build_client(
            base_url=self._settings.model_gateway_base_url,
            api_key=self._settings.model_gateway_api_key,
        )
        response = client.embeddings.create(
            model=plan.target_model_name,
            input=[item.text for item in request.items],
            timeout=plan.timeout_ms / 1000,
        )
        return self._to_provider_response(
            provider="litellm_proxy",
            response=response,
            request=request,
        )

    def _build_client(self, *, base_url: str, api_key: str) -> Any:
        if OpenAI is None:
            raise EmbeddingConfigurationError(
                "The 'openai' package is required to use the LiteLLM embedding adapter."
            )
        normalized_base_url = base_url.rstrip("/")
        if not normalized_base_url.endswith("/v1"):
            normalized_base_url = f"{normalized_base_url}/v1"
        return OpenAI(base_url=normalized_base_url, api_key=api_key)

    @staticmethod
    def _to_provider_response(
        *,
        provider: str,
        response: Any,
        request: EmbeddingBatchRequest,
    ) -> ProviderEmbeddingResponse:
        usage = getattr(response, "usage", None)
        items: list[EmbeddedChunk] = []
        response_data = list(getattr(response, "data", []))
        for index, payload in enumerate(response_data):
            source_item = request.items[index]
            vector = [float(value) for value in getattr(payload, "embedding", [])]
            items.append(
                EmbeddedChunk(
                    chunk_id=source_item.chunk_id,
                    text=source_item.text,
                    vector=vector,
                    dimension=len(vector),
                    metadata=dict(source_item.metadata),
                )
            )
        dimension = items[0].dimension if items else 0
        return ProviderEmbeddingResponse(
            provider=provider,
            model=getattr(response, "model", ""),
            dimension=dimension,
            items=items,
            usage=EmbeddingUsageInfo(
                prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                total_tokens=getattr(usage, "total_tokens", 0) or 0,
            ),
            raw_response=response.model_dump() if hasattr(response, "model_dump") else None,
        )
