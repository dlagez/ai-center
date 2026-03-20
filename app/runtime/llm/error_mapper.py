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
except ImportError:  # pragma: no cover - handled when the dependency is absent
    APIConnectionError = type("APIConnectionError", (Exception,), {})
    APIStatusError = type("APIStatusError", (Exception,), {})
    APITimeoutError = type("APITimeoutError", (Exception,), {})
    AuthenticationError = type("AuthenticationError", (Exception,), {})
    BadRequestError = type("BadRequestError", (Exception,), {})
    PermissionDeniedError = type("PermissionDeniedError", (Exception,), {})
    RateLimitError = type("RateLimitError", (Exception,), {})

from app.core.exceptions import (
    ModelGatewayAuthenticationError,
    ModelGatewayBadResponseError,
    ModelGatewayError,
    ModelGatewayPermissionError,
    ModelGatewayProviderUnavailableError,
    ModelGatewayRateLimitError,
    ModelGatewayTimeoutError,
    ModelGatewayValidationError,
)


class ErrorMapper:
    def to_gateway_error(self, error: Exception) -> ModelGatewayError:
        if isinstance(error, ModelGatewayError):
            return error
        if isinstance(error, AuthenticationError):
            return ModelGatewayAuthenticationError(str(error))
        if isinstance(error, PermissionDeniedError):
            return ModelGatewayPermissionError(str(error))
        if isinstance(error, RateLimitError):
            return ModelGatewayRateLimitError(str(error))
        if isinstance(error, APITimeoutError) or isinstance(error, TimeoutError):
            return ModelGatewayTimeoutError(str(error))
        if isinstance(error, BadRequestError):
            return ModelGatewayValidationError(str(error))
        if isinstance(error, APIConnectionError) or isinstance(error, APIStatusError):
            return ModelGatewayProviderUnavailableError(str(error))
        return ModelGatewayBadResponseError(str(error))
