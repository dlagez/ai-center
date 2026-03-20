from __future__ import annotations

import os
from dataclasses import dataclass


def _get_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return int(raw_value)


@dataclass(frozen=True)
class GatewaySettings:
    model_gateway_base_url: str
    model_gateway_api_key: str
    model_gateway_timeout_ms: int
    model_gateway_enable_public_proxy: bool
    model_gateway_enable_direct_fallback: bool
    model_gateway_default_logical_model: str
    model_gateway_default_public_model: str
    private_llm_base_url: str | None
    private_llm_api_key: str | None
    private_llm_model: str | None
    private_llm_logical_model: str

    @classmethod
    def from_env(cls) -> "GatewaySettings":
        return cls(
            model_gateway_base_url=os.getenv(
                "MODEL_GATEWAY_BASE_URL", "http://litellm-proxy:4000"
            ),
            model_gateway_api_key=os.getenv("MODEL_GATEWAY_API_KEY", "change-me"),
            model_gateway_timeout_ms=_get_int("MODEL_GATEWAY_TIMEOUT_MS", 60000),
            model_gateway_enable_public_proxy=_get_bool(
                "MODEL_GATEWAY_ENABLE_PUBLIC_PROXY", True
            ),
            model_gateway_enable_direct_fallback=_get_bool(
                "MODEL_GATEWAY_ENABLE_DIRECT_FALLBACK", True
            ),
            model_gateway_default_logical_model=os.getenv(
                "MODEL_GATEWAY_DEFAULT_LOGICAL_MODEL", "chat_default"
            ),
            model_gateway_default_public_model=os.getenv(
                "MODEL_GATEWAY_DEFAULT_PUBLIC_MODEL", "public-chat-default"
            ),
            private_llm_base_url=os.getenv("PRIVATE_LLM_BASE_URL") or None,
            private_llm_api_key=os.getenv("PRIVATE_LLM_API_KEY") or None,
            private_llm_model=os.getenv("PRIVATE_LLM_MODEL") or None,
            private_llm_logical_model=os.getenv(
                "PRIVATE_LLM_LOGICAL_MODEL", "private_sensitive_backup"
            ),
        )
