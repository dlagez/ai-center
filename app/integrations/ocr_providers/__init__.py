"""OCR provider adapters."""

from app.integrations.ocr_providers.aliyun_ocr_adapter import AliyunOCRAdapter
from app.integrations.ocr_providers.base import BaseOCRProviderAdapter
from app.integrations.ocr_providers.internal_ocr_adapter import InternalOCRAdapter

__all__ = [
    "AliyunOCRAdapter",
    "BaseOCRProviderAdapter",
    "InternalOCRAdapter",
]
