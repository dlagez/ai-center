from __future__ import annotations

import time
import uuid

from app.core.config import EmbeddingSettings, GatewaySettings
from app.core.exceptions import EmbeddingConfigurationError, EmbeddingError
from app.integrations.embedding_providers.base import BaseEmbeddingProviderAdapter
from app.integrations.embedding_providers.litellm_proxy_embedding_adapter import (
    LiteLLMProxyEmbeddingAdapter,
)
from app.integrations.embedding_providers.private_embedding_adapter import (
    PrivateEmbeddingAdapter,
)
from app.modules.model_center.repositories.in_memory import InMemoryModelConfigRepository
from app.modules.model_center.schemas import (
    ModelCatalogEntry,
    ModelFallbackPolicy,
    ModelRoutePolicy,
)
from app.modules.model_center.services.model_policy_service import ModelPolicyService
from app.observability.metrics.embedding_call_recorder import (
    InMemoryEmbeddingCallRecorder,
)
from app.runtime.embedding.error_mapper import EmbeddingErrorMapper
from app.runtime.embedding.resolver import EmbeddingModelResolver
from app.runtime.embedding.response_normalizer import EmbeddingResponseNormalizer
from app.runtime.embedding.schemas import (
    EmbeddingBatchRequest,
    EmbeddingBatchResult,
    EmbeddingFallbackHop,
    ProviderEmbeddingResponse,
    ResolvedEmbeddingPlan,
)

FALLBACK_ELIGIBLE_ERRORS = {
    "embedding_timeout_error",
    "embedding_rate_limit_error",
    "embedding_provider_unavailable",
    "embedding_bad_response_error",
    "embedding_unknown_error",
}


class EmbeddingGatewayService:
    def __init__(
        self,
        *,
        settings: EmbeddingSettings,
        resolver: EmbeddingModelResolver,
        adapters: dict[str, BaseEmbeddingProviderAdapter],
        recorder: InMemoryEmbeddingCallRecorder,
        error_mapper: EmbeddingErrorMapper | None = None,
        normalizer: EmbeddingResponseNormalizer | None = None,
    ) -> None:
        self._settings = settings
        self._resolver = resolver
        self._adapters = adapters
        self._recorder = recorder
        self._error_mapper = error_mapper or EmbeddingErrorMapper()
        self._normalizer = normalizer or EmbeddingResponseNormalizer()

    def embed(self, request: EmbeddingBatchRequest) -> EmbeddingBatchResult:
        if not request.items:
            raise EmbeddingConfigurationError("Embedding request items must not be empty.")

        trace_id = uuid.uuid4().hex
        primary_plan = self._resolver.resolve(request)
        fallback_hops: list[EmbeddingFallbackHop] = []

        try:
            response, latency_ms = self._embed_plan(
                plan=primary_plan,
                request=request,
                trace_id=trace_id,
            )
            result = self._normalizer.normalize(
                trace_id=trace_id,
                logical_model=primary_plan.logical_model,
                final_channel=primary_plan.channel,
                response=response,
                latency_ms=latency_ms,
                fallback_hops=fallback_hops,
            )
            self._recorder.record_success(request, result)
            return result
        except Exception as exc:
            primary_error = self._error_mapper.to_embedding_error(exc)

        fallback_plan = self._resolve_fallback_plan(
            primary_plan=primary_plan,
            request=request,
            error=primary_error,
        )
        if fallback_plan is None:
            self._recorder.record_failure(
                request=request,
                trace_id=trace_id,
                plan=primary_plan,
                error=primary_error,
                fallback_count=0,
            )
            raise primary_error

        fallback_hops.append(
            EmbeddingFallbackHop(
                source_logical_model=primary_plan.logical_model,
                target_logical_model=fallback_plan.logical_model,
                target_channel=fallback_plan.channel,
                reason=primary_error.code,
            )
        )
        try:
            response, latency_ms = self._embed_plan(
                plan=fallback_plan,
                request=request,
                trace_id=trace_id,
            )
            result = self._normalizer.normalize(
                trace_id=trace_id,
                logical_model=primary_plan.logical_model,
                final_channel=fallback_plan.channel,
                response=response,
                latency_ms=latency_ms,
                fallback_hops=fallback_hops,
            )
            self._recorder.record_success(request, result)
            return result
        except Exception as exc:
            fallback_error = self._error_mapper.to_embedding_error(exc)
            self._recorder.record_failure(
                request=request,
                trace_id=trace_id,
                plan=fallback_plan,
                error=fallback_error,
                fallback_count=len(fallback_hops),
            )
            raise fallback_error

    def _embed_plan(
        self,
        *,
        plan: ResolvedEmbeddingPlan,
        request: EmbeddingBatchRequest,
        trace_id: str,
    ) -> tuple[ProviderEmbeddingResponse, int]:
        start_time = time.perf_counter()
        adapter = self._get_adapter(plan.channel)
        responses: list[ProviderEmbeddingResponse] = []
        batch_size = max(1, plan.batch_size)
        for batch_start in range(0, len(request.items), batch_size):
            batch_request = request.model_copy(
                update={"items": request.items[batch_start : batch_start + batch_size]}
            )
            responses.append(adapter.embed(plan=plan, request=batch_request, trace_id=trace_id))

        response = self._merge_provider_responses(responses)
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        return response, latency_ms

    def _get_adapter(self, channel: str) -> BaseEmbeddingProviderAdapter:
        adapter = self._adapters.get(channel)
        if adapter is None and channel == "internal_proxy":
            adapter = self._adapters.get("direct")
        if adapter is None:
            raise EmbeddingConfigurationError(
                f"No embedding adapter is registered for channel '{channel}'."
            )
        return adapter

    def _resolve_fallback_plan(
        self,
        *,
        primary_plan: ResolvedEmbeddingPlan,
        request: EmbeddingBatchRequest,
        error: EmbeddingError,
    ) -> ResolvedEmbeddingPlan | None:
        if error.code not in FALLBACK_ELIGIBLE_ERRORS:
            return None
        if primary_plan.max_fallback_count <= 0:
            return None
        if not primary_plan.fallback_target_logical_model:
            return None
        if not self._settings.embedding_enable_direct_fallback:
            return None

        fallback_plan = self._resolver.resolve_logical_model(
            primary_plan.fallback_target_logical_model,
            request=request,
        )
        if fallback_plan.channel == primary_plan.channel:
            raise EmbeddingConfigurationError(
                "Embedding fallback target must not use the same channel as the primary plan."
            )
        return fallback_plan

    @staticmethod
    def _merge_provider_responses(
        responses: list[ProviderEmbeddingResponse],
    ) -> ProviderEmbeddingResponse:
        if not responses:
            raise EmbeddingConfigurationError("Embedding provider returned no batches.")

        first = responses[0]
        merged_items = [item for response in responses for item in response.items]
        raw_response = [
            response.raw_response for response in responses if response.raw_response is not None
        ]
        return ProviderEmbeddingResponse(
            provider=first.provider,
            model=first.model,
            dimension=first.dimension,
            items=merged_items,
            usage={
                "prompt_tokens": sum(response.usage.prompt_tokens for response in responses),
                "total_tokens": sum(response.usage.total_tokens for response in responses),
            },
            raw_response={"batches": raw_response} if raw_response else None,
        )


