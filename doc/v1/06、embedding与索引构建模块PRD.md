# Embedding 与索引构建模块 PRD（V1）

## 1. 文档目的

本文档用于明确 AI 中台在 V1 阶段如何建设统一的“Embedding 与索引构建模块”，并回答以下问题：

- Embedding 与索引构建在当前架构中的定位
- Embedding、Chunking、文档解析、Retrieval 之间的职责边界
- Embedding 与索引构建能力应该落在哪些目录与模块
- 如何定义统一的 Embedding 输入输出、索引写入协议与元数据结构
- 知识库、Agent、工作流如何复用统一的 Embedding 与索引构建能力
- V1 的实现范围、验收标准和后续演进方向

本文档要解决的问题不是“要不要做向量化和索引”，而是“在当前项目架构下，如何把 Embedding 与索引构建做成统一、可治理、可扩展的基础能力，而不是散落在各业务流程中的临时实现”。

---

## 2. 背景

根据当前架构，知识库与检索层由以下关键能力组成：

- 文档解析
- Chunking
- Embedding
- 索引构建
- 检索
- RAG / Graph RAG

其中：

- 文档解析负责把原始文件还原为标准文本与结构化结果
- Chunking 负责把长文本切成适合索引与检索的语义片段
- Embedding 负责把片段映射为向量
- 索引构建负责把向量、文本、元数据写入检索基础设施
- Retrieval 负责按查询策略召回片段

如果不把 Embedding 与索引构建模块独立出来，后续通常会出现以下问题：

- 每个知识库入库流程自己调用一遍 Embedding
- 每个业务模块自己维护 chunk 到向量的转换逻辑
- 向量库写入、元数据写入、索引状态管理散落在业务代码里
- 更换 Embedding 模型或更换向量库时影响面过大
- 无法统一做批量化、失败重试、幂等写入、观察指标和成本统计

因此，V1 需要建立统一的 Embedding 与索引构建模块，作为知识库入库链路中的标准能力层。

---

## 3. V1 目标

### 3.1 产品目标

- 提供统一的 Embedding 内部调用入口
- 提供统一的索引构建入口
- 支持从标准 Chunk 列表生成向量
- 支持把文本、向量、元数据统一写入索引
- 支持知识库入库流程复用
- 支持后续接入不同 Embedding provider 与不同向量库
- 支持基础 trace、耗时、失败记录、批次信息与幂等写入控制

### 3.2 业务价值

- 为知识库入库提供统一中游能力
- 降低 Embedding 与索引逻辑在各业务模块中重复实现的成本
- 为向量模型切换、索引结构升级、混合检索扩展提供稳定边界
- 为后续索引重建、增量更新、批处理优化提供统一基础

---

## 4. V1 非目标

以下内容不属于本次 V1 必做范围：

- 不做完整的向量库管理后台 UI
- 不做多向量、多字段、多视图的复杂索引体系
- 不做复杂 ANN 参数自动调优
- 不做完整的召回评测平台
- 不做重排、Query Rewrite、Hybrid 检索策略编排
- 不做知识图谱索引
- 不做大规模离线任务调度平台
- 不做精细到财务级别的 Embedding 成本结算

说明：

V1 重点是先把“标准 chunk 输入 -> Embedding -> 索引写入 -> 可供检索使用”这一条主链路跑通。

---

## 5. 术语说明

### 5.1 Parsed Document

文档解析模块输出的标准化文档对象，供 Chunking 使用。

### 5.2 Chunk Document

Chunking 模块输出的标准切片结果，是 Embedding 与索引构建模块的直接输入。

### 5.3 Embedding

把文本片段映射为固定维度向量的过程或能力。

### 5.4 Embedding Provider

具体提供向量能力的模型供应方或模型服务，例如：

- OpenAI Embedding
- 通义 / DashScope Embedding
- 本地 Embedding 模型
- vLLM 或私有模型服务

### 5.5 Index Build

把 chunk 文本、向量、元数据组织并写入检索基础设施的过程。

### 5.6 Index Record

索引中的标准写入单元，通常包含：

- chunk_id
- text
- vector
- metadata

### 5.7 Vector Store

保存向量并支持近似向量检索的存储系统。

### 5.8 Document Store / Metadata Store

保存原始文本、标题、来源、位置、权限等非向量信息的存储层。

---

## 6. 方案结论

V1 采用以下统一方案：

1. Embedding 与索引构建作为知识库与检索层中的独立基础能力落地
2. 上层知识库与 Agent 不直接调用具体 Embedding SDK 或向量库 SDK
3. Embedding 只负责“文本到向量”的统一转换
4. 索引构建负责“chunk + vector + metadata 到 index record”的标准写入
5. Chunking 输出标准 chunk，Embedding 与索引构建模块只消费标准 chunk
6. 向量模型切换与索引后端切换，通过 adapter 与配置完成，而不是修改业务主流程

