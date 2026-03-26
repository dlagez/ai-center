from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import langsmith
from langsmith import Client
from langsmith.run_helpers import get_current_run_tree, tracing_context

from app.core.config import LangSmithSettings
from app.observability.tracing.context import detect_runtime_environment
from app.observability.tracing.project_router import (
    infer_pipeline_kind,
    resolve_project_name,
)
from app.observability.tracing.sanitizers import sanitize_value, truncate_text


@dataclass
class NullTraceRun:
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    outputs: dict[str, Any] = field(default_factory=dict)
    id: str | None = None
    trace_id: str | None = None

    def end(
        self,
        *,
        outputs: dict[str, Any] | None = None,
        error: Any | None = None,
    ) -> None:
        if outputs:
            self.outputs.update(outputs)
        if error is not None:
            self.metadata["error"] = str(error)


class LangSmithTracer:
    def __init__(
        self,
        *,
        settings: LangSmithSettings | None = None,
        client: Client | None = None,
        trace_factory: Callable[..., Any] | None = None,
        tracing_context_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._settings = settings or LangSmithSettings.from_env()
        self._enabled = bool(
            self._settings.app_langsmith_enabled
            and self._settings.langsmith_tracing
            and self._settings.langsmith_api_key
        )
        self._client = client or self._build_client()
        self._trace_factory = trace_factory or langsmith.trace
        self._tracing_context_factory = tracing_context_factory or tracing_context

    @property
    def settings(self) -> LangSmithSettings:
        return self._settings

    @property
    def enabled(self) -> bool:
        return self._enabled and self._client is not None

    def capture_prompts(self) -> bool:
        return self._settings.app_langsmith_capture_prompts

    def capture_retrieved_text(self) -> bool:
        return self._settings.app_langsmith_capture_retrieved_text

    def preview_text(self, text: str | None, *, allow_capture: bool) -> str | None:
        if not allow_capture:
            return None
        return truncate_text(text, self._settings.app_langsmith_max_text_chars)

    def sanitize(self, value: Any) -> Any:
        return sanitize_value(
            value,
            max_text_chars=self._settings.app_langsmith_max_text_chars,
            redact_pii=self._settings.app_langsmith_redact_pii,
        )

    def current_run(self) -> Any | None:
        return get_current_run_tree()

    def flush(self) -> None:
        if self._client is not None:
            self._client.flush()

    @contextmanager
    def trace(
        self,
        *,
        name: str,
        run_type: str = "chain",
        inputs: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
        tags: list[str] | None = None,
        project_name: str | None = None,
        pipeline_kind: str | None = None,
        scene: str | None = None,
        reference_example_id: str | None = None,
    ) -> Iterator[Any]:
        sanitized_inputs = self.sanitize(dict(inputs or {}))
        sanitized_metadata = self.sanitize(dict(metadata or {}))
        inferred_pipeline = pipeline_kind or infer_pipeline_kind(
            scene=scene,
            metadata=dict(metadata or {}),
        )
        resolved_project = project_name or resolve_project_name(
            self._settings,
            pipeline_kind=inferred_pipeline,
        )
        resolved_tags = self._build_tags(
            pipeline_kind=inferred_pipeline,
            scene=scene,
            tags=tags,
        )

        if not self.enabled:
            null_run = NullTraceRun(
                metadata=dict(sanitized_metadata),
                tags=list(resolved_tags),
            )
            yield null_run
            return

        with self._tracing_context_factory(enabled=True, client=self._client):
            with self._trace_factory(
                name=name,
                run_type=run_type,
                inputs=dict(sanitized_inputs),
                project_name=resolved_project,
                tags=resolved_tags,
                metadata=dict(sanitized_metadata),
                client=self._client,
                reference_example_id=reference_example_id,
            ) as run:
                yield run

    def _build_client(self) -> Client | None:
        if not self._enabled:
            return None
        return Client(
            api_url=self._settings.langsmith_endpoint,
            api_key=self._settings.langsmith_api_key,
            workspace_id=self._settings.langsmith_workspace_id,
            tracing_sampling_rate=self._settings.app_langsmith_sample_rate,
            otel_enabled=self._settings.app_langsmith_otel_enabled,
        )

    @staticmethod
    def _build_tags(
        *,
        pipeline_kind: str,
        scene: str | None,
        tags: list[str] | None,
    ) -> list[str]:
        resolved_tags = set(tags or [])
        resolved_tags.add(f"env:{detect_runtime_environment()}")
        if pipeline_kind and pipeline_kind != "default":
            resolved_tags.add(f"pipeline:{pipeline_kind}")
        if scene:
            resolved_tags.add(f"scene:{scene}")
        return sorted(resolved_tags)


@lru_cache(maxsize=1)
def get_default_langsmith_tracer() -> LangSmithTracer:
    return LangSmithTracer()
