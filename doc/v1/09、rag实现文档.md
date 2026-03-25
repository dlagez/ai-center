# 09、RAG实现文档

## 1. 文档目标

本文档用于明确当前 `ai-center` 仓库在 V1 阶段如何实现一个最简单、可运行、可验证的 RAG 闭环，并回答以下问题：

- 当前仓库里哪些基础能力已经具备
- 最简单的 RAG 还缺哪些编排层能力
- 最小实现应放在哪一层、由哪些服务承担职责
- 文档入库链路如何从 `parse/chunk/embed` 走到向量库
- 问答链路如何从 `query/retrieve` 走到 LLM 生成
- V1 的范围边界、测试方式和验收标准是什么

本文档不讨论复杂的 Graph RAG、多路检索编排、重排序平台化治理，而是聚焦一个能在当前代码结构下快速落地的最小 RAG 实现。

---

## 2. 当前能力现状

结合当前仓库实现，RAG 所需的底层能力基本已经具备：

- 文档解析与抽取：`app/modules/document_center/`
- 文档切块：`app/runtime/retrieval/chunking/`
- 文档切块编排：`app/modules/knowledge_center/services/document_chunk_service.py`
- Embedding 网关：`app/runtime/embedding/gateway_service.py`
- 向量库抽象：`app/runtime/retrieval/vector_store/`
- 向量召回：`app/runtime/retrieval/gateway_service.py`
- LLM 网关：`app/runtime/llm/gateway_service.py`

当前真正缺失的不是基础能力，而是两层面向知识库场景的业务编排：

1. 索引构建编排服务  
负责把 chunk、embedding、vector store 串成一条入库链路。

2. RAG 问答编排服务  
负责把 retrieval 结果组织成 prompt，再调用 LLM 完成回答。

结论：V1 不需要新建一套新的 runtime 抽象层，直接在 `knowledge_center` 下补齐业务编排服务即可。

---

## 3. V1 最小 RAG 范围

### 3.1 本次必须支持

- 单知识库检索
- 单索引名：默认 `main`
- 单索引版本：默认 `v1`
- 纯向量召回
- 基于召回 chunk 的答案生成
- 返回引用信息（至少包含 `document_id`、`chunk_id`、`score`）
- 支持原始文本或文件入库

### 3.2 本次不做

- Hybrid Search
- Rerank
- Query Rewrite
- Multi-hop Agentic RAG
- 多知识库联合检索
- 对话记忆与长期会话存储
- 在线增量索引调度平台

---

## 4. 最小实现结论

V1 最简单 RAG 应拆成两条链路：

### 4.1 入库链路

```text
source(file/raw_text)
-> DocumentChunkService
-> EmbeddingGatewayService
-> VectorStoreService
-> collection/index_version 下的向量记录
```

### 4.2 问答链路

```text
user question
-> RetrieverService
-> top_k chunks
-> prompt context assembly
-> GatewayService.invoke_chat()
-> final answer + citations
```

### 4.3 模块落位结论

建议新增如下服务：

```text
app/modules/knowledge_center/services/
├── knowledge_index_service.py
└── simple_rag_service.py
```

这两个服务只做业务编排，不下沉重复抽象：

- `KnowledgeIndexService` 复用切块、embedding、向量入库能力
- `SimpleRAGService` 复用 retrieval 和 LLM 生成能力

---

## 5. 模块职责划分

### 5.1 DocumentChunkService

职责：

- 解析文档并切块
- 产出标准 `ChunkingResult`

不负责：

- 生成向量
- 写入向量库
- 生成答案

### 5.2 EmbeddingGatewayService

职责：

- 把文本转成向量
- 屏蔽不同 embedding provider 差异

不负责：

- 组织知识库 chunk 元数据
- 直接写入向量库

### 5.3 VectorStoreService

职责：

- 创建或校验 collection
- upsert/query/delete 向量记录
- 屏蔽底层向量库实现差异

不负责：

- 生成 query vector
- 决定最终召回策略
- 组装 LLM prompt

### 5.4 RetrieverService

职责：

- 把 query 转成 query vector
- 调用向量库进行召回
- 做 filter、top_k、阈值裁剪、去重

不负责：

- 构建最终问答 prompt
- 直接生成答案

