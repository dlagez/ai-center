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


class DocumentParseError(Exception):
    code = "document_parse_unknown_error"
    retryable = False

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class DocumentParseConfigurationError(DocumentParseError):
    code = "document_parse_configuration_error"


class DocumentParseValidationError(DocumentParseError):
    code = "document_parse_validation_error"


class DocumentParseUnsupportedFileTypeError(DocumentParseError):
    code = "document_parse_unsupported_file_type"


class DocumentParseBadResponseError(DocumentParseError):
    code = "document_parse_bad_response_error"


class DocumentParseCacheError(DocumentParseError):
    code = "document_parse_cache_error"


class ChunkingError(Exception):
    code = "chunking_unknown_error"
    retryable = False

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class ChunkingConfigurationError(ChunkingError):
    code = "chunking_configuration_error"


class ChunkingValidationError(ChunkingError):
    code = "chunking_validation_error"


class ChunkingEmptyInputError(ChunkingError):
    code = "chunking_empty_input_error"


class ChunkingBadDocumentError(ChunkingError):
    code = "chunking_bad_document_error"


class ChunkingPolicyError(ChunkingError):
    code = "chunking_policy_error"
