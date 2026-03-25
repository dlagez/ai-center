from __future__ import annotations

import unittest

from app.core.config import EmbeddingSettings, GatewaySettings
from app.core.exceptions import (
    EmbeddingConfigurationError,
    EmbeddingTimeoutError,
)
from app.integrations.embedding_providers.base import BaseEmbeddingProviderAdapter
from app.modules.model_center.repositories.in_memory import InMemoryModelConfigRepository
from app.modules.model_center.schemas import (
    ModelCatalogEntry,
    ModelFallbackPolicy,
    ModelRoutePolicy,
)
from app.observability.metrics.embedding_call_recorder import (
    InMemoryEmbeddingCallRecorder,
)
from app.runtime.embedding.gateway_service import build_embedding_gateway_service
from app.runtime.embedding.schemas import (
    EmbeddedChunk,
    EmbeddingBatchRequest,
    EmbeddingInputItem,
    EmbeddingUsageInfo,
    ProviderEmbeddingResponse,
)


class FakeEmbeddingAdapter(BaseEmbeddingProviderAdapter):
    def __init__(
        self,
        *,
        response: ProviderEmbeddingResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self._response = response
        self._error = error
        self.calls = 0

    def embed(self, *, plan, request, trace_id) -> ProviderEmbeddingResponse:
        self.calls += 1
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


class EmbeddingGatewayServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.gateway_settings = GatewaySettings(
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
        self.embedding_settings = EmbeddingSettings(
            embedding_default_logical_model="embedding_default",
            embedding_default_public_model="public-embedding-default",
            embedding_timeout_ms=30000,
            embedding_batch_size=16,
            embedding_enable_public_proxy=True,
            embedding_enable_direct_fallback=True,
            private_embedding_base_url="http://private-embedding:8000",
            private_embedding_api_key="private-key",
            private_embedding_model="private-embedding-model",
            private_embedding_logical_model="private_embedding_backup",
        )
        self.request = EmbeddingBatchRequest(
            tenant_id="tenant-a",
            app_id="app-kb",
            scene="knowledge_index",
            items=[
                EmbeddingInputItem(chunk_id="chunk-1", text="hello world"),
                EmbeddingInputItem(chunk_id="chunk-2", text="second chunk"),
            ],
        )

    def _build_repository(
        self,
        *,
        fallback_target: str | None = "private_embedding_backup",
        same_channel_fallback: bool = False,
    ) -> InMemoryModelConfigRepository:
        catalog_entries = [
            ModelCatalogEntry(
                logical_model="embedding_default",
                display_name="Public embedding",
                provider="litellm_proxy",
                channel="litellm_proxy",
                gateway_model_name="public-embedding-default",
                task_type="embedding",
                capability_tags=["embedding"],
                enabled=True,
                timeout_ms=30000,
            ),
            ModelCatalogEntry(
                logical_model="private_embedding_backup",
                display_name="Private embedding",
                provider="private_embedding",
                channel="litellm_proxy" if same_channel_fallback else "direct",
                direct_model_name="private-embedding-model",
                base_url="http://private-embedding:8000",
                api_key="private-key",
                task_type="embedding",
                capability_tags=["embedding"],
                enabled=True,
                timeout_ms=30000,
            ),
        ]
        route_policies = [
            ModelRoutePolicy(
                logical_model="embedding_default",
                task_type="embedding",
                priority=100,
                enabled=True,
            )
        ]
        fallback_policies = [
            ModelFallbackPolicy(
                source_logical_model="embedding_default",
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

    def test_embed_uses_default_public_model_when_primary_succeeds(self) -> None:
        recorder = InMemoryEmbeddingCallRecorder()
        proxy_adapter = FakeEmbeddingAdapter(
            response=ProviderEmbeddingResponse(
                provider="litellm_proxy",
                model="public-embedding-default",
                dimension=3,
                items=[
                    EmbeddedChunk(
                        chunk_id="chunk-1",
                        text="hello world",
                        vector=[0.1, 0.2, 0.3],
                        dimension=3,
                    ),
                    EmbeddedChunk(
                        chunk_id="chunk-2",
                        text="second chunk",
                        vector=[0.4, 0.5, 0.6],
                        dimension=3,
                    ),
                ],
                usage=EmbeddingUsageInfo(prompt_tokens=12, total_tokens=12),
            )
        )
        service = build_embedding_gateway_service(
            embedding_settings=self.embedding_settings,
            gateway_settings=self.gateway_settings,
            repository=self._build_repository(),
            adapters={
                "litellm_proxy": proxy_adapter,
                "direct": FakeEmbeddingAdapter(),
                "internal_proxy": FakeEmbeddingAdapter(),
            },
            recorder=recorder,
        )

        result = service.embed(self.request)

        self.assertEqual(result.final_channel, "litellm_proxy")
        self.assertEqual(result.final_model, "public-embedding-default")
        self.assertEqual(result.dimension, 3)
        self.assertEqual(len(result.items), 2)
        self.assertEqual(result.items[0].chunk_id, "chunk-1")
        self.assertEqual(len(recorder.records), 1)
        self.assertEqual(recorder.records[0].status, "success")
        self.assertEqual(recorder.records[0].total_tokens, 12)

    def test_embed_falls_back_to_direct_model_when_proxy_fails(self) -> None:
        recorder = InMemoryEmbeddingCallRecorder()
        proxy_adapter = FakeEmbeddingAdapter(error=EmbeddingTimeoutError("proxy timeout"))
        private_adapter = FakeEmbeddingAdapter(
            response=ProviderEmbeddingResponse(
                provider="private_embedding",
                model="private-embedding-model",
                dimension=2,
                items=[
                    EmbeddedChunk(
                        chunk_id="chunk-1",
                        text="hello world",
                        vector=[0.1, 0.2],
                        dimension=2,
                    ),
                    EmbeddedChunk(
                        chunk_id="chunk-2",
                        text="second chunk",
                        vector=[0.3, 0.4],
                        dimension=2,
                    ),
                ],
                usage=EmbeddingUsageInfo(prompt_tokens=10, total_tokens=10),
            )
        )
        service = build_embedding_gateway_service(
            embedding_settings=self.embedding_settings,
            gateway_settings=self.gateway_settings,
            repository=self._build_repository(),
            adapters={
                "litellm_proxy": proxy_adapter,
                "direct": private_adapter,
                "internal_proxy": private_adapter,
            },
            recorder=recorder,
        )

        result = service.embed(self.request)

        self.assertEqual(result.final_channel, "direct")
        self.assertEqual(result.final_provider, "private_embedding")
        self.assertEqual(len(result.fallback_hops), 1)
        self.assertEqual(result.fallback_hops[0].reason, "embedding_timeout_error")
        self.assertEqual(recorder.records[0].fallback_count, 1)

    def test_embed_rejects_same_channel_fallback(self) -> None:
        recorder = InMemoryEmbeddingCallRecorder()
        service = build_embedding_gateway_service(
            embedding_settings=self.embedding_settings,
            gateway_settings=self.gateway_settings,
            repository=self._build_repository(same_channel_fallback=True),
            adapters={
                "litellm_proxy": FakeEmbeddingAdapter(
                    error=EmbeddingTimeoutError("proxy timeout")
                ),
                "direct": FakeEmbeddingAdapter(),
                "internal_proxy": FakeEmbeddingAdapter(),
            },
            recorder=recorder,
        )

        with self.assertRaises(EmbeddingConfigurationError):
            service.embed(self.request)

    def test_embed_splits_requests_by_batch_size(self) -> None:
        recorder = InMemoryEmbeddingCallRecorder()
        batch_settings = self.embedding_settings.model_copy(
            update={"embedding_batch_size": 1}
        ) if hasattr(self.embedding_settings, "model_copy") else EmbeddingSettings(
            embedding_default_logical_model=self.embedding_settings.embedding_default_logical_model,
            embedding_default_public_model=self.embedding_settings.embedding_default_public_model,
            embedding_timeout_ms=self.embedding_settings.embedding_timeout_ms,
            embedding_batch_size=1,
            embedding_enable_public_proxy=self.embedding_settings.embedding_enable_public_proxy,
            embedding_enable_direct_fallback=self.embedding_settings.embedding_enable_direct_fallback,
            private_embedding_base_url=self.embedding_settings.private_embedding_base_url,
            private_embedding_api_key=self.embedding_settings.private_embedding_api_key,
            private_embedding_model=self.embedding_settings.private_embedding_model,
            private_embedding_logical_model=self.embedding_settings.private_embedding_logical_model,
        )
        proxy_adapter = FakeEmbeddingAdapter(
            response=ProviderEmbeddingResponse(
                provider="litellm_proxy",
                model="public-embedding-default",
                dimension=3,
                items=[
                    EmbeddedChunk(
                        chunk_id="chunk-1",
                        text="hello world",
                        vector=[0.1, 0.2, 0.3],
                        dimension=3,
                    )
                ],
                usage=EmbeddingUsageInfo(prompt_tokens=6, total_tokens=6),
            )
        )
        service = build_embedding_gateway_service(
            embedding_settings=batch_settings,
            gateway_settings=self.gateway_settings,
            repository=self._build_repository(),
            adapters={
                "litellm_proxy": proxy_adapter,
                "direct": FakeEmbeddingAdapter(),
                "internal_proxy": FakeEmbeddingAdapter(),
            },
            recorder=recorder,
        )

        result = service.embed(self.request)

        self.assertEqual(proxy_adapter.calls, 2)
        self.assertEqual(len(result.items), 2)
        self.assertEqual(result.usage.total_tokens, 12)


if __name__ == "__main__":
    unittest.main()
