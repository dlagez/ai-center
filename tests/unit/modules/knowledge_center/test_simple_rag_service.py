from __future__ import annotations

import unittest

from app.modules.knowledge_center import RAGAskRequest
from app.modules.knowledge_center.services.simple_rag_service import SimpleRAGService
from app.runtime.llm.schemas import LLMInvokeResult
from app.runtime.retrieval.schemas import RetrievalHit, RetrievalResult


class FakeRetrieverService:
    def __init__(self, result: RetrievalResult) -> None:
        self._result = result
        self.requests: list[object] = []

    def retrieve(self, request: object) -> RetrievalResult:
        self.requests.append(request)
        return self._result


class FakeLLMService:
    def __init__(self, result: LLMInvokeResult) -> None:
        self._result = result
        self.requests: list[object] = []

    def invoke_chat(self, request: object) -> LLMInvokeResult:
        self.requests.append(request)
        return self._result


class SimpleRAGServiceTestCase(unittest.TestCase):
    def test_answer_builds_context_and_returns_citations(self) -> None:
        retriever = FakeRetrieverService(
            RetrievalResult(
                trace_id="retrieval-trace",
                query="什么是 alpha？",
                total_hits=1,
                hits=[
                    RetrievalHit(
                        chunk_id="chunk-1",
                        document_id="doc-1",
                        score=0.91,
                        text="alpha beta",
                        metadata={"page_range": [1]},
                        source_position={"page_no": 1},
                    )
                ],
                latency_ms=4,
                retrieval_strategy="vector_search",
                debug_info={},
            )
        )
        llm = FakeLLMService(
            LLMInvokeResult(
                trace_id="llm-trace",
                logical_model="chat_default",
                final_channel="litellm_proxy",
                final_provider="litellm_proxy",
                final_model="public-chat-default",
                content="alpha 是示例内容。",
                latency_ms=18,
            )
        )
        service = SimpleRAGService(retriever, llm_service=llm)

        result = service.answer(
            RAGAskRequest(
                tenant_id="tenant-a",
                app_id="app-a",
                knowledge_base_id="kb-a",
                question="什么是 alpha？",
            )
        )

        self.assertEqual(retriever.requests[0].scene, "knowledge_retrieval")
        self.assertEqual(llm.requests[0].scene, "knowledge_qa")
        self.assertIn("什么是 alpha？", llm.requests[0].messages[1]["content"])
        self.assertIn("document_id=doc-1", llm.requests[0].messages[1]["content"])
        self.assertIn("alpha beta", llm.requests[0].messages[1]["content"])
        self.assertEqual(result.answer, "alpha 是示例内容。")
        self.assertEqual(result.citations[0].chunk_id, "chunk-1")
        self.assertEqual(result.retrieval_trace_id, "retrieval-trace")
        self.assertEqual(result.llm_trace_id, "llm-trace")
        self.assertEqual(result.metadata["llm_final_model"], "public-chat-default")
        self.assertEqual(llm.requests[0].metadata["rag_trace_id"], result.trace_id)

    def test_answer_uses_empty_context_guard_when_no_hits(self) -> None:
        retriever = FakeRetrieverService(
            RetrievalResult(
                trace_id="retrieval-trace",
                query="没有答案的问题",
                total_hits=0,
                hits=[],
                latency_ms=2,
                retrieval_strategy="vector_search",
                debug_info={},
            )
        )
        llm = FakeLLMService(
            LLMInvokeResult(
                trace_id="llm-trace",
                logical_model="chat_default",
                final_channel="litellm_proxy",
                final_provider="litellm_proxy",
                final_model="public-chat-default",
                content="根据现有资料无法确定。",
                latency_ms=10,
            )
        )
        service = SimpleRAGService(retriever, llm_service=llm)

        result = service.answer(
            RAGAskRequest(
                tenant_id="tenant-a",
                app_id="app-a",
                knowledge_base_id="kb-a",
                question="没有答案的问题",
            )
        )

        self.assertEqual(result.citations, [])
        self.assertIn("无可用参考资料", llm.requests[0].messages[1]["content"])


if __name__ == "__main__":
    unittest.main()
