from __future__ import annotations

from collections.abc import Iterable

from app.core.config import GatewaySettings
from app.modules.model_center.schemas import (
    ModelCatalogEntry,
    ModelFallbackPolicy,
    ModelRoutePolicy,
)


class InMemoryModelConfigRepository:
    def __init__(
        self,
        *,
        catalog_entries: Iterable[ModelCatalogEntry] | None = None,
        route_policies: Iterable[ModelRoutePolicy] | None = None,
        fallback_policies: Iterable[ModelFallbackPolicy] | None = None,
    ) -> None:
        self._catalog_entries = {
            entry.logical_model: entry for entry in (catalog_entries or [])
        }
        self._route_policies = list(route_policies or [])
        self._fallback_policies = {
            policy.source_logical_model: policy for policy in (fallback_policies or [])
        }

    @classmethod
    def from_settings(cls, settings: GatewaySettings) -> "InMemoryModelConfigRepository":
        catalog_entries = [
            ModelCatalogEntry(
                logical_model=settings.model_gateway_default_logical_model,
                display_name="Default public chat model",
                provider="litellm_proxy",
                channel="litellm_proxy",
                gateway_model_name=settings.model_gateway_default_public_model,
                task_type="chat",
                capability_tags=["tool-calling"],
                enabled=settings.model_gateway_enable_public_proxy,
                is_default=True,
                timeout_ms=settings.model_gateway_timeout_ms,
            )
        ]
        route_policies = [
            ModelRoutePolicy(
                logical_model=settings.model_gateway_default_logical_model,
                scene="chat",
                task_type="chat",
                priority=100,
                enabled=True,
            )
        ]
        fallback_policies: list[ModelFallbackPolicy] = []

        if settings.private_llm_model and settings.private_llm_base_url:
            catalog_entries.append(
                ModelCatalogEntry(
                    logical_model=settings.private_llm_logical_model,
                    display_name="Private fallback model",
                    provider="private_llm",
                    channel="direct",
                    direct_model_name=settings.private_llm_model,
                    base_url=settings.private_llm_base_url,
                    api_key=settings.private_llm_api_key,
                    task_type="chat",
                    enabled=True,
                    timeout_ms=settings.model_gateway_timeout_ms,
                )
            )

        if settings.model_gateway_enable_direct_fallback and settings.private_llm_model:
            fallback_policies.append(
                ModelFallbackPolicy(
                    source_logical_model=settings.model_gateway_default_logical_model,
                    channel_fallback_target=settings.private_llm_logical_model,
                    max_fallback_count=1,
                    enabled=True,
                )
            )

        return cls(
            catalog_entries=catalog_entries,
            route_policies=route_policies,
            fallback_policies=fallback_policies,
        )

    def get_model(self, logical_model: str) -> ModelCatalogEntry | None:
        return self._catalog_entries.get(logical_model)

    def list_models(self) -> list[ModelCatalogEntry]:
        return list(self._catalog_entries.values())

    def list_route_policies(self) -> list[ModelRoutePolicy]:
        return list(self._route_policies)

    def get_fallback_policy(self, logical_model: str) -> ModelFallbackPolicy | None:
        return self._fallback_policies.get(logical_model)
