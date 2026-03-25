from __future__ import annotations

try:
    from openai import (
        APIConnectionError,
        APIStatusError,
        APITimeoutError,
        AuthenticationError,
        BadRequestError,
        PermissionDeniedError,
        RateLimitError,
    )
except ImportError:  # pragma: no cover
    APIConnectionError = type("APIConnectionError", (Exception,), {})
    APIStatusError = type("APIStatusError", (Exception,), {})
    APITimeoutError = type("APITimeoutError", (Exception,), {})
    AuthenticationError = type("AuthenticationError", (Exception,), {})
    BadRequestError = type("BadRequestError", (Exception,), {})
    PermissionDeniedError = type("PermissionDeniedError", (Exception,), {})
    RateLimitError = type("RateLimitError", (Exception,), {})

from app.core.exceptions import (
    EmbeddingAuthenticationError,
    EmbeddingBadResponseError,
    EmbeddingError,
    EmbeddingPermissionError,
    EmbeddingProviderUnavailableError,
    EmbeddingRateLimitError,
    EmbeddingTimeoutError,
    EmbeddingValidationError,
)


class EmbeddingErrorMapper:
    def to_embedding_error(self, error: Exception) -> EmbeddingError:
        if isinstance(error, EmbeddingError):
            return error
        if isinstance(error, AuthenticationError):
            return EmbeddingAuthenticationError(str(error))
        if isinstance(error, PermissionDeniedError):
            return EmbeddingPermissionError(str(error))
        if isinstance(error, RateLimitError):
            return EmbeddingRateLimitError(str(error))
        if isinstance(error, APITimeoutError) or isinstance(error, TimeoutError):
            return EmbeddingTimeoutError(str(error))
        if isinstance(error, BadRequestError):
            return EmbeddingValidationError(str(error))
        if isinstance(error, APIConnectionError) or isinstance(error, APIStatusError):
            return EmbeddingProviderUnavailableError(str(error))
        return EmbeddingBadResponseError(str(error))
