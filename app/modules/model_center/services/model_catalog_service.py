from __future__ import annotations

from app.core.exceptions import (
    ModelGatewayConfigurationError,
    ModelGatewayPermissionError,
)
from app.modules.model_center.repositories.in_memory import InMemoryModelConfigRepository
from app.modules.model_center.schemas import ModelCatalogEntry


class ModelCatalogService:
    def __init__(self, repository: InMemoryModelConfigRepository) -> None:
        self._repository = repository

    def get_enabled_model(
        self, logical_model: str, *, tenant_id: str | None = None, app_id: str | None = None
    ) -> ModelCatalogEntry:
        entry = self._repository.get_model(logical_model)
        if entry is None:
            raise ModelGatewayConfigurationError(
                f"Model '{logical_model}' is not defined in the catalog."
            )
        if not entry.enabled:
            raise ModelGatewayConfigurationError(
                f"Model '{logical_model}' is currently disabled."
            )
        if entry.tenant_scope and tenant_id and tenant_id not in entry.tenant_scope:
            raise ModelGatewayPermissionError(
                f"Tenant '{tenant_id}' cannot access model '{logical_model}'."
            )
        if entry.app_scope and app_id and app_id not in entry.app_scope:
            raise ModelGatewayPermissionError(
                f"App '{app_id}' cannot access model '{logical_model}'."
            )
        return entry