换句话说：

- 文档解析模块负责“把文件转成可消费文档结构”
- Chunking 模块负责“把文档结构转成可索引片段”
- Embedding 模块负责“把片段转成向量”
- 索引构建模块负责“把片段与向量写成检索可用索引”
- Retrieval 模块负责“基于索引做召回”

---

## 7. 与其他模块的职责边界

### 7.1 与文档解析模块

文档解析负责：

- 文件解析
- 文本提取
- 结构还原
- 原文位置保留

Embedding 与索引构建不负责：

- OCR
- 文件格式解析
- 文档结构清洗

关系是：

```text
文档解析 -> Chunking -> Embedding -> 索引构建
```

### 7.2 与 Chunking 模块

Chunking 负责：

- 生成标准 chunk
- 保留来源位置与上下文信息

Embedding 与索引构建负责：

- 消费 chunk
- 生成向量
- 写入索引

Embedding 与索引构建不负责：

- 决定 chunk 大小
- 自己重做切分策略

### 7.3 与 Retrieval / RAG 模块

Retrieval 负责：

- 检索 query 理解
- 向量召回
- 混合检索
- 排序和后续组装

Embedding 与索引构建负责：

- 建索引
- 更新索引
- 保证 chunk 到 index record 的映射稳定

### 7.4 与模型管理 / 模型路由模块

模型管理与路由负责：

- Embedding 模型配置
- provider 路由
- fallback 策略
- 配额与治理

Embedding 与索引构建模块不负责：

- 自己维护 provider 路由规则
- 绕过统一模型治理直接绑定某个模型服务

---

## 8. 用户与使用场景

### 8.1 知识库场景

- 作为知识库模块，我希望文档切分后统一进入 Embedding 与索引构建流程
- 我希望不同文档来源都走同一套向量化与写入逻辑
- 我希望未来切换 Embedding 模型时不用修改入库主流程

### 8.2 Agent 场景

- 作为 Agent，我希望在需要临时构建小型语义索引时，可以复用统一 Embedding 能力
- 我希望 Agent 不直接维护一套独立的向量化与索引写入逻辑

### 8.3 平台治理场景

- 作为平台，我希望记录每次 Embedding 的 provider、模型、耗时、批次大小、失败情况
- 我希望记录每次索引写入的目标 index、写入数量、成功数量与失败数量
- 我希望未来能够做索引重建、增量更新和批量修复

---

## 9. 范围定义

### 9.1 V1 必做范围

- 统一 Embedding 请求与响应协议
- 统一索引构建请求与响应协议
- 支持从标准 chunk 列表批量生成向量
- 支持标准 index record 写入
- 支持基础幂等写入
- 支持知识库入库流程复用
- 支持基础 trace 与观察指标

### 9.2 V1 预留但不强制实现

- 多 Embedding 模型并行写入
- 多向量字段索引
- Hybrid 检索中的稀疏索引协同写入
- 自动索引分片
- 向量归一化策略自适应优化
- 增量重算调度平台
- 成本核算报表

---

## 10. 推荐目录落位

建议后续按以下目录落位：

```text
app/
├── runtime/
│   ├── embedding/
│   │   ├── schemas.py
│   │   ├── base.py
│   │   ├── provider_router.py
│   │   ├── gateway_service.py
│   │   └── batch_service.py
│   └── retrieval/
│       ├── indexing/
│       │   ├── schemas.py
│       │   ├── base.py
│       │   ├── vector_store_adapter.py
│       │   ├── document_store_adapter.py
│       │   ├── index_builder.py
│       │   └── service.py
├── integrations/
│   ├── embedding_providers/
│   │   ├── base.py
│   │   ├── openai_embedding_adapter.py
│   │   ├── dashscope_embedding_adapter.py
│   │   └── local_embedding_adapter.py
│   └── vector_stores/
│       ├── base.py
│       ├── milvus_adapter.py
│       ├── pgvector_adapter.py
│       └── elasticsearch_adapter.py
└── modules/
    └── knowledge_center/
        └── services/
            ├── ingestion_service.py
            ├── embedding_service.py
            └── index_build_service.py
```

说明：

- `runtime/embedding/` 负责统一 Embedding 抽象与执行
- `runtime/retrieval/indexing/` 负责统一索引构建与写入
- `integrations/embedding_providers/` 负责对接具体 Embedding provider
- `integrations/vector_stores/` 负责对接具体向量库或索引后端
- `knowledge_center` 只负责调用和编排，不直接实现 Embedding 与索引逻辑

