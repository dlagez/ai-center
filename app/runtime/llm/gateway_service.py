from __future__ import annotations

import time
import uuid
from collections.abc import Iterator

from app.core.config import GatewaySettings
from app.core.exceptions import (
    ModelGatewayConfigurationError,
    ModelGatewayError,
)
from app.integrations.model_providers.base import BaseModelProviderAdapter
from app.integrations.model_providers.litellm_proxy_adapter import LiteLLMProxyAdapter
from app.integrations.model_providers.private_llm_adapter import PrivateLLMAdapter
from app.modules.model_center.repositories.in_memory import InMemoryModelConfigRepository
from app.modules.model_center.services.model_catalog_service import ModelCatalogService
from app.modules.model_center.services.model_policy_service import ModelPolicyService
from app.modules.model_center.services.model_route_service import ModelRouteService
from app.observability.metrics.llm_call_recorder import InMemoryLLMCallRecorder
from app.runtime.llm.error_mapper import ErrorMapper
from app.runtime.llm.model_resolver import ModelResolver
from app.runtime.llm.response_normalizer import ResponseNormalizer
from app.runtime.llm.schemas import (
    FallbackHop,
    LLMInvokeRequest,
    LLMInvokeResult,
    LLMStreamChunk,
    ProviderInvokeResponse,
    ResolvedInvocationPlan,
)


FALLBACK_ELIGIBLE_ERRORS = {
    "timeout_error",
    "rate_limit_error",
    "provider_unavailable",
    "bad_response_error",
    "unknown_error",
}


