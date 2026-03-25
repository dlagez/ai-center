"""Embedding provider adapters."""

from app.integrations.embedding_providers.base import BaseEmbeddingProviderAdapter
from app.integrations.embedding_providers.litellm_proxy_embedding_adapter import (
    LiteLLMProxyEmbeddingAdapter,
)
from app.integrations.embedding_providers.private_embedding_adapter import (
    PrivateEmbeddingAdapter,
)

__all__ = [
    "BaseEmbeddingProviderAdapter",
    "LiteLLMProxyEmbeddingAdapter",
    "PrivateEmbeddingAdapter",
]