---

## 11. 核心功能需求

### 11.1 统一 Embedding 入口

系统必须提供统一的 Embedding 调用接口，例如：

```python
embed_chunks(request: EmbeddingBatchRequest) -> EmbeddingBatchResult
```

或：

```python
embedding_service.embed(request)
```

该入口对上层屏蔽以下差异：

- provider 协议差异
- 模型名称差异
- 认证方式差异
- 批处理能力差异
- 返回向量结构差异

### 11.2 统一索引构建入口

系统必须提供统一的索引写入接口，例如：

```python
build_index(request: IndexBuildRequest) -> IndexBuildResult
```

或：

```python
index_builder.upsert(request)
```

### 11.3 Embedding 输入要求

Embedding 模块的标准输入应来自 Chunking 输出的标准 chunk 列表，至少包含：

- chunk_id
- text
- source document id
- 来源位置元数据
- chunk metadata

### 11.4 Embedding 输出要求

Embedding 输出至少包含：

- chunk_id
- vector
- vector dimension
- provider
- model
- usage 或统计信息

### 11.5 索引写入要求

索引构建模块必须支持将以下内容统一写入索引：

- chunk_id
- document_id
- text
- vector
- metadata
- 来源位置

### 11.6 幂等写入

同一个 chunk 反复入库时，系统需要支持稳定的 upsert 语义，而不是盲目重复写入。

最小要求：

- 以 `index_id + chunk_id` 作为幂等键
- 重复写入相同 chunk 时进行覆盖或跳过，而不是新增重复记录

### 11.7 批处理能力

Embedding 与索引构建应支持批处理：

- 批量向量化
- 批量写入
- 批次级错误记录

### 11.8 索引版本与重建能力

V1 至少应预留以下字段：

- index_name
- index_version
- embedding_model
- embedding_dimension
- chunk_policy_version

为后续索引重建提供基础。

---

## 12. 数据模型建议

### 12.1 Embedding 请求对象

```python
class EmbeddingBatchRequest(BaseModel):
    tenant_id: str
    app_id: str
    scene: str
    logical_model: str
    chunks: list[ChunkDocument]
    metadata: dict = Field(default_factory=dict)
```

### 12.2 Embedding 结果对象

```python
class EmbeddedChunk(BaseModel):
    chunk_id: str
    vector: list[float]
    dimension: int
    text: str
    metadata: dict = Field(default_factory=dict)


class EmbeddingBatchResult(BaseModel):
    trace_id: str
    provider: str
    model: str
    dimension: int
    items: list[EmbeddedChunk]
    latency_ms: int
    usage: dict = Field(default_factory=dict)
```

### 12.3 索引写入请求对象

```python
class IndexBuildRequest(BaseModel):
    tenant_id: str
    app_id: str
    knowledge_base_id: str
    index_name: str
    index_version: str
    chunks: list[EmbeddedChunk]
    metadata: dict = Field(default_factory=dict)
```

### 12.4 索引写入结果对象

```python
class IndexBuildResult(BaseModel):
    trace_id: str
    index_name: str
    index_version: str
    total_count: int
    success_count: int
    failed_count: int
    latency_ms: int
    errors: list[dict] = Field(default_factory=list)
```

### 12.5 标准 Index Record

```python
class IndexRecord(BaseModel):
    index_name: str
    chunk_id: str
    document_id: str
    text: str
    vector: list[float]
    metadata: dict = Field(default_factory=dict)
```

---

## 13. 标准执行流程

### 13.1 知识库入库主流程

```text
文件上传
-> 文档解析
-> Chunking
-> Embedding
-> 索引构建
-> 入库完成
```

### 13.2 Embedding 流程

```text
接收标准 chunk 列表
-> 选择 embedding provider / model
-> 批量调用 embedding
-> 标准化返回向量结果
-> 返回 EmbeddedChunk 列表
```

### 13.3 索引构建流程

```text
接收 EmbeddedChunk 列表
-> 组装 index record
-> 写入 vector store / metadata store
-> 返回写入结果
```

### 13.4 重复入库流程

```text
接收重复 chunk
-> 根据 chunk_id + index_name 判定是否已存在
-> 若存在则覆盖或跳过
-> 保证索引状态一致
```

---

## 14. 模块职责设计

### 14.1 runtime/embedding

职责：

- 统一 Embedding 协议
- 统一模型调用
- 标准化返回结果
- 支持批处理

非职责：

- 不负责 chunk 切分
- 不负责索引写入
- 不直接承载向量库存储逻辑

### 14.2 runtime/retrieval/indexing

职责：

