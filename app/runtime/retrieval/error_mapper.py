from __future__ import annotations

from app.core.exceptions import (
    EmbeddingError,
    RetrievalConfigurationError,
    RetrievalEmbeddingError,
    RetrievalError,
    RetrievalResultError,
    RetrievalStoreTimeoutError,
    RetrievalStoreUnavailableError,
    RetrievalUnknownError,
    RetrievalValidationError,
    VectorStoreCollectionError,
    VectorStoreConfigurationError,
    VectorStoreDimensionMismatchError,
    VectorStoreError,
    VectorStoreProviderUnavailableError,
    VectorStoreQueryError,
    VectorStoreTimeoutError,
    VectorStoreValidationError,
)


class RetrievalErrorMapper:
    def to_retrieval_error(self, error: Exception) -> RetrievalError:
        if isinstance(error, RetrievalError):
            return error
        if isinstance(error, EmbeddingError):
            return RetrievalEmbeddingError(str(error))
        if isinstance(error, VectorStoreTimeoutError):
            return RetrievalStoreTimeoutError(str(error))
        if isinstance(error, VectorStoreProviderUnavailableError):
            return RetrievalStoreUnavailableError(str(error))
        if isinstance(error, (VectorStoreConfigurationError, VectorStoreCollectionError)):
            return RetrievalConfigurationError(str(error))
        if isinstance(
            error,
            (VectorStoreValidationError, VectorStoreDimensionMismatchError),
        ):
            return RetrievalValidationError(str(error))
        if isinstance(error, (VectorStoreQueryError, VectorStoreError)):
            return RetrievalResultError(str(error))
        return RetrievalUnknownError(str(error))
