from __future__ import annotations

from collections.abc import Iterator
from typing import Any

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - handled when dependency is absent
    OpenAI = None

from app.core.config import GatewaySettings
from app.core.exceptions import ModelGatewayConfigurationError
from app.integrations.model_providers.base import BaseModelProviderAdapter
from app.integrations.model_providers.litellm_proxy_adapter import LiteLLMProxyAdapter
from app.runtime.llm.schemas import (
    LLMInvokeRequest,
    LLMStreamChunk,
    ProviderInvokeResponse,
    ResolvedInvocationPlan,
)


class PrivateLLMAdapter(BaseModelProviderAdapter):
    def __init__(self, settings: GatewaySettings) -> None:
        self._settings = settings

    def invoke(
        self,
        *,
        plan: ResolvedInvocationPlan,
        request: LLMInvokeRequest,
        trace_id: str,
    ) -> ProviderInvokeResponse:
        client = self._build_client(
            base_url=plan.base_url or self._settings.private_llm_base_url,
            api_key=plan.api_key or self._settings.private_llm_api_key or "change-me",
        )
        response = client.chat.completions.create(
            model=plan.target_model_name,
            messages=request.messages,
            tools=request.tools,
            response_format=request.response_format,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            timeout=plan.timeout_ms / 1000,
        )
        provider_response = LiteLLMProxyAdapter._to_provider_response(response)
        return provider_response.model_copy(
            update={"provider": plan.provider or "private_llm"}
        )

    def stream(
        self,
        *,
        plan: ResolvedInvocationPlan,
        request: LLMInvokeRequest,
        trace_id: str,
    ) -> Iterator[LLMStreamChunk]:
        client = self._build_client(
            base_url=plan.base_url or self._settings.private_llm_base_url,
            api_key=plan.api_key or self._settings.private_llm_api_key or "change-me",
        )
        stream = client.chat.completions.create(
            model=plan.target_model_name,
            messages=request.messages,
            tools=request.tools,
            response_format=request.response_format,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            timeout=plan.timeout_ms / 1000,
            stream=True,
        )
        for chunk in stream:
            base_chunk = LiteLLMProxyAdapter._to_stream_chunk(
                trace_id=trace_id,
                logical_model=plan.logical_model,
                final_channel=plan.channel,
                chunk=chunk,
            )
            yield base_chunk.model_copy(
                update={"final_provider": plan.provider or "private_llm"}
            )

    @staticmethod
    def _build_client(*, base_url: str | None, api_key: str) -> Any:
        if OpenAI is None:
            raise ModelGatewayConfigurationError(
                "The 'openai' package is required to use the private model adapter."
            )
        if not base_url:
            raise ModelGatewayConfigurationError(
                "Private model adapter requires a base URL."
            )
        normalized_base_url = base_url.rstrip("/")
        if not normalized_base_url.endswith("/v1"):
            normalized_base_url = f"{normalized_base_url}/v1"
        return OpenAI(base_url=normalized_base_url, api_key=api_key)
