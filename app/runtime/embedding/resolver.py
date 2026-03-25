from __future__ import annotations

from app.core.config import EmbeddingSettings
from app.core.exceptions import EmbeddingConfigurationError, EmbeddingPermissionError
from app.modules.model_center.repositories.in_memory import InMemoryModelConfigRepository
from app.modules.model_center.schemas import ModelCatalogEntry, ModelRoutePolicy
from app.modules.model_center.services.model_policy_service import ModelPolicyService
from app.runtime.embedding.schemas import EmbeddingBatchRequest, ResolvedEmbeddingPlan


class EmbeddingModelResolver:
    def __init__(
        self,
        *,
        settings: EmbeddingSettings,
        repository: InMemoryModelConfigRepository,
        policy_service: ModelPolicyService,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._policy_service = policy_service

    def resolve(self, request: EmbeddingBatchRequest) -> ResolvedEmbeddingPlan:
        logical_model = self._resolve_logical_model(request)
        return self.resolve_logical_model(logical_model, request=request)

    def resolve_logical_model(
        self,
        logical_model: str,
        *,
        request: EmbeddingBatchRequest,
    ) -> ResolvedEmbeddingPlan:
        entry = self._get_enabled_model(
            logical_model,
            tenant_id=request.tenant_id,
            app_id=request.app_id,
        )
        fallback_policy = self._policy_service.get_fallback_policy(logical_model)
        target_model_name = entry.gateway_model_name or entry.direct_model_name
        if not target_model_name:
            raise EmbeddingConfigurationError(
                f"Embedding model '{entry.logical_model}' does not define a target model name."
            )
        timeout_ms = request.timeout_ms or entry.timeout_ms or self._settings.embedding_timeout_ms
        return ResolvedEmbeddingPlan(
            logical_model=entry.logical_model,
            channel=entry.channel,
            provider=entry.provider,
            target_model_name=target_model_name,
            base_url=entry.base_url,
            api_key=entry.api_key,
            timeout_ms=timeout_ms,
            batch_size=self._settings.embedding_batch_size,
            task_type=entry.task_type,
            capability_tags=entry.capability_tags,
            fallback_target_logical_model=(
                fallback_policy.channel_fallback_target if fallback_policy else None
            ),
            max_fallback_count=fallback_policy.max_fallback_count if fallback_policy else 0,
            metadata=dict(entry.metadata),
        )

    def _resolve_logical_model(self, request: EmbeddingBatchRequest) -> str:
        if request.logical_model:
            return request.logical_model

        candidates = [
            policy
            for policy in self._repository.list_route_policies()
            if policy.enabled and self._matches(policy, request)
        ]
        if candidates:
            candidates.sort(
                key=lambda policy: (self._specificity(policy), policy.priority),
                reverse=True,
            )
            return candidates[0].logical_model

        if self._settings.embedding_default_logical_model:
            return self._settings.embedding_default_logical_model

        raise EmbeddingConfigurationError(
            "Unable to resolve a logical embedding model for the current request."
        )

    def _get_enabled_model(
        self,
        logical_model: str,
        *,
        tenant_id: str | None = None,
        app_id: str | None = None,
    ) -> ModelCatalogEntry:
        entry = self._repository.get_model(logical_model)
        if entry is None:
            raise EmbeddingConfigurationError(
                f"Embedding model '{logical_model}' is not defined in the catalog."
            )
        if not entry.enabled:
            raise EmbeddingConfigurationError(
                f"Embedding model '{logical_model}' is currently disabled."
            )
        if entry.tenant_scope and tenant_id and tenant_id not in entry.tenant_scope:
            raise EmbeddingPermissionError(
                f"Tenant '{tenant_id}' cannot access embedding model '{logical_model}'."
            )
        if entry.app_scope and app_id and app_id not in entry.app_scope:
            raise EmbeddingPermissionError(
                f"App '{app_id}' cannot access embedding model '{logical_model}'."
            )
        return entry

    @staticmethod
    def _matches(policy: ModelRoutePolicy, request: EmbeddingBatchRequest) -> bool:
        if policy.tenant_id and policy.tenant_id != request.tenant_id:
            return False
        if policy.app_id and policy.app_id != request.app_id:
            return False
        if policy.scene and policy.scene != request.scene:
            return False
        if policy.task_type and policy.task_type != request.task_type:
            return False
        request_tags = set(request.capability_tags)
        if policy.required_capability_tags and not set(
            policy.required_capability_tags
        ).issubset(request_tags):
            return False
        return True

    @staticmethod
    def _specificity(policy: ModelRoutePolicy) -> int:
        return sum(
            1
            for value in (
                policy.tenant_id,
                policy.app_id,
                policy.scene,
                policy.task_type,
            )
            if value
        ) + (1 if policy.required_capability_tags else 0)
