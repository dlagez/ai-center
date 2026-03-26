"""OCR provider adapters."""

from app.integrations.ocr_providers.aliyun_ocr_adapter import AliyunOCRAdapter
from app.integrations.ocr_providers.base import BaseOCRProviderAdapter
from app.integrations.ocr_providers.internal_ocr_adapter import InternalOCRAdapter
from app.integrations.ocr_providers.internal_text_ocr_adapter import (
    InternalTextOCRAdapter,
)

__all__ = [
    "AliyunOCRAdapter",
    "BaseOCRProviderAdapter",
    "InternalOCRAdapter",
    "InternalTextOCRAdapter",
]
