from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from app.core.config import DocumentParseSettings
from app.core.exceptions import (
    DocumentParseUnsupportedFileTypeError,
    DocumentParseValidationError,
)
from app.modules.document_center.schemas import (
    DocumentParseRequest,
    NormalizedDocumentAsset,
)

FILE_TYPE_ALIASES = {
    "markdown": "md",
    "htm": "html",
}

EXTENSION_FILE_TYPES = {
    ".pdf": "pdf",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".bmp": "image",
    ".tif": "image",
    ".tiff": "image",
    ".webp": "image",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".pptx": "pptx",
    ".txt": "txt",
    ".md": "md",
    ".markdown": "md",
    ".html": "html",
    ".htm": "html",
    ".csv": "csv",
}

SUPPORTED_FILE_TYPES = set(EXTENSION_FILE_TYPES.values()) | {"image", "pdf"}


class FileIdentityService:
    def __init__(self, settings: DocumentParseSettings) -> None:
        self._settings = settings

    def normalize(self, request: DocumentParseRequest) -> NormalizedDocumentAsset:
        file_name = self._resolve_file_name(request)
        content_bytes = self._load_bytes(request)
        if not content_bytes:
            raise DocumentParseValidationError("Document content must not be empty.")

        file_type = self._resolve_file_type(request, file_name=file_name)
        asset_hash = hashlib.sha256(content_bytes).hexdigest()
        return NormalizedDocumentAsset(
            source_type=request.source_type,
            source_value=request.source_value,
            file_name=file_name,
            file_type=file_type,
            content_bytes=content_bytes,
            asset_hash=asset_hash,
        )

    def _load_bytes(self, request: DocumentParseRequest) -> bytes:
        if request.source_type == "file_path":
            path = Path(request.source_value)
            if not path.exists():
                raise DocumentParseValidationError(
                    f"File '{request.source_value}' does not exist."
                )
            if not path.is_file():
                raise DocumentParseValidationError(
                    f"Source '{request.source_value}' is not a file."
                )
            return path.read_bytes()

        if request.source_type == "base64":
            try:
                return base64.b64decode(request.source_value, validate=True)
            except ValueError as exc:
                raise DocumentParseValidationError(
                    "Base64 document input is invalid."
                ) from exc

        parsed = urlparse(request.source_value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise DocumentParseValidationError(
                "Document URL sources must use an absolute http or https URL."
            )
        with urlopen(
            request.source_value,
            timeout=self._settings.document_parse_download_timeout_ms / 1000,
        ) as response:
            return response.read()

    def _resolve_file_name(self, request: DocumentParseRequest) -> str:
        if request.file_name:
            return request.file_name
        if request.source_type == "file_path":
            return Path(request.source_value).name
        if request.source_type == "url":
            path = urlparse(request.source_value).path
            name = Path(path).name
            if name:
                return name
        if request.file_type:
            normalized_type = FILE_TYPE_ALIASES.get(request.file_type, request.file_type)
            suffix = "bin" if normalized_type == "image" else normalized_type
            return f"document.{suffix}"
        return "document.bin"

    def _resolve_file_type(self, request: DocumentParseRequest, *, file_name: str) -> str:
        if request.file_type:
            normalized = FILE_TYPE_ALIASES.get(
                request.file_type.lower(), request.file_type.lower()
            )
            if normalized in SUPPORTED_FILE_TYPES:
                return normalized
            raise DocumentParseUnsupportedFileTypeError(
                f"Unsupported document file type '{request.file_type}'."
            )

        suffix = Path(file_name).suffix.lower()
        file_type = EXTENSION_FILE_TYPES.get(suffix)
        if file_type:
            return file_type
        raise DocumentParseUnsupportedFileTypeError(
            f"Unsupported document file type for source '{request.source_value}'."
        )