### 5.5 GatewayService

职责：

- 统一 LLM 调用
- 处理模型路由和 fallback

不负责：

- 决定检索策略
- 决定引用格式

### 5.6 KnowledgeIndexService

职责：

- 串联 `chunk -> embed -> upsert`
- 管理 `knowledge_base_id/index_name/index_version`
- 管理文档级删除

### 5.7 SimpleRAGService

职责：

- 串联 `retrieve -> context assembly -> llm answer`
- 控制 prompt 模板
- 返回答案和引用

---

## 6. 目录设计

建议按如下方式落地：

```text
app/
└── modules/
    └── knowledge_center/
        ├── __init__.py
        └── services/
            ├── __init__.py
            ├── document_chunk_service.py
            ├── document_ocr_service.py
            ├── knowledge_index_service.py
            └── simple_rag_service.py
```

说明：

- 不建议再新增 `app/runtime/rag/`
- RAG 在当前阶段不是新的底层 runtime 能力，而是知识库场景的编排层
- runtime 已经有 `embedding / retrieval / llm / vector_store`，继续叠一层会产生重复边界

---

## 7. KnowledgeIndexService 设计

### 7.1 核心目标

给知识库提供最简单的“文档入库”能力，把原始文档稳定写入向量库。

### 7.2 依赖

- `build_document_chunk_service()`
- `build_embedding_gateway_service()`
- `build_default_vector_store_service()`

### 7.3 推荐接口

```python
class KnowledgeIndexService:
    def ingest_source(...)
    def ingest_raw_text(...)
    def delete_document(...)
```

### 7.4 ingest_source 标准流程

```text
1. 调用 DocumentChunkService.parse_and_chunk()
2. 取出 chunks
3. 调用 EmbeddingGatewayService.embed()
4. 以 chunk_id 对齐向量结果
5. 组装 VectorRecord 列表
6. 调用 VectorStoreService.upsert_records()
7. 返回 ingest result
```

### 7.5 ingest_raw_text 标准流程

```text
1. 直接构建 ChunkingRequest(raw_text)
2. 调用 chunking service 切块
3. 后续流程同 ingest_source
```

### 7.6 写入向量库的最小 metadata

每个 chunk 建议至少写入以下字段：

- `tenant_id`
- `app_id`
- `knowledge_base_id`
- `document_id`
- `chunk_id`
- `chunk_index`
- `title_path`
- `page_range`
- `source_block_ids`
- `source_positions`
- `file_name`
- `file_type`
- `scene`

其中：

- `tenant_id/app_id/knowledge_base_id/document_id` 用于过滤和隔离
- `chunk_index/title_path/page_range/source_positions` 用于引用定位
- `file_name/file_type` 用于展示和调试

### 7.7 delete_document 流程

```text
1. 接收 tenant/app/knowledge_base/index/document_id
2. 调用 VectorStoreService.delete_records(document_ids=[...])
3. 返回删除结果
```

---

## 8. SimpleRAGService 设计

### 8.1 核心目标

给知识库提供最简单的问答能力：基于召回结果回答问题，并返回引用。

### 8.2 依赖

- `build_default_retriever_service()`
- `build_gateway_service()`

### 8.3 推荐接口

```python
class SimpleRAGService:
    def answer(...)
```

### 8.4 标准流程

```text
1. 接收 user question
2. 调用 RetrieverService.retrieve()
3. 获取 top_k chunks
4. 将 chunks 组装为 context
5. 构造 system + user prompt
6. 调用 GatewayService.invoke_chat()
7. 返回 answer + citations + trace ids
```

### 8.5 retrieve 请求建议

- `top_k=5`
- `include_text=True`
- `include_metadata=True`
- `include_positions=True`
- `index_name="main"`
- `index_version="v1"`

### 8.6 context 组装规则

推荐把召回结果组织成如下结构：

```text
[1] document_id=doc-1 chunk_id=chunk-1 score=0.91
正文内容...

[2] document_id=doc-2 chunk_id=chunk-8 score=0.83
正文内容...
```

要求：

- 保留编号，方便引用
- 保留 `document_id/chunk_id`
- 保留原始 chunk 文本
- 必要时附带 `page_range` 或 `source_positions`

