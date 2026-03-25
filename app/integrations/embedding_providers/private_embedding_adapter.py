from __future__ import annotations

from typing import Any

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - handled when dependency is absent
    OpenAI = None

from app.core.config import EmbeddingSettings
from app.core.exceptions import EmbeddingConfigurationError
from app.integrations.embedding_providers.base import BaseEmbeddingProviderAdapter
from app.integrations.embedding_providers.litellm_proxy_embedding_adapter import (
    LiteLLMProxyEmbeddingAdapter,
)
from app.runtime.embedding.schemas import (
    EmbeddingBatchRequest,
    ProviderEmbeddingResponse,
    ResolvedEmbeddingPlan,
)


class PrivateEmbeddingAdapter(BaseEmbeddingProviderAdapter):
    def __init__(self, settings: EmbeddingSettings) -> None:
        self._settings = settings

    def embed(
        self,
        *,
        plan: ResolvedEmbeddingPlan,
        request: EmbeddingBatchRequest,
        trace_id: str,
    ) -> ProviderEmbeddingResponse:
        client = self._build_client(
            base_url=plan.base_url or self._settings.private_embedding_base_url,
            api_key=plan.api_key or self._settings.private_embedding_api_key or "change-me",
        )
        response = client.embeddings.create(
            model=plan.target_model_name,
            input=[item.text for item in request.items],
            timeout=plan.timeout_ms / 1000,
        )
        provider_response = LiteLLMProxyEmbeddingAdapter._to_provider_response(
            provider=plan.provider or "private_embedding",
            response=response,
            request=request,
        )
        return provider_response

    @staticmethod
    def _build_client(*, base_url: str | None, api_key: str) -> Any:
        if OpenAI is None:
            raise EmbeddingConfigurationError(
                "The 'openai' package is required to use the private embedding adapter."
            )
        if not base_url:
            raise EmbeddingConfigurationError(
                "Private embedding adapter requires a base URL."
            )
        normalized_base_url = base_url.rstrip("/")
        if not normalized_base_url.endswith("/v1"):
            normalized_base_url = f"{normalized_base_url}/v1"
        return OpenAI(base_url=normalized_base_url, api_key=api_key)
