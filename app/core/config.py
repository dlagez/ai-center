from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


_DOTENV_LOADED = False


def load_dotenv_if_present() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return

    project_root = Path(__file__).resolve().parents[2]
    candidate_paths = [project_root / ".env", Path.cwd() / ".env"]
    seen_paths: set[Path] = set()

    for candidate in candidate_paths:
        resolved_candidate = candidate.resolve()
        if resolved_candidate in seen_paths or not candidate.exists():
            continue
        seen_paths.add(resolved_candidate)
        _load_dotenv_file(candidate)

    _DOTENV_LOADED = True


def _load_dotenv_file(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        key = name.strip()
        if not key:
            continue
        normalized_value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, normalized_value)


def _get_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return int(raw_value)


def _get_optional(name: str) -> str | None:
    raw_value = os.getenv(name)
    if raw_value is None:
        return None
    stripped = raw_value.strip()
    return stripped or None


load_dotenv_if_present()


@dataclass(frozen=True)
class GatewaySettings:
    model_gateway_base_url: str
    model_gateway_api_key: str
    model_gateway_timeout_ms: int
    model_gateway_enable_public_proxy: bool
    model_gateway_enable_direct_fallback: bool
    model_gateway_default_logical_model: str
    model_gateway_default_public_model: str
    private_llm_base_url: str | None
    private_llm_api_key: str | None
    private_llm_model: str | None
    private_llm_logical_model: str

    @classmethod
    def from_env(cls) -> "GatewaySettings":
        return cls(
            model_gateway_base_url=os.getenv(
                "MODEL_GATEWAY_BASE_URL", "http://litellm-proxy:4000"
            ),
            model_gateway_api_key=os.getenv("MODEL_GATEWAY_API_KEY", "change-me"),
            model_gateway_timeout_ms=_get_int("MODEL_GATEWAY_TIMEOUT_MS", 60000),
            model_gateway_enable_public_proxy=_get_bool(
                "MODEL_GATEWAY_ENABLE_PUBLIC_PROXY", True
            ),
            model_gateway_enable_direct_fallback=_get_bool(
                "MODEL_GATEWAY_ENABLE_DIRECT_FALLBACK", True
            ),
            model_gateway_default_logical_model=os.getenv(
                "MODEL_GATEWAY_DEFAULT_LOGICAL_MODEL", "chat_default"
            ),
            model_gateway_default_public_model=os.getenv(
                "MODEL_GATEWAY_DEFAULT_PUBLIC_MODEL", "public-chat-default"
            ),
            private_llm_base_url=os.getenv("PRIVATE_LLM_BASE_URL") or None,
            private_llm_api_key=os.getenv("PRIVATE_LLM_API_KEY") or None,
            private_llm_model=os.getenv("PRIVATE_LLM_MODEL") or None,
            private_llm_logical_model=os.getenv(
                "PRIVATE_LLM_LOGICAL_MODEL", "private_sensitive_backup"
            ),
        )


@dataclass(frozen=True)
class OCRSettings:
    ocr_default_provider: str
    ocr_timeout_ms: int
    ocr_enable_layout: bool
    aliyun_ocr_base_url: str | None
    aliyun_ocr_api_key: str | None
    aliyun_ocr_app_code: str | None
    internal_ocr_base_url: str | None
    internal_ocr_api_key: str | None

    @classmethod
    def from_env(cls) -> "OCRSettings":
        return cls(
            ocr_default_provider=os.getenv("OCR_DEFAULT_PROVIDER", "aliyun_ocr"),
            ocr_timeout_ms=_get_int("OCR_TIMEOUT_MS", 60000),
            ocr_enable_layout=_get_bool("OCR_ENABLE_LAYOUT", False),
            aliyun_ocr_base_url=_get_optional("ALIYUN_OCR_BASE_URL"),
            aliyun_ocr_api_key=_get_optional("ALIYUN_OCR_API_KEY"),
            aliyun_ocr_app_code=_get_optional("ALIYUN_OCR_APP_CODE"),
            internal_ocr_base_url=_get_optional("INTERNAL_OCR_BASE_URL"),
            internal_ocr_api_key=_get_optional("INTERNAL_OCR_API_KEY"),
        )
