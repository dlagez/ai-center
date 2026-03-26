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


def _get_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return float(raw_value)


def _get_optional(name: str) -> str | None:
    raw_value = os.getenv(name)
    if raw_value is None:
        return None
    stripped = raw_value.strip()
    return stripped or None


def _get_optional_float(name: str) -> float | None:
    raw_value = _get_optional(name)
    if raw_value is None:
        return None
    return float(raw_value)


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


@dataclass(frozen=True)
class DocumentParseSettings:
    document_parse_cache_dir: str
    document_parse_enable_cache: bool
    document_parse_download_timeout_ms: int

    @classmethod
    def from_env(cls) -> "DocumentParseSettings":
        project_root = Path(__file__).resolve().parents[2]
        raw_cache_dir = os.getenv(
            "DOCUMENT_PARSE_CACHE_DIR",
            str(project_root / "data" / "document_parse_cache"),
        )
        cache_dir = Path(raw_cache_dir)
        if not cache_dir.is_absolute():
            cache_dir = project_root / cache_dir

        return cls(
            document_parse_cache_dir=str(cache_dir),
            document_parse_enable_cache=_get_bool("DOCUMENT_PARSE_ENABLE_CACHE", True),
            document_parse_download_timeout_ms=_get_int(
                "DOCUMENT_PARSE_DOWNLOAD_TIMEOUT_MS", 60000
            ),
        )


@dataclass(frozen=True)
class EmbeddingSettings:
    embedding_default_logical_model: str
    embedding_default_public_model: str
    embedding_timeout_ms: int
    embedding_batch_size: int
    embedding_enable_public_proxy: bool
    embedding_enable_direct_fallback: bool
    private_embedding_base_url: str | None
    private_embedding_api_key: str | None
    private_embedding_model: str | None
    private_embedding_logical_model: str

    @classmethod
    def from_env(cls) -> "EmbeddingSettings":
        return cls(
            embedding_default_logical_model=os.getenv(
                "EMBEDDING_DEFAULT_LOGICAL_MODEL", "embedding_default"
            ),
            embedding_default_public_model=os.getenv(
                "EMBEDDING_DEFAULT_PUBLIC_MODEL", "text-embedding-3-small"
            ),
            embedding_timeout_ms=_get_int("EMBEDDING_TIMEOUT_MS", 60000),
            embedding_batch_size=_get_int("EMBEDDING_BATCH_SIZE", 32),
            embedding_enable_public_proxy=_get_bool(
                "EMBEDDING_ENABLE_PUBLIC_PROXY", True
            ),
            embedding_enable_direct_fallback=_get_bool(
                "EMBEDDING_ENABLE_DIRECT_FALLBACK", True
            ),
            private_embedding_base_url=_get_optional("PRIVATE_EMBEDDING_BASE_URL"),
            private_embedding_api_key=_get_optional("PRIVATE_EMBEDDING_API_KEY"),
            private_embedding_model=_get_optional("PRIVATE_EMBEDDING_MODEL"),
            private_embedding_logical_model=os.getenv(
                "PRIVATE_EMBEDDING_LOGICAL_MODEL", "private_embedding_backup"
            ),
        )


@dataclass(frozen=True)
class ChunkingSettings:
    chunking_default_policy_name: str
    chunking_max_chars: int
    chunking_overlap_chars: int
    chunking_split_by_heading: bool
    chunking_split_by_paragraph: bool
    chunking_keep_heading_prefix: bool

    @classmethod
    def from_env(cls) -> "ChunkingSettings":
        return cls(
            chunking_default_policy_name=os.getenv(
                "CHUNKING_DEFAULT_POLICY_NAME", "default"
            ),
            chunking_max_chars=_get_int("CHUNKING_MAX_CHARS", 1200),
            chunking_overlap_chars=_get_int("CHUNKING_OVERLAP_CHARS", 150),
            chunking_split_by_heading=_get_bool("CHUNKING_SPLIT_BY_HEADING", True),
            chunking_split_by_paragraph=_get_bool(
                "CHUNKING_SPLIT_BY_PARAGRAPH", True
            ),
            chunking_keep_heading_prefix=_get_bool(
                "CHUNKING_KEEP_HEADING_PREFIX", True
            ),
        )


