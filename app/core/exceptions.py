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


class OCRToolError(Exception):
    code = "ocr_unknown_error"
    retryable = False

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class OCRToolConfigurationError(OCRToolError):
    code = "ocr_configuration_error"


class OCRToolValidationError(OCRToolError):
    code = "ocr_validation_error"


class OCRToolAuthenticationError(OCRToolError):
    code = "ocr_authentication_error"


class OCRToolPermissionError(OCRToolError):
    code = "ocr_permission_error"


class OCRToolTimeoutError(OCRToolError):
    code = "ocr_timeout_error"
    retryable = True


class OCRToolProviderUnavailableError(OCRToolError):
    code = "ocr_provider_unavailable"
    retryable = True


class OCRToolBadResponseError(OCRToolError):
    code = "ocr_bad_response_error"
    retryable = True


class OCRToolUnsupportedFileTypeError(OCRToolError):
    code = "ocr_unsupported_file_type"


class OCRToolNotFoundError(OCRToolError):
    code = "ocr_tool_not_found"