class GatewayService:
    def __init__(
        self,
        *,
        settings: GatewaySettings,
        resolver: ModelResolver,
        adapters: dict[str, BaseModelProviderAdapter],
        recorder: InMemoryLLMCallRecorder,
        error_mapper: ErrorMapper | None = None,
        normalizer: ResponseNormalizer | None = None,
    ) -> None:
        self._settings = settings
        self._resolver = resolver
        self._adapters = adapters
        self._recorder = recorder
        self._error_mapper = error_mapper or ErrorMapper()
        self._normalizer = normalizer or ResponseNormalizer()

    def invoke_chat(self, request: LLMInvokeRequest) -> LLMInvokeResult:
        trace_id = self._new_trace_id()
        primary_plan = self._resolver.resolve(request)
        fallback_hops: list[FallbackHop] = []

        try:
            response, latency_ms = self._invoke_plan(
                plan=primary_plan, request=request, trace_id=trace_id
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
            primary_error = self._error_mapper.to_gateway_error(exc)

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
            FallbackHop(
                source_logical_model=primary_plan.logical_model,
                target_logical_model=fallback_plan.logical_model,
                target_channel=fallback_plan.channel,
                reason=primary_error.code,
            )
        )
        try:
            response, latency_ms = self._invoke_plan(
                plan=fallback_plan, request=request, trace_id=trace_id
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
            fallback_error = self._error_mapper.to_gateway_error(exc)
            self._recorder.record_failure(
                request=request,
                trace_id=trace_id,
                plan=fallback_plan,
                error=fallback_error,
                fallback_count=len(fallback_hops),
            )
            raise fallback_error

    def stream_chat(self, request: LLMInvokeRequest) -> Iterator[LLMStreamChunk]:
        trace_id = self._new_trace_id()
        primary_plan = self._resolver.resolve(request)

        def stream() -> Iterator[LLMStreamChunk]:
            fallback_hops: list[FallbackHop] = []
            first_yield_emitted = False
            try:
                adapter = self._get_adapter(primary_plan.channel)
                for chunk in adapter.stream(
                    plan=primary_plan, request=request, trace_id=trace_id
                ):
                    first_yield_emitted = True
                    yield chunk
                self._recorder.record_stream_success(
                    request=request,
                    trace_id=trace_id,
                    logical_model=primary_plan.logical_model,
                    final_channel=primary_plan.channel,
                    final_provider=primary_plan.provider,
                    final_model=primary_plan.target_model_name,
                    fallback_count=0,
                )
                return
            except Exception as exc:
                error = self._error_mapper.to_gateway_error(exc)
                if first_yield_emitted:
                    self._recorder.record_failure(
                        request=request,
                        trace_id=trace_id,
                        plan=primary_plan,
                        error=error,
                        fallback_count=0,
                    )
                    raise error

            fallback_plan = self._resolve_fallback_plan(
                primary_plan=primary_plan,
                request=request,
                error=error,
            )
            if fallback_plan is None:
                self._recorder.record_failure(
                    request=request,
                    trace_id=trace_id,
                    plan=primary_plan,
                    error=error,
                    fallback_count=0,
                )
                raise error

            fallback_hops.append(
                FallbackHop(
                    source_logical_model=primary_plan.logical_model,
                    target_logical_model=fallback_plan.logical_model,
                    target_channel=fallback_plan.channel,
                    reason=error.code,
                )
            )
            try:
                adapter = self._get_adapter(fallback_plan.channel)
                for chunk in adapter.stream(
                    plan=fallback_plan, request=request, trace_id=trace_id
                ):
                    yield chunk
                self._recorder.record_stream_success(
                    request=request,
                    trace_id=trace_id,
                    logical_model=primary_plan.logical_model,
                    final_channel=fallback_plan.channel,
                    final_provider=fallback_plan.provider,
                    final_model=fallback_plan.target_model_name,
                    fallback_count=len(fallback_hops),
                )
            except Exception as exc:
                fallback_error = self._error_mapper.to_gateway_error(exc)
                self._recorder.record_failure(
                    request=request,
                    trace_id=trace_id,
                    plan=fallback_plan,
                    error=fallback_error,
                    fallback_count=len(fallback_hops),
                )
                raise fallback_error

        return stream()

    def _invoke_plan(
        self,
        *,
        plan: ResolvedInvocationPlan,
        request: LLMInvokeRequest,
        trace_id: str,
    ) -> tuple[ProviderInvokeResponse, int]:
        start_time = time.perf_counter()
        adapter = self._get_adapter(plan.channel)
        response = adapter.invoke(plan=plan, request=request, trace_id=trace_id)
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        return response, latency_ms

    def _get_adapter(self, channel: str) -> BaseModelProviderAdapter:
        adapter = self._adapters.get(channel)
        if adapter is None and channel == "internal_proxy":
            adapter = self._adapters.get("direct")
        if adapter is None:
            raise ModelGatewayConfigurationError(
                f"No adapter is registered for channel '{channel}'."
            )
        return adapter

    def _resolve_fallback_plan(
        self,
        *,
        primary_plan: ResolvedInvocationPlan,
        request: LLMInvokeRequest,
        error: ModelGatewayError,
    ) -> ResolvedInvocationPlan | None:
        if error.code not in FALLBACK_ELIGIBLE_ERRORS:
            return None
        if primary_plan.max_fallback_count <= 0:
            return None
        if not primary_plan.fallback_target_logical_model:
            return None
        if not self._settings.model_gateway_enable_direct_fallback:
            return None

        fallback_plan = self._resolver.resolve_logical_model(
            primary_plan.fallback_target_logical_model,
            request=request,
        )
        if fallback_plan.channel == primary_plan.channel:
            raise ModelGatewayConfigurationError(
                "Fallback target must not use the same channel as the primary plan."
            )
        return fallback_plan

    @staticmethod
    def _new_trace_id() -> str:
        return uuid.uuid4().hex


def build_gateway_service(
    *,
    settings: GatewaySettings | None = None,
    repository: InMemoryModelConfigRepository | None = None,
    adapters: dict[str, BaseModelProviderAdapter] | None = None,
    recorder: InMemoryLLMCallRecorder | None = None,
) -> GatewayService:
    settings = settings or GatewaySettings.from_env()
    repository = repository or InMemoryModelConfigRepository.from_settings(settings)
    catalog_service = ModelCatalogService(repository)
    route_service = ModelRouteService(repository, settings)
    policy_service = ModelPolicyService(repository)
    resolver = ModelResolver(
        settings=settings,
        catalog_service=catalog_service,
        route_service=route_service,
        policy_service=policy_service,
    )
    adapters = adapters or {
        "litellm_proxy": LiteLLMProxyAdapter(settings),
        "direct": PrivateLLMAdapter(settings),
        "internal_proxy": PrivateLLMAdapter(settings),
    }
    recorder = recorder or InMemoryLLMCallRecorder()
    return GatewayService(
        settings=settings,
        resolver=resolver,
        adapters=adapters,
        recorder=recorder,
    )