### 8.7 最小 prompt 原则

system prompt 建议：

```text
你是知识库问答助手。只能根据提供的参考资料回答问题。
如果参考资料不足以回答，就明确回答“根据现有资料无法确定”。
不要编造事实，不要引用未提供的内容。
```

user prompt 建议包含：

- 用户问题
- 检索到的参考资料
- 输出约束：先给结论，再给依据

### 8.8 无结果处理

当 `retrieval.hits` 为空时，有两种可选策略：

1. 直接返回固定兜底文本  
例如：`未检索到相关知识，无法根据知识库回答该问题。`

2. 仍然调用 LLM，但明确传入“无可用参考资料”  
让模型统一输出风格

V1 推荐策略 2，保持回答风格一致，但必须在 prompt 中强约束“无资料不能编造”。

---

## 9. 建议的数据结构

### 9.1 RAG 请求对象

```python
class RAGAskRequest(BaseModel):
    tenant_id: str
    app_id: str
    knowledge_base_id: str
    question: str
    user_id: str | None = None
    index_name: str = "main"
    index_version: str = "v1"
    top_k: int = 5
    score_threshold: float | None = None
    logical_model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### 9.2 RAG 返回对象

```python
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
```

说明：

- V1 可以先不把这套 schema 下沉到 runtime
- 直接放在 `knowledge_center` 作为业务层 schema 更合适

---

## 10. 最小实现伪代码

### 10.1 索引构建

```python
chunk_result = document_chunk_service.parse_and_chunk(...)

embedding_result = embedding_service.embed(
    EmbeddingBatchRequest(
        tenant_id=tenant_id,
        app_id=app_id,
        scene="knowledge_index",
        items=[
            EmbeddingInputItem(chunk_id=chunk.chunk_id, text=chunk.text)
            for chunk in chunk_result.chunks
        ],
    )
)

vector_store_service.upsert_records(
    VectorUpsertRequest(
        tenant_id=tenant_id,
        app_id=app_id,
        knowledge_base_id=knowledge_base_id,
        index_name="main",
        index_version="v1",
        records=[...],
    )
)
```

### 10.2 问答

```python
retrieval_result = retriever_service.retrieve(
    RetrievalRequest(
        tenant_id=tenant_id,
        app_id=app_id,
        knowledge_base_id=knowledge_base_id,
        query=question,
        top_k=5,
    )
)

llm_result = gateway_service.invoke_chat(
    LLMInvokeRequest(
        tenant_id=tenant_id,
        app_id=app_id,
        user_id=user_id,
        scene="knowledge_qa",
        task_type="chat",
        messages=[...],
        temperature=0.1,
    )
)
```

---

## 11. 配置建议

RAG 最小闭环依赖以下配置组：

- LLM 网关配置
- Embedding 配置
- Retrieval 配置
- Vector Store 配置

关键项包括：

```env
MODEL_GATEWAY_BASE_URL=
MODEL_GATEWAY_API_KEY=
PRIVATE_LLM_BASE_URL=
PRIVATE_LLM_API_KEY=
PRIVATE_LLM_MODEL=

EMBEDDING_DEFAULT_PUBLIC_MODEL=
PRIVATE_EMBEDDING_BASE_URL=
PRIVATE_EMBEDDING_API_KEY=
PRIVATE_EMBEDDING_MODEL=

RETRIEVAL_DEFAULT_TOP_K=5
RETRIEVAL_MAX_TOP_K=20
RETRIEVAL_TIMEOUT_MS=60000

