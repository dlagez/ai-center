from __future__ import annotations

import uuid
from typing import Any

from app.modules.knowledge_center.schemas import (
    RAGAskRequest,
    RAGAskResult,
    RAGCitation,
)
from app.runtime.llm.gateway_service import GatewayService, build_gateway_service
from app.runtime.llm.schemas import LLMInvokeRequest
from app.runtime.retrieval import (
    RetrievalHit,
    RetrievalRequest,
    RetrieverService,
    build_default_retriever_service,
)

_RETRIEVAL_SCENE = "knowledge_retrieval"
_DEFAULT_SYSTEM_PROMPT = (
    "你是知识库问答助手。只能根据提供的参考资料回答问题。"
    "如果参考资料不足以回答，就明确回答“根据现有资料无法确定”。"
    "不要编造事实，不要引用未提供的内容。"
)
_EMPTY_CONTEXT = "无可用参考资料。请直接回答：根据现有资料无法确定。"


class SimpleRAGService:
    def __init__(
        self,
        retriever_service: RetrieverService,
        *,
        llm_service: GatewayService | None = None,
    ) -> None:
        self._retriever_service = retriever_service
        self._llm_service = llm_service or build_gateway_service()

    def answer(self, request: RAGAskRequest) -> RAGAskResult:
        trace_id = uuid.uuid4().hex
        retrieval_result = self._retriever_service.retrieve(
            RetrievalRequest(
                tenant_id=request.tenant_id,
                app_id=request.app_id,
                knowledge_base_id=request.knowledge_base_id,
                index_name=request.index_name,
                index_version=request.index_version,
                scene=_RETRIEVAL_SCENE,
                query=request.question,
                top_k=request.top_k,
                score_threshold=request.score_threshold,
                document_ids=list(request.document_ids),
                filters=dict(request.filters),
                include_text=True,
                include_metadata=True,
                include_positions=True,
                query_logical_model=request.query_logical_model,
                timeout_ms=request.timeout_ms,
                metadata={
                    **request.metadata,
                    "rag_trace_id": trace_id,
                },
            )
        )

        citations = self._build_citations(retrieval_result.hits)
        llm_result = self._llm_service.invoke_chat(
            LLMInvokeRequest(
                tenant_id=request.tenant_id,
                app_id=request.app_id,
                user_id=request.user_id,
                scene=request.scene,
                task_type="chat",
                logical_model=request.logical_model,
                capability_tags=list(request.capability_tags),
                messages=self._build_messages(
                    question=request.question,
                    hits=retrieval_result.hits,
                    system_prompt=request.system_prompt,
                ),
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                timeout_ms=request.timeout_ms,
                metadata={
                    **request.metadata,
                    "rag_trace_id": trace_id,
                    "retrieval_trace_id": retrieval_result.trace_id,
                    "citation_count": len(citations),
                },
            )
        )

        return RAGAskResult(
            trace_id=trace_id,
            question=request.question,
            answer=llm_result.content or "",
            citations=citations,
            retrieval_trace_id=retrieval_result.trace_id,
            llm_trace_id=llm_result.trace_id,
            metadata={
                **request.metadata,
                "retrieval_total_hits": retrieval_result.total_hits,
                "llm_final_channel": llm_result.final_channel,
                "llm_final_provider": llm_result.final_provider,
                "llm_final_model": llm_result.final_model,
                "llm_latency_ms": llm_result.latency_ms,
            },
        )

    @staticmethod
    def _build_citations(hits: list[RetrievalHit]) -> list[RAGCitation]:
        return [
            RAGCitation(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                score=hit.score,
                text=hit.text,
                metadata=dict(hit.metadata),
                source_position=dict(hit.source_position),
            )
            for hit in hits
        ]

    def _build_messages(
        self,
        *,
        question: str,
        hits: list[RetrievalHit],
        system_prompt: str | None,
    ) -> list[dict[str, Any]]:
        return [
            {
                "role": "system",
                "content": system_prompt or _DEFAULT_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    f"用户问题：{question}\n\n"
                    f"参考资料：\n{self._build_context(hits)}\n\n"
                    "回答要求：\n"
                    "1. 只能根据参考资料回答。\n"
                    "2. 如果资料不足，明确回答“根据现有资料无法确定”。\n"
                    "3. 先给结论，再给依据。"
                ),
            },
        ]

    @staticmethod
    def _build_context(hits: list[RetrievalHit]) -> str:
        if not hits:
            return _EMPTY_CONTEXT

        blocks: list[str] = []
        for index, hit in enumerate(hits, start=1):
            lines = [
                f"[{index}] document_id={hit.document_id} chunk_id={hit.chunk_id} score={hit.score:.4f}"
            ]
            if hit.source_position:
                lines.append(f"source_position={hit.source_position}")
            lines.append(hit.text or "")
            blocks.append("\n".join(lines).strip())
        return "\n\n".join(blocks)


def build_simple_rag_service(
    *,
    retriever_service: RetrieverService | None = None,
    llm_service: GatewayService | None = None,
) -> SimpleRAGService:
    return SimpleRAGService(
        retriever_service or build_default_retriever_service(),
        llm_service=llm_service,
    )
