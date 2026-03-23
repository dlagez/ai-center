from __future__ import annotations

import os
import unittest
from collections.abc import Iterator

from app.core.config import GatewaySettings
from app.core.exceptions import (
    ModelGatewayConfigurationError,
    ModelGatewayTimeoutError,
)
from app.integrations.model_providers.base import BaseModelProviderAdapter
from app.modules.model_center.repositories.in_memory import InMemoryModelConfigRepository
from app.modules.model_center.schemas import (
    ModelCatalogEntry,
    ModelFallbackPolicy,
    ModelRoutePolicy,
)
from app.observability.metrics.llm_call_recorder import InMemoryLLMCallRecorder
from app.runtime.llm.gateway_service import build_gateway_service
from app.runtime.llm.schemas import (
    LLMInvokeRequest,
    LLMStreamChunk,
    ProviderInvokeResponse,
    UsageInfo,
)


def _load_dotenv_if_present() -> None:
    env_path = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(env_path):
        return

    with open(env_path, encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


class FakeAdapter(BaseModelProviderAdapter):
    def __init__(
        self,
        *,
        response: ProviderInvokeResponse | None = None,
        error: Exception | None = None,
        stream_chunks: list[LLMStreamChunk] | None = None,
        stream_error: Exception | None = None,
    ) -> None:
        self._response = response
        self._error = error
        self._stream_chunks = stream_chunks or []
        self._stream_error = stream_error

    def invoke(self, *, plan, request, trace_id) -> ProviderInvokeResponse:
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response

    def stream(self, *, plan, request, trace_id) -> Iterator[LLMStreamChunk]:
        if self._stream_error is not None:
            raise self._stream_error
        yield from self._stream_chunks


class GatewayServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = GatewaySettings(
            model_gateway_base_url="http://litellm-proxy:4000",
            model_gateway_api_key="change-me",
            model_gateway_timeout_ms=60000,
            model_gateway_enable_public_proxy=True,
            model_gateway_enable_direct_fallback=True,
            model_gateway_default_logical_model="chat_default",
            model_gateway_default_public_model="public-chat-default",
            private_llm_base_url="http://private-llm:8000",
            private_llm_api_key="private-key",
            private_llm_model="private-chat-model",
            private_llm_logical_model="private_sensitive_backup",
        )
        self.request = LLMInvokeRequest(
            tenant_id="tenant-a",
            app_id="app-chat",
            scene="chat",
            task_type="chat",
            messages=[{"role": "user", "content": "hello"}],
        )

    def _build_repository(
        self,
        *,
        fallback_target: str | None = "private_sensitive_backup",
        same_channel_fallback: bool = False,
    ) -> InMemoryModelConfigRepository:
        catalog_entries = [
            ModelCatalogEntry(
                logical_model="chat_default",
                display_name="Public chat",
                provider="litellm_proxy",
                channel="litellm_proxy",
                gateway_model_name="public-chat-default",
                task_type="chat",
                enabled=True,
                timeout_ms=30000,
            ),
            ModelCatalogEntry(
                logical_model="private_sensitive_backup",
                display_name="Private chat",
                provider="private_llm",
                channel="litellm_proxy" if same_channel_fallback else "direct",
                direct_model_name="private-chat-model",
                base_url="http://private-llm:8000",
                api_key="private-key",
                task_type="chat",
                enabled=True,
                timeout_ms=30000,
            ),
        ]
        route_policies = [
            ModelRoutePolicy(
                logical_model="chat_default",
                scene="chat",
                task_type="chat",
                priority=100,
                enabled=True,
            )
        ]
        fallback_policies = [
            ModelFallbackPolicy(
                source_logical_model="chat_default",
                channel_fallback_target=fallback_target,
                max_fallback_count=1,
                enabled=bool(fallback_target),
            )
        ]
        return InMemoryModelConfigRepository(
            catalog_entries=catalog_entries,
            route_policies=route_policies,
            fallback_policies=fallback_policies,
        )

    def test_invoke_chat_uses_litellm_proxy_when_primary_succeeds(self) -> None:
        recorder = InMemoryLLMCallRecorder()
        proxy_adapter = FakeAdapter(
            response=ProviderInvokeResponse(
                provider="litellm_proxy",
                model="public-chat-default",
                content="hello world",
                finish_reason="stop",
                usage=UsageInfo(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )
        )
        service = build_gateway_service(
            settings=self.settings,
            repository=self._build_repository(),
            adapters={
                "litellm_proxy": proxy_adapter,
                "direct": FakeAdapter(),
                "internal_proxy": FakeAdapter(),
            },
            recorder=recorder,
        )

        result = service.invoke_chat(self.request)

        self.assertEqual(result.final_channel, "litellm_proxy")
        self.assertEqual(result.final_model, "public-chat-default")
        self.assertEqual(result.content, "hello world")
        self.assertEqual(len(result.fallback_hops), 0)
        self.assertEqual(len(recorder.records), 1)
        self.assertEqual(recorder.records[0].status, "success")
        self.assertEqual(recorder.records[0].total_tokens, 15)

    def test_invoke_chat_falls_back_to_direct_model_when_proxy_fails(self) -> None:
        recorder = InMemoryLLMCallRecorder()
        proxy_adapter = FakeAdapter(error=ModelGatewayTimeoutError("proxy timeout"))
        private_adapter = FakeAdapter(
            response=ProviderInvokeResponse(
                provider="private_llm",
                model="private-chat-model",
                content="fallback answer",
                finish_reason="stop",
                usage=UsageInfo(prompt_tokens=8, completion_tokens=4, total_tokens=12),
            )
        )
        service = build_gateway_service(
            settings=self.settings,
            repository=self._build_repository(),
            adapters={
                "litellm_proxy": proxy_adapter,
                "direct": private_adapter,
                "internal_proxy": private_adapter,
            },
            recorder=recorder,
        )

        result = service.invoke_chat(self.request)

        self.assertEqual(result.final_channel, "direct")
        self.assertEqual(result.final_provider, "private_llm")
        self.assertEqual(result.content, "fallback answer")
        self.assertEqual(len(result.fallback_hops), 1)
        self.assertEqual(result.fallback_hops[0].reason, "timeout_error")
        self.assertEqual(recorder.records[0].fallback_count, 1)

    def test_invoke_chat_rejects_same_channel_fallback(self) -> None:
        recorder = InMemoryLLMCallRecorder()
        service = build_gateway_service(
            settings=self.settings,
            repository=self._build_repository(same_channel_fallback=True),
            adapters={
                "litellm_proxy": FakeAdapter(error=ModelGatewayTimeoutError("proxy timeout")),
                "direct": FakeAdapter(),
                "internal_proxy": FakeAdapter(),
            },
            recorder=recorder,
        )

        with self.assertRaises(ModelGatewayConfigurationError):
            service.invoke_chat(self.request)

    def test_stream_chat_uses_proxy_stream(self) -> None:
        recorder = InMemoryLLMCallRecorder()
        stream_chunks = [
            LLMStreamChunk(
                trace_id="trace-1",
                logical_model="chat_default",
                final_channel="litellm_proxy",
                final_provider="litellm_proxy",
                final_model="public-chat-default",
                delta="hello ",
            ),
            LLMStreamChunk(
                trace_id="trace-1",
                logical_model="chat_default",
                final_channel="litellm_proxy",
                final_provider="litellm_proxy",
                final_model="public-chat-default",
                delta="world",
                finish_reason="stop",
            ),
        ]
        service = build_gateway_service(
            settings=self.settings,
            repository=self._build_repository(),
            adapters={
                "litellm_proxy": FakeAdapter(stream_chunks=stream_chunks),
                "direct": FakeAdapter(),
                "internal_proxy": FakeAdapter(),
            },
            recorder=recorder,
        )

        chunks = list(service.stream_chat(self.request))

        self.assertEqual("".join(chunk.delta or "" for chunk in chunks), "hello world")
        self.assertEqual(len(recorder.records), 1)
        self.assertEqual(recorder.records[0].status, "stream_success")


class GatewayServiceAlibabaIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _load_dotenv_if_present()

    def test_invoke_chat_with_alibaba_dashscope(self) -> None:
        required_keys = (
            "PRIVATE_LLM_BASE_URL",
            "PRIVATE_LLM_API_KEY",
            "PRIVATE_LLM_MODEL",
            "PRIVATE_LLM_LOGICAL_MODEL",
        )
        missing_keys = [key for key in required_keys if not os.getenv(key)]
        if missing_keys:
            self.skipTest(
                "Missing required environment variables: "
                + ", ".join(missing_keys)
            )

        settings = GatewaySettings.from_env()
        service = build_gateway_service(settings=settings)
        request = LLMInvokeRequest(
            tenant_id="integration-tenant",
            app_id="integration-app",
            scene="chat",
            task_type="chat",
            logical_model=settings.private_llm_logical_model,
            messages=[
                {
                    "role": "user",
                    "content": "请只回复 OK，不要输出其他内容。",
                }
            ],
            temperature=0.1,
            timeout_ms=30000,
        )

        result = service.invoke_chat(request)

        self.assertEqual(result.final_channel, "direct")
        self.assertEqual(result.final_provider, "private_llm")
        self.assertEqual(result.final_model, settings.private_llm_model)
        self.assertIsNotNone(result.content)
        self.assertTrue(result.content.strip())


if __name__ == "__main__":
    unittest.main()

# python -m unittest tests.unit.runtime.llm.test_gateway_service.GatewayServiceAlibabaIntegrationTestCase.test_invoke_chat_with_alibaba_dashscope
#测试阿里模型接口是否可以调用。
