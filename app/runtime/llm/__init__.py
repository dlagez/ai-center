"""LLM gateway runtime package."""

__all__ = [
    "GatewayService",
    "build_gateway_service",
    "LLMInvokeRequest",
    "LLMInvokeResult",
    "LLMStreamChunk",
]


def __getattr__(name: str):
    if name in {"GatewayService", "build_gateway_service"}:
        from app.runtime.llm.gateway_service import GatewayService, build_gateway_service

        exports = {
            "GatewayService": GatewayService,
            "build_gateway_service": build_gateway_service,
        }
        return exports[name]
    if name in {"LLMInvokeRequest", "LLMInvokeResult", "LLMStreamChunk"}:
        from app.runtime.llm.schemas import (
            LLMInvokeRequest,
            LLMInvokeResult,
            LLMStreamChunk,
        )

        exports = {
            "LLMInvokeRequest": LLMInvokeRequest,
            "LLMInvokeResult": LLMInvokeResult,
            "LLMStreamChunk": LLMStreamChunk,
        }
        return exports[name]
    raise AttributeError(name)
