"""Embedding runtime abstractions and executors."""

__all__ = [
    "EmbeddedChunk",
    "EmbeddingBatchRequest",
    "EmbeddingBatchResult",
    "EmbeddingFallbackHop",
    "EmbeddingGatewayService",
    "EmbeddingInputItem",
    "EmbeddingUsageInfo",
    "ProviderEmbeddingResponse",
    "ResolvedEmbeddingPlan",
    "build_default_embedding_repository",
    "build_embedding_gateway_service",
]


def __getattr__(name: str):
    if name in {
        "EmbeddedChunk",
        "EmbeddingBatchRequest",
        "EmbeddingBatchResult",
        "EmbeddingFallbackHop",
        "EmbeddingInputItem",
        "EmbeddingUsageInfo",
        "ProviderEmbeddingResponse",
        "ResolvedEmbeddingPlan",
    }:
        from app.runtime.embedding.schemas import (
            EmbeddedChunk,
            EmbeddingBatchRequest,
            EmbeddingBatchResult,
            EmbeddingFallbackHop,
            EmbeddingInputItem,
            EmbeddingUsageInfo,
            ProviderEmbeddingResponse,
            ResolvedEmbeddingPlan,
        )

        exports = {
            "EmbeddedChunk": EmbeddedChunk,
            "EmbeddingBatchRequest": EmbeddingBatchRequest,
            "EmbeddingBatchResult": EmbeddingBatchResult,
            "EmbeddingFallbackHop": EmbeddingFallbackHop,
            "EmbeddingInputItem": EmbeddingInputItem,
            "EmbeddingUsageInfo": EmbeddingUsageInfo,
            "ProviderEmbeddingResponse": ProviderEmbeddingResponse,
            "ResolvedEmbeddingPlan": ResolvedEmbeddingPlan,
        }
        return exports[name]

    if name in {
        "EmbeddingGatewayService",
        "build_default_embedding_repository",
        "build_embedding_gateway_service",
    }:
        from app.runtime.embedding.gateway_service import (
            EmbeddingGatewayService,
            build_default_embedding_repository,
            build_embedding_gateway_service,
        )

        exports = {
            "EmbeddingGatewayService": EmbeddingGatewayService,
            "build_default_embedding_repository": build_default_embedding_repository,
            "build_embedding_gateway_service": build_embedding_gateway_service,
        }
        return exports[name]

    raise AttributeError(name)