VECTOR_STORE_PROVIDER=local_file
VECTOR_STORE_DEFAULT_METRIC=cosine
VECTOR_STORE_COLLECTION_PREFIX=kb_
VECTOR_STORE_LOCAL_DIR=data/vector_store
```

V1 默认可以直接使用：

- LLM：现有 `GatewayService`
- Embedding：现有 `EmbeddingGatewayService`
- Vector Store：现有 `local_file` provider

这意味着最简单 RAG 可以在本地直接跑通，不依赖外部专用向量数据库。

---

## 12. 错误处理原则

### 12.1 入库阶段

应重点处理：

- 文档解析失败
- chunk 为空
- embedding 失败
- 向量维度不匹配
- 向量写入失败

### 12.2 检索阶段

应重点处理：

- query 为空
- query embedding 失败
- vector query 失败
- score threshold 后无命中

### 12.3 生成阶段

应重点处理：

- LLM 超时
- 模型不可用
- 无法根据资料回答时的兜底语义

原则：

- 检索空结果不是系统异常，是业务正常分支
- 只有底层服务失败才应抛出异常

---

## 13. 测试建议

### 13.1 单元测试

应新增至少两组测试：

1. `KnowledgeIndexService`  
验证 `chunk -> embed -> upsert` 能串通，且 metadata 正确落库。

2. `SimpleRAGService`  
验证 `retrieve -> context assembly -> llm answer` 能串通，且返回 citations。

### 13.2 集成测试

建议增加一个最小 smoke case：

```text
一段原始文本入库
-> 用相关问题检索
-> LLM 基于召回片段回答
-> 返回答案与引用
```

### 13.3 回归测试

需要确保以下已有模块不被破坏：

- `chunking`
- `embedding gateway`
- `retriever`
- `llm gateway`
- `vector store`

---

## 14. 分阶段实施建议

### 14.1 第一阶段

- 新增 `knowledge_index_service.py`
- 新增 `simple_rag_service.py`
- 更新 `knowledge_center/services/__init__.py`
- 增加最小单测

### 14.2 第二阶段

- 增加文档删除与索引重建接口
- 增加引用格式标准化
- 增加回答长度与上下文截断策略

### 14.3 第三阶段

- 增加 rerank
- 增加 hybrid retrieval
- 增加多知识库路由
- 增加更细粒度的观测指标

---

## 15. 验收标准

### 15.1 功能验收

- 能把原始文本或文件切块后写入向量库
- 能基于用户问题召回相关 chunk
- 能将召回结果组装为 context 调用 LLM
- 能返回最终答案和引用信息

### 15.2 架构验收

- 不新增重复的 runtime 抽象层
- RAG 编排只发生在 `knowledge_center`
- `chunking / embedding / retrieval / llm / vector_store` 保持职责清晰

### 15.3 数据验收

- 每条入库记录都能回溯 `document_id/chunk_id`
- 每条召回结果都能回溯来源 metadata
- 每次问答都能回溯 retrieval 与 llm trace

---

## 16. 最终结论

当前仓库实现最简单 RAG 的正确方式不是再造一层新的底座，而是基于已有 runtime 能力补两层知识库编排：

- `KnowledgeIndexService` 负责入库
- `SimpleRAGService` 负责问答

最终主链路应为：

```text
文档/文本
-> parse_and_chunk
-> embedding
-> vector upsert
-> retrieval
-> prompt assembly
-> llm answer
```

这条链路的优点是：

- 复用现有模块最多
- 代码改动面最小
- 边界最清晰
- 最容易先跑通，再逐步演进到更复杂的 RAG 形态

---

## 17. Qdrant Local Mode 补充

当前实现补充支持 Qdrant SDK 本地模式，目的是让开发环境和最小 smoke 环境不再依赖单独启动 Qdrant 服务。

### 17.1 开发配置建议

```env
VECTOR_STORE_PROVIDER=qdrant
QDRANT_LOCAL_MODE=true
QDRANT_LOCAL_PATH=data/qdrant_local
```

在这个模式下：

- 应用仍然走统一的 `VectorStoreService`
- 适配器内部使用 `QdrantClient(path=...)`
- 数据会持久化到项目目录下的 `data/qdrant_local`

### 17.2 适用范围

推荐用于：

- 本地开发
- Demo 演示
- 端到端最小验证
- 单机 smoke 测试

不建议直接作为生产默认方案，生产环境仍建议：

```env
QDRANT_LOCAL_MODE=false
QDRANT_URL=http://<your-qdrant-host>:6333
QDRANT_API_KEY=
```

### 17.3 对 RAG 链路的影响

Qdrant Local Mode 不改变 RAG 主链路：

```text
parse_and_chunk -> embedding -> vector upsert -> retrieval -> llm answer
```

它只改变向量存储的运行方式：

- 开发环境：Qdrant SDK 本地模式
- 生产环境：外部 Qdrant Server / Cloud
