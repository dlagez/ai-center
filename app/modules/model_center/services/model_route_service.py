from __future__ import annotations

from typing import Any

from app.core.config import GatewaySettings
from app.core.exceptions import ModelGatewayConfigurationError
from app.modules.model_center.repositories.in_memory import InMemoryModelConfigRepository
from app.modules.model_center.schemas import ModelRoutePolicy


class ModelRouteService:
    def __init__(
        self,
        repository: InMemoryModelConfigRepository,
        settings: GatewaySettings,
    ) -> None:
        self._repository = repository
        self._settings = settings

    def resolve_logical_model(self, request: Any) -> str:
        if getattr(request, "logical_model", None):
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

        if self._settings.model_gateway_default_logical_model:
            return self._settings.model_gateway_default_logical_model

        raise ModelGatewayConfigurationError(
            "Unable to resolve a logical model for the current request."
        )

    @staticmethod
    def _matches(policy: ModelRoutePolicy, request: Any) -> bool:
        if policy.tenant_id and policy.tenant_id != getattr(request, "tenant_id", None):
            return False
        if policy.app_id and policy.app_id != getattr(request, "app_id", None):
            return False
        if policy.scene and policy.scene != getattr(request, "scene", None):
            return False
        if policy.task_type and policy.task_type != getattr(request, "task_type", None):
            return False
        request_tags = set(getattr(request, "capability_tags", []))
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