@dataclass(frozen=True)
class RetrievalSettings:
    retrieval_default_top_k: int
    retrieval_max_top_k: int
    retrieval_default_score_threshold: float | None
    retrieval_timeout_ms: int
    retrieval_enable_hybrid: bool
    retrieval_query_logical_model: str

    @classmethod
    def from_env(cls) -> "RetrievalSettings":
        default_query_logical_model = _get_optional("RETRIEVAL_QUERY_LOGICAL_MODEL")
        if default_query_logical_model is None:
            embedding_settings = EmbeddingSettings.from_env()
            if (
                not embedding_settings.embedding_enable_public_proxy
                and embedding_settings.private_embedding_model
                and embedding_settings.private_embedding_base_url
            ):
                default_query_logical_model = (
                    embedding_settings.private_embedding_logical_model
                )
            else:
                default_query_logical_model = "embedding_default"
        return cls(
            retrieval_default_top_k=_get_int("RETRIEVAL_DEFAULT_TOP_K", 10),
            retrieval_max_top_k=_get_int("RETRIEVAL_MAX_TOP_K", 50),
            retrieval_default_score_threshold=_get_optional_float(
                "RETRIEVAL_DEFAULT_SCORE_THRESHOLD"
            ),
            retrieval_timeout_ms=_get_int("RETRIEVAL_TIMEOUT_MS", 60000),
            retrieval_enable_hybrid=_get_bool("RETRIEVAL_ENABLE_HYBRID", False),
            retrieval_query_logical_model=default_query_logical_model,
        )


@dataclass(frozen=True)
class VectorStoreSettings:
    vector_store_provider: str
    vector_store_timeout_ms: int
    vector_store_default_metric: str
    vector_store_collection_prefix: str
    vector_store_local_dir: str
    qdrant_local_mode: bool = False
    qdrant_local_path: str | None = None
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    qdrant_grpc_port: int = 6334
    qdrant_prefer_grpc: bool = False
    qdrant_https: bool = False

    @classmethod
    def from_env(cls) -> "VectorStoreSettings":
        project_root = Path(__file__).resolve().parents[2]
        raw_local_dir = os.getenv(
            "VECTOR_STORE_LOCAL_DIR",
            str(project_root / "data" / "vector_store"),
        )
        local_dir = Path(raw_local_dir)
        if not local_dir.is_absolute():
            local_dir = project_root / local_dir

        raw_qdrant_local_path = os.getenv(
            "QDRANT_LOCAL_PATH",
            str(project_root / "data" / "qdrant_local"),
        )
        qdrant_local_path = Path(raw_qdrant_local_path)
        if not qdrant_local_path.is_absolute():
            qdrant_local_path = project_root / qdrant_local_path

        return cls(
            vector_store_provider=os.getenv("VECTOR_STORE_PROVIDER", "qdrant"),
            vector_store_timeout_ms=_get_int("VECTOR_STORE_TIMEOUT_MS", 60000),
            vector_store_default_metric=os.getenv(
                "VECTOR_STORE_DEFAULT_METRIC", "cosine"
            ),
            vector_store_collection_prefix=os.getenv(
                "VECTOR_STORE_COLLECTION_PREFIX", "kb_"
            ),
            vector_store_local_dir=str(local_dir),
            qdrant_local_mode=_get_bool("QDRANT_LOCAL_MODE", False),
            qdrant_local_path=str(qdrant_local_path),
            qdrant_url=_get_optional("QDRANT_URL") or "http://localhost:6333",
            qdrant_api_key=_get_optional("QDRANT_API_KEY"),
            qdrant_grpc_port=_get_int("QDRANT_GRPC_PORT", 6334),
            qdrant_prefer_grpc=_get_bool("QDRANT_PREFER_GRPC", False),
            qdrant_https=_get_bool("QDRANT_HTTPS", False),
        )