def build_default_embedding_repository(
    settings: EmbeddingSettings,
) -> InMemoryModelConfigRepository:
    catalog_entries = [
        ModelCatalogEntry(
            logical_model=settings.embedding_default_logical_model,
            display_name="Default public embedding model",
            provider="litellm_proxy",
            channel="litellm_proxy",
            gateway_model_name=settings.embedding_default_public_model,
            task_type="embedding",
            capability_tags=["embedding"],
            enabled=settings.embedding_enable_public_proxy,
            is_default=True,
            timeout_ms=settings.embedding_timeout_ms,
            metadata={"batch_size": settings.embedding_batch_size},
        )
    ]
    route_policies = [
        ModelRoutePolicy(
            logical_model=settings.embedding_default_logical_model,
            task_type="embedding",
            priority=100,
            enabled=True,
        )
    ]
    fallback_policies: list[ModelFallbackPolicy] = []

    if settings.private_embedding_model and settings.private_embedding_base_url:
        catalog_entries.append(
            ModelCatalogEntry(
                logical_model=settings.private_embedding_logical_model,
                display_name="Private embedding fallback model",
                provider="private_embedding",
                channel="direct",
                direct_model_name=settings.private_embedding_model,
                base_url=settings.private_embedding_base_url,
                api_key=settings.private_embedding_api_key,
                task_type="embedding",
                capability_tags=["embedding"],
                enabled=True,
                timeout_ms=settings.embedding_timeout_ms,
                metadata={"batch_size": settings.embedding_batch_size},
            )
        )

    if (
        settings.embedding_enable_direct_fallback
        and settings.private_embedding_model
        and settings.private_embedding_base_url
    ):
        fallback_policies.append(
            ModelFallbackPolicy(
                source_logical_model=settings.embedding_default_logical_model,
                channel_fallback_target=settings.private_embedding_logical_model,
                max_fallback_count=1,
                enabled=True,
            )
        )

    return InMemoryModelConfigRepository(
        catalog_entries=catalog_entries,
        route_policies=route_policies,
        fallback_policies=fallback_policies,
    )


def build_embedding_gateway_service(
    *,
    embedding_settings: EmbeddingSettings | None = None,
    gateway_settings: GatewaySettings | None = None,
    repository: InMemoryModelConfigRepository | None = None,
    adapters: dict[str, BaseEmbeddingProviderAdapter] | None = None,
    recorder: InMemoryEmbeddingCallRecorder | None = None,
) -> EmbeddingGatewayService:
    embedding_settings = embedding_settings or EmbeddingSettings.from_env()
    gateway_settings = gateway_settings or GatewaySettings.from_env()
    repository = repository or build_default_embedding_repository(embedding_settings)
    policy_service = ModelPolicyService(repository)
    resolver = EmbeddingModelResolver(
        settings=embedding_settings,
        repository=repository,
        policy_service=policy_service,
    )
    adapters = adapters or {
        "litellm_proxy": LiteLLMProxyEmbeddingAdapter(gateway_settings),
        "direct": PrivateEmbeddingAdapter(embedding_settings),
        "internal_proxy": PrivateEmbeddingAdapter(embedding_settings),
    }
    recorder = recorder or InMemoryEmbeddingCallRecorder()
    return EmbeddingGatewayService(
        settings=embedding_settings,
        resolver=resolver,
        adapters=adapters,
        recorder=recorder,
    )
