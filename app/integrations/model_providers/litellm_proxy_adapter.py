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
from app.runtime.llm.schemas import (
    LLMInvokeRequest,
    LLMStreamChunk,
    ProviderInvokeResponse,
    ResolvedInvocationPlan,
    UsageInfo,
)


class LiteLLMProxyAdapter(BaseModelProviderAdapter):
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
            base_url=self._settings.model_gateway_base_url,
            api_key=self._settings.model_gateway_api_key,
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
        return self._to_provider_response(response)

    def stream(
        self,
        *,
        plan: ResolvedInvocationPlan,
        request: LLMInvokeRequest,
        trace_id: str,
    ) -> Iterator[LLMStreamChunk]:
        client = self._build_client(
            base_url=self._settings.model_gateway_base_url,
            api_key=self._settings.model_gateway_api_key,
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
            yield self._to_stream_chunk(
                trace_id=trace_id,
                logical_model=plan.logical_model,
                final_channel=plan.channel,
                chunk=chunk,
            )

    def _build_client(self, *, base_url: str, api_key: str) -> Any:
        if OpenAI is None:
            raise ModelGatewayConfigurationError(
                "The 'openai' package is required to use the LiteLLM proxy adapter."
            )
        normalized_base_url = base_url.rstrip("/")
        if not normalized_base_url.endswith("/v1"):
            normalized_base_url = f"{normalized_base_url}/v1"
        return OpenAI(base_url=normalized_base_url, api_key=api_key)

    @staticmethod
    def _to_provider_response(response: Any) -> ProviderInvokeResponse:
        choice = response.choices[0]
        message = choice.message
        usage = getattr(response, "usage", None)
        return ProviderInvokeResponse(
            provider="litellm_proxy",
            model=getattr(response, "model", ""),
            content=LiteLLMProxyAdapter._extract_content(getattr(message, "content", None)),
            tool_calls=LiteLLMProxyAdapter._dump_items(getattr(message, "tool_calls", None)),
            finish_reason=getattr(choice, "finish_reason", None),
            usage=UsageInfo(
                prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                total_tokens=getattr(usage, "total_tokens", 0) or 0,
            ),
            raw_response=response.model_dump() if hasattr(response, "model_dump") else None,
        )

    @staticmethod
    def _to_stream_chunk(
        *,
        trace_id: str,
        logical_model: str,
        final_channel: str,
        chunk: Any,
    ) -> LLMStreamChunk:
        choice = chunk.choices[0]
        delta = choice.delta
        return LLMStreamChunk(
            trace_id=trace_id,
            logical_model=logical_model,
            final_channel=final_channel,
            final_provider="litellm_proxy",
            final_model=getattr(chunk, "model", ""),
            delta=LiteLLMProxyAdapter._extract_content(getattr(delta, "content", None)),
            tool_calls=LiteLLMProxyAdapter._dump_items(getattr(delta, "tool_calls", None)),
            finish_reason=getattr(choice, "finish_reason", None),
            raw_response=chunk.model_dump() if hasattr(chunk, "model_dump") else None,
        )

    @staticmethod
    def _extract_content(content: Any) -> str | None:
        if content is None:
            return None
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
                elif hasattr(item, "text"):
                    text_parts.append(getattr(item, "text"))
            return "".join(text_parts) or None
        return str(content)

    @staticmethod
    def _dump_items(items: Any) -> list[dict[str, Any]] | None:
        if not items:
            return None
        dumped_items: list[dict[str, Any]] = []
        for item in items:
            if hasattr(item, "model_dump"):
                dumped_items.append(item.model_dump())
            elif isinstance(item, dict):
                dumped_items.append(item)
            else:
                dumped_items.append(vars(item))
        return dumped_items
