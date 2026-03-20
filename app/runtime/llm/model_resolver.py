from __future__ import annotations

from app.core.config import GatewaySettings
from app.core.exceptions import ModelGatewayConfigurationError
from app.modules.model_center.schemas import ModelCatalogEntry
from app.modules.model_center.services.model_catalog_service import ModelCatalogService
from app.modules.model_center.services.model_policy_service import ModelPolicyService
from app.modules.model_center.services.model_route_service import ModelRouteService
from app.runtime.llm.schemas import LLMInvokeRequest, ResolvedInvocationPlan


class ModelResolver:
    def __init__(
        self,
        *,
        settings: GatewaySettings,
        catalog_service: ModelCatalogService,
        route_service: ModelRouteService,
        policy_service: ModelPolicyService,
    ) -> None:
        self._settings = settings
        self._catalog_service = catalog_service
        self._route_service = route_service
        self._policy_service = policy_service

    def resolve(self, request: LLMInvokeRequest) -> ResolvedInvocationPlan:
        logical_model = self._route_service.resolve_logical_model(request)
        return self.resolve_logical_model(logical_model, request=request)

    def resolve_logical_model(
        self,
        logical_model: str,
        *,
        request: LLMInvokeRequest,
    ) -> ResolvedInvocationPlan:
        entry = self._catalog_service.get_enabled_model(
            logical_model,
            tenant_id=request.tenant_id,
            app_id=request.app_id,
        )
        fallback_policy = self._policy_service.get_fallback_policy(logical_model)
        return self._build_plan(
            entry=entry,
            request=request,
            fallback_target_logical_model=(
                fallback_policy.channel_fallback_target if fallback_policy else None
            ),
            max_fallback_count=fallback_policy.max_fallback_count if fallback_policy else 0,
        )

    def _build_plan(
        self,
        *,
        entry: ModelCatalogEntry,
        request: LLMInvokeRequest,
        fallback_target_logical_model: str | None,
        max_fallback_count: int,
    ) -> ResolvedInvocationPlan:
        target_model_name = entry.gateway_model_name or entry.direct_model_name
        if not target_model_name:
            raise ModelGatewayConfigurationError(
                f"Model '{entry.logical_model}' does not define a target model name."
            )
        timeout_ms = request.timeout_ms or entry.timeout_ms or self._settings.model_gateway_timeout_ms
        return ResolvedInvocationPlan(
            logical_model=entry.logical_model,
            channel=entry.channel,
            provider=entry.provider,
            target_model_name=target_model_name,
            base_url=entry.base_url,
            api_key=entry.api_key,
            timeout_ms=timeout_ms,
            task_type=entry.task_type,
            capability_tags=entry.capability_tags,
            fallback_target_logical_model=fallback_target_logical_model,
            max_fallback_count=max_fallback_count,
            metadata=dict(entry.metadata),
        )
