from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.runtime.retrieval.chunking import ChunkingPolicyConfig


class KnowledgeIndexSourceRequest(BaseModel):
    tenant_id: str
    app_id: str
    knowledge_base_id: str
    source_type: str
    source_value: str
    document_id: str | None = None
    scene: str = "knowledge_ingest"
    index_name: str = "main"
    index_version: str = "v1"
    file_name: str | None = None
    file_type: str | None = None
    provider: str | None = None
    policy: ChunkingPolicyConfig | None = None
    logical_model: str | None = None
    timeout_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeIndexTextRequest(BaseModel):
    tenant_id: str
    app_id: str
    knowledge_base_id: str
    document_id: str
    raw_text: str
    scene: str = "knowledge_ingest"
    index_name: str = "main"
    index_version: str = "v1"
    file_name: str | None = None
    file_type: str | None = None
    policy: ChunkingPolicyConfig | None = None
    logical_model: str | None = None
    timeout_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_raw_text(self) -> "KnowledgeIndexTextRequest":
        if not self.raw_text.strip():
            raise ValueError("Knowledge index raw_text must not be empty.")
        return self


class KnowledgeIndexResult(BaseModel):
    trace_id: str
    document_id: str
    knowledge_base_id: str
    index_name: str
    index_version: str
    collection_name: str
    source_type: str | None = None
    file_name: str | None = None
    file_type: str | None = None
    total_chunks: int
    embedded_count: int
    success_count: int
    failed_count: int
    chunking_trace_id: str
    embedding_trace_id: str
    vector_store_trace_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeDeleteRequest(BaseModel):
    tenant_id: str
    app_id: str
    knowledge_base_id: str
    document_id: str
    index_name: str = "main"
    index_version: str = "v1"
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeDeleteResult(BaseModel):
    trace_id: str
    document_id: str
    knowledge_base_id: str
    index_name: str
    index_version: str
    collection_name: str
    deleted_count: int
    vector_store_trace_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RAGAskRequest(BaseModel):
    tenant_id: str
    app_id: str
    knowledge_base_id: str
    question: str
    user_id: str | None = None
    scene: str = "knowledge_qa"
    index_name: str = "main"
    index_version: str = "v1"
    top_k: int = 5
    score_threshold: float | None = None
    document_ids: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    query_logical_model: str | None = None
    logical_model: str | None = None
    capability_tags: list[str] = Field(default_factory=list)
    temperature: float | None = 0.1
    max_tokens: int | None = None
    timeout_ms: int | None = None
    system_prompt: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_question(self) -> "RAGAskRequest":
        self.question = self.question.strip()
        if not self.question:
            raise ValueError("RAG question must not be empty.")
        return self


class RAGCitation(BaseModel):
    chunk_id: str
    document_id: str
    score: float
    text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_position: dict[str, Any] = Field(default_factory=dict)


class RAGAskResult(BaseModel):
    trace_id: str
    question: str
    answer: str
    citations: list[RAGCitation] = Field(default_factory=list)
    retrieval_trace_id: str | None = None
    llm_trace_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