- 定义索引写入协议
- 组装标准 index record
- 执行 upsert / delete / rebuild
- 管理索引版本元数据

非职责：

- 不负责 embedding 模型调用
- 不负责 query 检索
- 不负责 rerank

### 14.3 integrations/embedding_providers

职责：

- 对接具体 Embedding provider
- 封装 provider 协议与认证差异
- 映射统一输入输出

### 14.4 integrations/vector_stores

职责：

- 对接具体向量库
- 封装 upsert / delete / query 等基础接口
- 对接 metadata store 或支持混合存储

---

## 15. 配置设计

### 15.1 Embedding 相关配置建议

建议至少补充：

```env
# Embedding runtime
EMBEDDING_DEFAULT_LOGICAL_MODEL=embedding_default
EMBEDDING_TIMEOUT_MS=60000
EMBEDDING_BATCH_SIZE=32

# Vector store
VECTOR_STORE_PROVIDER=pgvector
VECTOR_STORE_INDEX_PREFIX=kb_
VECTOR_STORE_TIMEOUT_MS=60000
```

### 15.2 配置原则

- Embedding 逻辑模型通过模型治理层统一配置
- 上层业务不直接保存 provider 凭据
- 向量库连接信息统一由配置层管理
- 索引名称和版本由索引构建模块统一管理

---

## 16. 观察与审计

每次 Embedding 调用至少记录：

- trace_id
- tenant_id
- app_id
- scene
- logical_model
- provider
- model
- batch_size
- dimension
- latency_ms
- status
- error_code

每次索引写入至少记录：

- trace_id
- index_name
- index_version
- total_count
- success_count
- failed_count
- latency_ms
- status
- error_code

建议重点关注以下指标：

- Embedding 总请求量
- 平均批次大小
- 单次向量化耗时
- 向量维度分布
- 索引写入耗时
- upsert 成功率
- 失败重试次数

---

## 17. 风险与约束

### 17.1 风险

- 如果 Embedding 与索引写入散落在业务层，后续难以统一治理
- 如果 chunk_id 设计不稳定，会导致索引重复写入或覆盖错误
- 如果不记录 embedding model 与 chunk policy version，后续索引重建难以回溯
- 如果直接绑定某个向量库 SDK，更换底层存储成本会很高

### 17.2 约束

- V1 必须优先保证模块边界清晰
- V1 必须先建立标准输入输出协议
- V1 必须保证知识库入库链路可复用
- V1 不应在业务模块中硬编码 Embedding provider 细节

---

## 18. 分阶段落地建议

### 18.1 第一阶段

- 定义 Embedding 请求/响应协议
- 定义 Index Build 请求/响应协议
- 实现 1 个 Embedding provider adapter
- 实现 1 个向量库 adapter
- 打通知识库入库链路

### 18.2 第二阶段

- 支持批量化 Embedding
- 支持幂等 upsert
- 增加索引版本管理
- 增加基础重试与失败记录

### 18.3 第三阶段

- 增加多 provider 支持
- 增加多索引后端支持
- 增加索引重建与增量更新机制
- 支持混合检索相关索引协同写入

---

## 19. 验收标准

### 19.1 功能验收

- 标准 chunk 列表可以统一进入 Embedding 模块
- Embedding 结果可以统一进入索引构建模块
- 索引构建完成后可供后续 Retrieval 使用
- 相同 chunk 重复写入时不会产生不可控重复记录
- 知识库入库流程可复用统一 Embedding 与索引构建能力

### 19.2 架构验收

- 上层业务不直接依赖具体 Embedding SDK
- 上层业务不直接依赖具体向量库 SDK
- Embedding 与索引构建职责分离
- Chunking、Embedding、索引构建、Retrieval 边界清晰

### 19.3 数据验收

- 每次 Embedding 均有 trace_id
- 每次索引写入均有 trace_id
- 可回溯 provider、model、dimension、index_version
- 可从 index record 回溯到来源 chunk_id 与 document_id

---

## 20. 最终结论摘要

Embedding 与索引构建不应散落在知识库或 Agent 的业务流程中，而应作为知识库与检索层中的独立标准能力实现。

正确的链路应该是：

```text
文档解析 -> Chunking -> Embedding -> 索引构建 -> Retrieval / RAG
```

这意味着：

- 文档解析负责还原文档内容
- Chunking 负责生成标准 chunk
- Embedding 负责把 chunk 转成向量
- 索引构建负责把 chunk 与向量写成可检索索引
- Retrieval 负责基于索引做召回

这样做的结果是：

- 架构边界更清晰
- 业务模块更轻
- 向量模型和索引后端更容易切换
- 后续检索优化、索引升级和重建更容易治理

