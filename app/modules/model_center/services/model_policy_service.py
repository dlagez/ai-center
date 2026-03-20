from __future__ import annotations

from app.modules.model_center.repositories.in_memory import InMemoryModelConfigRepository
from app.modules.model_center.schemas import ModelFallbackPolicy


class ModelPolicyService:
    def __init__(self, repository: InMemoryModelConfigRepository) -> None:
        self._repository = repository

    def get_fallback_policy(self, logical_model: str) -> ModelFallbackPolicy | None:
        policy = self._repository.get_fallback_policy(logical_model)
        if policy is None or not policy.enabled:
            return None
        return policy
