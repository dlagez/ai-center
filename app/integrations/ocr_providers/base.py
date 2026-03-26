from __future__ import annotations

import base64
import json
import socket
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.exceptions import (
    OCRToolAuthenticationError,
    OCRToolBadResponseError,
    OCRToolPermissionError,
    OCRToolProviderUnavailableError,
    OCRToolTimeoutError,
    OCRToolValidationError,
)
from app.runtime.tools.schemas import (
    OCRLine,
    OCRPage,
    OCRProviderResponse,
    OCRToolRequest,
)


class BaseOCRProviderAdapter(ABC):
    provider_name: str
    supports_pdf_page_range: bool = False

    @abstractmethod
    def extract_text(
        self,
        request: OCRToolRequest,
        *,
        trace_id: str,
    ) -> OCRProviderResponse:
        raise NotImplementedError

    @staticmethod
    def build_source_payload(request: OCRToolRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if request.source_type == "file_path":
            path = Path(request.source_value)
            payload["file_name"] = path.name
            payload["file_base64"] = base64.b64encode(path.read_bytes()).decode("ascii")
        elif request.source_type == "url":
            payload["file_url"] = request.source_value
        elif request.source_type == "base64":
            payload["file_base64"] = request.source_value
        else:  # pragma: no cover - request schema already constrains this
            raise OCRToolValidationError(
                f"Unsupported OCR source type '{request.source_type}'."
            )

        payload["file_type"] = request.file_type
        payload["language_hints"] = request.language_hints
        payload["enable_layout"] = request.enable_layout
        payload["page_range"] = request.page_range
        payload["metadata"] = dict(request.metadata)
        return payload

    @staticmethod
    def post_json(
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_ms: int,
    ) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        request = Request(url=url, data=data, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=timeout_ms / 1000) as response:
                raw_body = response.read().decode("utf-8")
        except HTTPError as exc:
            raw_body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 401:
                raise OCRToolAuthenticationError(raw_body or str(exc)) from exc
            if exc.code == 403:
                raise OCRToolPermissionError(raw_body or str(exc)) from exc
            if exc.code in {408, 429, 500, 502, 503, 504}:
                raise OCRToolProviderUnavailableError(raw_body or str(exc)) from exc
            raise OCRToolBadResponseError(raw_body or str(exc)) from exc
        except socket.timeout as exc:
            raise OCRToolTimeoutError(str(exc)) from exc
        except TimeoutError as exc:
            raise OCRToolTimeoutError(str(exc)) from exc
        except URLError as exc:
            raise OCRToolProviderUnavailableError(str(exc)) from exc

        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise OCRToolBadResponseError(
                "OCR provider returned a non-JSON response."
            ) from exc
        if not isinstance(body, dict):
            raise OCRToolBadResponseError(
                "OCR provider returned an unexpected JSON payload."
            )
        return body

    @classmethod
    def parse_common_response(
        cls,
        body: dict[str, Any],
        *,
        provider: str,
    ) -> OCRProviderResponse:
        pages = cls._extract_pages(body)
        text = cls._coalesce(
            body,
            "text",
            "data.text",
            "result.text",
            "data.result.text",
            "content.text",
        )
        if not text:
            text = "\n\n".join(page.text for page in pages if page.text)
        if not text:
            raise OCRToolBadResponseError(
                f"OCR provider '{provider}' returned no usable text."
            )

        usage = cls._coalesce(body, "usage", "data.usage", "result.usage")
        usage = usage if isinstance(usage, dict) else {}
        model = cls._coalesce(body, "model", "data.model", "result.model")

        return OCRProviderResponse(
            provider=provider,
            model=model if isinstance(model, str) else None,
            text=text,
            pages=pages,
            usage=usage,
            raw_response=body,
        )

    @classmethod
    def _extract_pages(cls, body: dict[str, Any]) -> list[OCRPage]:
        raw_pages = cls._coalesce(body, "pages", "data.pages", "result.pages")
        if isinstance(raw_pages, list):
            pages = [cls._parse_page(item, index) for index, item in enumerate(raw_pages, start=1)]
            return [page for page in pages if page is not None]

        raw_lines = cls._coalesce(body, "lines", "data.lines", "result.lines")
        if isinstance(raw_lines, list):
            page = OCRPage(
                page_no=1,
                text=cls._join_line_text(raw_lines),
                lines=cls._parse_lines(raw_lines, page_no=1),
            )
            return [page]
        return []

    @classmethod
    def _parse_page(cls, raw_page: Any, index: int) -> OCRPage | None:
        if not isinstance(raw_page, dict):
            return None
        page_no = raw_page.get("page_no") or raw_page.get("page") or index
        raw_lines = raw_page.get("lines") or raw_page.get("items") or []
        if isinstance(raw_lines, list):
            lines = cls._parse_lines(raw_lines, page_no=int(page_no))
        else:
            lines = []

        text = raw_page.get("text")
        if not isinstance(text, str):
            text = "\n".join(line.text for line in lines if line.text)
        return OCRPage(page_no=int(page_no), text=text or "", lines=lines)

    @classmethod
    def _parse_lines(cls, raw_lines: list[Any], *, page_no: int) -> list[OCRLine]:
        lines: list[OCRLine] = []
        for item in raw_lines:
            if isinstance(item, str):
                lines.append(OCRLine(text=item, page_no=page_no))
                continue
            if not isinstance(item, dict):
                continue
            text = item.get("text") or item.get("content")
            if not isinstance(text, str):
                continue
            bbox = item.get("bbox") or item.get("box") or item.get("polygon")
            lines.append(
                OCRLine(
                    text=text,
                    page_no=int(item.get("page_no") or item.get("page") or page_no),
                    bbox=cls._normalize_bbox(bbox),
                    confidence=cls._normalize_confidence(item.get("confidence")),
                )
            )
        return lines

    @staticmethod
    def _normalize_bbox(value: Any) -> list[float] | None:
        if not isinstance(value, list):
            return None
        normalized: list[float] = []
        for item in value:
            if not isinstance(item, (int, float)):
                return None
            normalized.append(float(item))
        return normalized or None

    @staticmethod
    def _normalize_confidence(value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        return None

    @staticmethod
    def _join_line_text(raw_lines: list[Any]) -> str:
        parts: list[str] = []
        for item in raw_lines:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)

    @staticmethod
    def _coalesce(body: dict[str, Any], *paths: str) -> Any:
        for path in paths:
            current: Any = body
            for segment in path.split("."):
                if not isinstance(current, dict) or segment not in current:
                    break
                current = current[segment]
            else:
                return current
        return None
