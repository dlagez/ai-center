from __future__ import annotations


class ModelGatewayError(Exception):
    code = "unknown_error"
    retryable = False

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class ModelGatewayConfigurationError(ModelGatewayError):
    code = "configuration_error"


class ModelGatewayValidationError(ModelGatewayError):
    code = "validation_error"


class ModelGatewayAuthenticationError(ModelGatewayError):
    code = "authentication_error"


class ModelGatewayPermissionError(ModelGatewayError):
    code = "permission_error"


class ModelGatewayRateLimitError(ModelGatewayError):
    code = "rate_limit_error"
    retryable = True


class ModelGatewayTimeoutError(ModelGatewayError):
    code = "timeout_error"
    retryable = True


class ModelGatewayProviderUnavailableError(ModelGatewayError):
    code = "provider_unavailable"
    retryable = True


class ModelGatewayBadResponseError(ModelGatewayError):
    code = "bad_response_error"
    retryable = True
