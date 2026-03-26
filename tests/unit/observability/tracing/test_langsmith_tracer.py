from __future__ import annotations

import unittest
from contextlib import contextmanager

from app.core.config import LangSmithSettings
from app.observability.tracing import (
    LangSmithTracer,
    NullTraceRun,
    infer_pipeline_kind,
)
from app.observability.tracing.sanitizers import sanitize_messages, sanitize_value


class FakeClient:
    def __init__(self) -> None:
        self.flush_count = 0

    def flush(self) -> None:
        self.flush_count += 1


class FakeRun:
    def __init__(self, metadata: dict) -> None:
        self.metadata = dict(metadata)
        self.outputs: dict = {}

    def end(self, *, outputs=None, error=None) -> None:
        if outputs:
            self.outputs.update(outputs)
        if error is not None:
            self.metadata["error"] = str(error)


class FakeTraceFactory:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.runs: list[FakeRun] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)

        @contextmanager
        def manager():
            run = FakeRun(kwargs.get("metadata") or {})
            self.runs.append(run)
            yield run

        return manager()


class FakeTracingContextFactory:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)

        @contextmanager
        def manager():
            yield

        return manager()


class LangSmithTracerTestCase(unittest.TestCase):
    def test_trace_returns_null_run_when_disabled(self) -> None:
        tracer = LangSmithTracer(
            settings=LangSmithSettings(
                langsmith_tracing=False,
                langsmith_api_key=None,
                langsmith_endpoint="https://api.smith.langchain.com",
                langsmith_project="default",
                langsmith_workspace_id=None,
                app_langsmith_enabled=False,
                app_langsmith_project_rag="rag",
                app_langsmith_project_ingest="ingest",
                app_langsmith_project_eval="eval",
                app_langsmith_sample_rate=1.0,
                app_langsmith_max_text_chars=20,
                app_langsmith_capture_retrieved_text=True,
                app_langsmith_capture_prompts=True,
                app_langsmith_redact_pii=False,
                app_langsmith_otel_enabled=False,
                app_langsmith_otel_only=False,
            )
        )

        with tracer.trace(name="rag.answer", scene="knowledge_qa") as run:
            self.assertIsInstance(run, NullTraceRun)
            run.end(outputs={"ok": True})

        tracer.flush()

    def test_trace_routes_project_and_sanitizes_payloads(self) -> None:
        trace_factory = FakeTraceFactory()
        tracing_context_factory = FakeTracingContextFactory()
        client = FakeClient()
        tracer = LangSmithTracer(
            settings=LangSmithSettings(
                langsmith_tracing=True,
                langsmith_api_key="test-key",
                langsmith_endpoint="https://api.smith.langchain.com",
                langsmith_project="default-project",
                langsmith_workspace_id=None,
                app_langsmith_enabled=True,
                app_langsmith_project_rag="rag-project",
                app_langsmith_project_ingest="ingest-project",
                app_langsmith_project_eval="eval-project",
                app_langsmith_sample_rate=1.0,
                app_langsmith_max_text_chars=10,
                app_langsmith_capture_retrieved_text=True,
                app_langsmith_capture_prompts=True,
                app_langsmith_redact_pii=False,
                app_langsmith_otel_enabled=False,
                app_langsmith_otel_only=False,
            ),
            client=client,
            trace_factory=trace_factory,
            tracing_context_factory=tracing_context_factory,
        )

        with tracer.trace(
            name="rag.answer",
            scene="knowledge_qa",
            inputs={
                "question": "abcdefghijklmno",
                "api_key": "secret-value",
            },
            metadata={"rag_trace_id": "rag-1"},
        ) as run:
            run.end(outputs={"ok": True})

        self.assertEqual(trace_factory.calls[0]["project_name"], "rag-project")
        self.assertEqual(trace_factory.calls[0]["inputs"]["api_key"], "***")
        self.assertEqual(
            trace_factory.calls[0]["inputs"]["question"],
            "abcdefghij...<truncated:5>",
        )
        self.assertEqual(trace_factory.calls[0]["metadata"]["rag_trace_id"], "rag-1")
        self.assertEqual(tracing_context_factory.calls[0]["enabled"], True)
        self.assertIs(tracing_context_factory.calls[0]["client"], client)
        tracer.flush()
        self.assertEqual(client.flush_count, 1)

    def test_infer_pipeline_kind_from_metadata_and_scene(self) -> None:
        self.assertEqual(
            infer_pipeline_kind(
                metadata={"knowledge_index_trace_id": "idx-1"},
            ),
            "ingest",
        )
        self.assertEqual(
            infer_pipeline_kind(scene="knowledge_qa"),
            "rag",
        )
        self.assertEqual(
            infer_pipeline_kind(scene="other-scene"),
            "default",
        )

    def test_sanitizers_redact_and_control_message_content(self) -> None:
        sanitized = sanitize_value(
            {"api_key": "secret", "text": "hello@example.com 13800000000"},
            max_text_chars=100,
            redact_pii=True,
        )
        self.assertEqual(sanitized["api_key"], "***")
        self.assertEqual(sanitized["text"], "***@*** ***")

        messages = sanitize_messages(
            [{"role": "user", "content": "hidden"}],
            capture_content=False,
            max_text_chars=50,
            redact_pii=False,
        )
        self.assertEqual(messages, [{"role": "user"}])


if __name__ == "__main__":
    unittest.main()
