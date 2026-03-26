from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel


_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
    "cookie",
)
_EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_PHONE_RE = re.compile(r"(?<!\d)(1\d{10})(?!\d)")


def truncate_text(text: str | None, max_chars: int) -> str | None:
    if text is None or len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}...<truncated:{len(text) - max_chars}>"


def sanitize_value(
    value: Any,
    *,
    max_text_chars: int,
    redact_pii: bool,
    key: str | None = None,
) -> Any:
    if key and _is_sensitive_key(key):
        return "***"

    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        return truncate_text(_redact_text(value) if redact_pii else value, max_text_chars)

    if isinstance(value, Path):
        return truncate_text(str(value), max_text_chars)

    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"

    if isinstance(value, BaseModel):
        return sanitize_value(
            value.model_dump(mode="json"),
            max_text_chars=max_text_chars,
            redact_pii=redact_pii,
            key=key,
        )

    if isinstance(value, Mapping):
        return {
            str(item_key): sanitize_value(
                item_value,
                max_text_chars=max_text_chars,
                redact_pii=redact_pii,
                key=str(item_key),
            )
            for item_key, item_value in value.items()
        }

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [
            sanitize_value(
                item,
                max_text_chars=max_text_chars,
                redact_pii=redact_pii,
            )
            for item in value
        ]

    return truncate_text(repr(value), max_text_chars)


def sanitize_messages(
    messages: list[dict[str, Any]],
    *,
    capture_content: bool,
    max_text_chars: int,
    redact_pii: bool,
) -> list[dict[str, Any]]:
    sanitized_messages: list[dict[str, Any]] = []
    for message in messages:
        sanitized_message = {
            "role": message.get("role"),
        }
        if capture_content and "content" in message:
            sanitized_message["content"] = sanitize_value(
                message.get("content"),
                max_text_chars=max_text_chars,
                redact_pii=redact_pii,
            )
        if "name" in message:
            sanitized_message["name"] = sanitize_value(
                message.get("name"),
                max_text_chars=max_text_chars,
                redact_pii=redact_pii,
            )
        if "tool_calls" in message:
            sanitized_message["tool_calls"] = sanitize_value(
                message.get("tool_calls"),
                max_text_chars=max_text_chars,
                redact_pii=redact_pii,
            )
        sanitized_messages.append(sanitized_message)
    return sanitized_messages


def summarize_hits(
    hits: Sequence[Any],
    *,
    capture_text: bool,
    max_text_chars: int,
    redact_pii: bool,
    limit: int = 5,
) -> list[dict[str, Any]]:
    summarized_hits: list[dict[str, Any]] = []
    for hit in list(hits)[:limit]:
        item = {
            "chunk_id": getattr(hit, "chunk_id", None),
            "document_id": getattr(hit, "document_id", None),
            "score": getattr(hit, "score", None),
        }
        if capture_text:
            item["text"] = sanitize_value(
                getattr(hit, "text", None),
                max_text_chars=max_text_chars,
                redact_pii=redact_pii,
            )
        metadata = getattr(hit, "metadata", None)
        if metadata:
            item["metadata"] = sanitize_value(
                metadata,
                max_text_chars=max_text_chars,
                redact_pii=redact_pii,
            )
        source_position = getattr(hit, "source_position", None)
        if source_position:
            item["source_position"] = sanitize_value(
                source_position,
                max_text_chars=max_text_chars,
                redact_pii=redact_pii,
            )
        summarized_hits.append(item)
    return summarized_hits


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def _redact_text(text: str) -> str:
    redacted = _EMAIL_RE.sub("***@***", text)
    redacted = _PHONE_RE.sub("***", redacted)
    return redacted
