# Retriever 模块 PRD（V1）
## 1. 文档目的

本文档用于明确 AI 中台在 V1 阶段如何建设统一的“Retriever 模块”，并回答以下问题：

- Retriever 模块在当前架构中的定位
- Retriever 与 Embedding、索引构建、向量库接入、Rerank、RAG 之间的职责边界
- Retriever 能力应落在哪些目录与模块
- 如何定义统一的检索请求、召回结果、过滤条件与检索策略协议
- 知识库、Agent、工作流如何复用统一的 Retriever 能力
- V1 的实现范围、验收标准和后续演进方向

本文档要解决的问题不是“要不要做检索”，而是“在当前项目架构下，如何把检索做成统一、可治理、可扩展的标准能力，而不是散落在知识库、Agent、业务接口中的临时查询逻辑”。

---

## 2. 背景

根据当前架构，知识库与检索层由以下关键能力组成：

- 文档解析
- Chunking
- Embedding
- 索引构建
- 向量库接入
- Retriever
- Rerank
- RAG / Graph RAG

其中：

- 文档解析负责把文件转换成标准化文档结构
- Chunking 负责把文档切成可索引、可回溯的语义片段
- Embedding 负责把 query 或 chunk 转成向量
- 索引构建负责把 chunk、向量与元数据组织成标准索引记录
- 向量库接入负责把标准索引记录写入后端并提供统一查询协议
- Retriever 负责面向查询场景组织召回流程、过滤规则、候选集融合和统一结果输出
- Rerank 负责对召回候选进一步排序
- RAG 负责消费检索结果组装上下文并进入生成阶段

如果不把 Retriever 独立出来，后续通常会出现以下问题：

- 知识库接口自己写一套相似度查询逻辑
- Agent 节点自己写一套临时检索逻辑
- 不同业务各自定义 top_k、score 阈值、过滤条件与去重规则
- 向量检索、关键词检索、混合检索的融合逻辑散落在多个模块里
- 上层模块直接感知向量库后端返回格式，后续替换成本高
- 无法统一记录查询 trace、召回质量、过滤命中率和延迟指标

因此，V1 需要建立统一的 Retriever 模块，作为“查询意图到标准候选结果”的核心运行时能力层。

---

## 3. V1 目标

### 3.1 产品目标

- 提供统一的检索请求入口
- 支持基于 query text 的标准召回流程
- 支持向量检索能力复用
- 预留关键词检索与混合检索扩展位
- 支持过滤条件、租户隔离、应用隔离和知识库隔离
- 支持去重、截断、基础融合与统一结果标准化
- 支持 RAG、Agent、工作流复用统一 Retriever 能力
- 支持基础 trace、召回统计、失败记录和调试信息输出

### 3.2 业务价值

- 降低检索逻辑在各业务模块中的重复实现成本
- 为 RAG、问答、文档问询、Agent 工具检索提供统一中间层
- 为后续引入混合检索、重排、查询改写、多路召回提供稳定边界
- 为检索评测、效果优化、召回参数治理提供统一抓手

---

## 4. V1 非目标

以下内容不属于本次 V1 必做范围：

- 不做完整的检索策略管理后台 UI
- 不做复杂的在线学习型检索路由
- 不做多阶段自动 query rewrite 编排平台
- 不做完整的多路召回实验平台
- 不做完整的 rerank 平台，Rerank 仅作为 Retriever 的下游模块预留
- 不做 Graph RAG 的图检索主链路
- 不做复杂的跨知识库联邦检索编排
- 不做细粒度到业务级精排效果自动调参

说明：
V1 的重点是先把“标准检索请求 -> 查询向量化 -> 向量召回 -> 过滤/去重/截断 -> 标准结果输出”这条主链路跑通。

---

## 5. 术语说明

### 5.1 Query

用户输入或上层模块传入的检索查询内容，通常是文本，也可能附带过滤条件、上下文和目标知识库范围。

### 5.2 Retriever

负责组织召回流程、调用底层检索能力并输出统一候选结果的运行时模块。

### 5.3 Recall

从索引或检索后端中召回候选片段的过程。

### 5.4 Retrieval Hit

一次检索命中的标准结果单元，通常包含：

- chunk_id
- document_id
- score
- text
- metadata
- source position

### 5.5 Filter

对检索范围的约束条件，例如：

- tenant_id
- app_id
- knowledge_base_id
- document_id
- tag
- source_type

### 5.6 Hybrid Retrieval

向量检索与关键词检索等多路召回方式的组合检索能力。

### 5.7 Rerank

对 Retriever 召回出的候选结果再排序的能力，不属于 Retriever V1 的核心实现范围，但必须预留衔接边界。

---

## 6. 方案结论

V1 采用以下统一方案：

1. Retriever 作为 `runtime/retrieval/` 下的独立基础能力落地
2. 上层知识库、Agent、工作流只调用统一 Retriever 服务，不直接依赖向量库 SDK 或临时拼装查询逻辑
3. Retriever 默认消费“query text + filters + retrieval options”这类标准输入
4. Retriever 通过统一 Embedding 能力获取 query vector，通过统一向量库接入能力完成召回
5. Retriever 负责做结果标准化、基础过滤、去重、截断和调试信息归档
6. Hybrid 检索、Rerank、Query Rewrite 在 V1 只预留接口，不强制完整实现

换句话说：

- Embedding 负责“把 query 或 chunk 转成向量”
- 向量库接入负责“把 query vector 变成底层检索结果”
- Retriever 负责“把检索请求组织成可消费的召回结果”
- Rerank 负责“在 Retriever 结果之上做进一步排序”
- RAG 负责“消费最终候选上下文并进入生成”

---

## 7. 与其他模块的职责边界

### 7.1 与 Embedding 模块

Embedding 负责：

- query 向量化
- chunk 向量化
- provider / model 调用

Retriever 负责：

- 组织 query embedding 调用
- 组织检索参数
- 消费 embedding 结果并进入召回流程

Retriever 不负责：

- 直接管理 embedding provider SDK
- 自己维护 embedding model 路由规则

### 7.2 与索引构建模块

索引构建模块负责：

- 把 chunk、vector、metadata 组织成标准索引记录
- 写入索引版本

Retriever 负责：

- 基于已可检索的索引执行查询

Retriever 不负责：

- 建索引
- 重建索引
- 补写索引数据

### 7.3 与向量库接入模块

向量库接入模块负责：

- collection / namespace 管理
- upsert / delete / query 协议
- 屏蔽不同后端差异

Retriever 负责：

- 构造查询请求
- 传入 filters、top_k、threshold 等参数
- 标准化结果

Retriever 不负责：

- 直接依赖具体向量库 SDK
- 维护底层 schema 与连接配置

### 7.4 与 Rerank 模块

Rerank 模块负责：

- 对候选集进一步排序
- 输出更接近生成需求的结果顺序

Retriever 负责：

- 提供候选结果集
- 保留可供 rerank 使用的文本和元数据

Retriever 不负责：

- 最终精排
- 复杂相关性建模

### 7.5 与 RAG 模块

RAG 模块负责：

- 检索请求编排
- 上下文窗口控制
- Prompt 组装
- 生成阶段调用

Retriever 负责：

- 提供标准检索结果列表
- 提供来源定位信息和得分信息

RAG 不应负责：

- 直接写向量检索逻辑
- 直接依赖向量库后端

### 7.6 与知识库模块

知识库模块负责：

- 管理知识库实体
- 选择检索范围
- 编排入库与查询流程

Retriever 负责：

- 提供跨知识库检索能力的统一运行时入口

知识库模块不应负责：

- 自己实现一套独立检索内核

---

## 8. 用户与使用场景

### 8.1 知识库问答场景

- 作为知识库模块，我希望只传入 query、knowledge_base_id 和 filters，就能拿到统一的候选片段结果
- 我希望检索结果带有来源页码、段落或 chunk 位置信息，供回答引用和回源使用

### 8.2 Agent 场景

- 作为 Agent 模块，我希望某个节点需要查资料时，只调用统一 Retriever，而不是在节点代码里拼装向量查询
- 我希望不同 Agent 节点拿到同一种结果结构，而不是感知底层后端差异

### 8.3 工作流场景

- 作为工作流模块，我希望可以把 Retriever 作为一个标准节点能力嵌入流程中
- 我希望运行时能记录一次检索用了哪个知识库、多少候选、耗时多少

### 8.4 平台治理场景

- 作为平台，我希望知道每次检索的 query、filters、top_k、命中数、耗时和错误类型
- 我希望后续可以按租户、应用、知识库维度分析召回效果

---

## 9. 范围定义

### 9.1 V1 必做范围

- 统一检索请求/响应协议
- 基于 query text 的标准检索主链路
- 查询向量化能力接入
- 向量相似度检索接入
- 过滤条件透传
- top_k、score threshold、去重、截断
- 标准命中结果对象
- 基础 trace、错误归一和调试信息

### 9.2 V1 预留但不强制实现

- Query Rewrite
- 多路召回融合
- 稀疏检索 / BM25
- 完整 Hybrid Retrieval
- Rerank 集成
- 多知识库跨源召回融合
- 基于用户画像或会话历史的个性化检索

---

## 10. 推荐目录落位

建议后续按以下目录落位：

```text
app/
├─ runtime/
│  ├─ retrieval/
│  │  ├─ schemas.py
│  │  ├─ base.py
│  │  ├─ query_understanding.py
│  │  ├─ filter_builder.py
│  │  ├─ recall_service.py
│  │  ├─ fusion_service.py
│  │  ├─ result_normalizer.py
│  │  ├─ gateway_service.py
│  │  └─ error_mapper.py
│  ├─ embeddings/
│  └─ rerankers/
├─ integrations/
│  ├─ vector_stores/
│  └─ search_backends/
└─ modules/
   ├─ knowledge_center/
   │  └─ services/
   │     └─ retrieval_service.py
   └─ agent_center/
```

说明：

- `runtime/retrieval/` 负责统一 Retriever 协议、流程编排和结果标准化
- `runtime/embeddings/` 负责 query embedding 能力
- `integrations/vector_stores/` 负责底层向量检索后端适配
- `knowledge_center` 和 `agent_center` 只负责调用，不直接持有检索内核逻辑

---

## 11. 核心产品规则

### 11.1 单一检索入口规则

上层业务只能通过统一 Retriever 模块执行检索，不允许直接调用向量库或自定义相似度查询代码。

### 11.2 单一结果结构规则

无论底层是向量检索还是未来的混合检索，输出给上层的都必须是统一 `RetrievalHit` 结构。

### 11.3 过滤前置规则

tenant、app、knowledge_base 等过滤条件必须在检索阶段前置透传，不允许完全依赖结果返回后再二次过滤。

### 11.4 去重统一规则

相同 chunk、相同文档重复命中或多路召回命中时，必须由 Retriever 统一处理去重或聚合。

### 11.5 回源可追踪规则

每个检索结果必须可回溯到：

- knowledge_base_id
- document_id
- chunk_id
- source position

### 11.6 调试信息受控输出规则

Retriever 可以记录 query vector 维度、命中分数、候选总数等调试信息，但不应默认把底层后端原始响应直接暴露给业务层。

---

## 12. 功能需求

### 12.1 统一检索入口

系统必须提供统一检索接口，例如：

```python
retrieve(request: RetrievalRequest) -> RetrievalResult
```

该入口对上层屏蔽以下差异：

- embedding provider 差异
- 向量库后端协议差异
- 命中结果结构差异
- 错误模型差异

### 12.2 Query 预处理

Retriever 在 V1 至少要支持：

- 接收 query text
- 清洗空白字符
- 记录原始 query
- 为后续 Query Rewrite 预留扩展位

### 12.3 Query Embedding

Retriever 必须支持调用统一 Embedding 能力，将 query text 转成 query vector。

### 12.4 检索范围控制

Retriever 必须支持：

- knowledge_base_id 过滤
- tenant_id 过滤
- app_id 过滤
- document_id 过滤
- tag / source_type 等 metadata 过滤

### 12.5 召回控制

Retriever 必须支持：

- top_k
- score_threshold
- include_text
- include_metadata
- include_positions

### 12.6 结果后处理

Retriever 必须支持：

- 基础去重
- 分数标准化预留位
- 截断候选数量
- 结果排序稳定输出

### 12.7 结果标准化

Retriever 输出的每个命中项至少包含：

- chunk_id
- document_id
- score
- text
- metadata
- source position

### 12.8 调试与观测

Retriever 必须输出可记录的调试信息，例如：

- trace_id
- query
- top_k
- filter_keys
- candidate_count
- hit_count
- latency_ms

---

## 13. 数据模型建议

### 13.1 检索请求对象

```python
class RetrievalRequest(BaseModel):
    tenant_id: str
    app_id: str
    knowledge_base_id: str
    query: str
    top_k: int = 10
    score_threshold: float | None = None
    document_ids: list[str] = Field(default_factory=list)
    filters: dict = Field(default_factory=dict)
    include_text: bool = True
    include_metadata: bool = True
    include_positions: bool = True
    metadata: dict = Field(default_factory=dict)
```

### 13.2 检索命中对象

```python
class RetrievalHit(BaseModel):
    chunk_id: str
    document_id: str
    score: float
    text: str | None = None
    metadata: dict = Field(default_factory=dict)
    source_position: dict = Field(default_factory=dict)
```

### 13.3 检索结果对象

```python
class RetrievalResult(BaseModel):
    trace_id: str
    query: str
    total_hits: int
    hits: list[RetrievalHit] = Field(default_factory=list)
    latency_ms: int
    retrieval_strategy: str
    debug_info: dict = Field(default_factory=dict)
```

### 13.4 检索调试对象

```python
class RetrievalDebugInfo(BaseModel):
    query_vector_dimension: int | None = None
    candidate_count: int = 0
    filtered_count: int = 0
    deduped_count: int = 0
    store_provider: str | None = None
```

---

## 14. 标准执行流程

### 14.1 标准检索流程

```text
上层模块发起 RetrievalRequest
-> Retriever 校验请求
-> Query 预处理
-> 调用 Embedding 获取 query vector
-> 构造向量检索请求
-> 调用向量库接入模块 query
-> 执行过滤、去重、截断
-> 标准化为 RetrievalHit 列表
-> 返回 RetrievalResult
```

### 14.2 RAG 查询流程

```text
用户问题
-> RAG 服务组装 RetrievalRequest
-> Retriever 返回候选上下文
-> 可选 Rerank
-> 截取上下文窗口
-> 进入生成阶段
```

### 14.3 Agent 查询流程

```text
Agent 节点触发检索
-> 调用统一 Retriever
-> 返回候选片段
-> 节点决定是否继续推理、调用工具或回答
```

### 14.4 未来混合检索预留流程

```text
Query
-> Query 预处理
-> 向量召回
-> 关键词召回
-> 候选融合
-> 去重/截断
-> 可选 Rerank
-> 返回标准结果
```

---

## 15. 模块职责设计

### 15.1 runtime/retrieval/gateway_service

职责：

- 接收标准检索请求
- 编排 query embedding、向量召回和结果标准化
- 输出统一 RetrievalResult

非职责：

- 不直接管理底层向量库连接
- 不直接管理索引写入

### 15.2 runtime/retrieval/filter_builder

职责：

- 统一 tenant、app、knowledge_base、document 等过滤条件构造
- 输出底层检索可消费的标准 filter 对象

### 15.3 runtime/retrieval/fusion_service

职责：

- 预留未来多路召回融合逻辑
- V1 可先实现单路召回透传

### 15.4 runtime/retrieval/result_normalizer

职责：

- 把底层 query 结果转成统一 RetrievalHit 结构
- 保证字段稳定

### 15.5 integrations/vector_stores

职责：

- 屏蔽不同后端 query 协议差异
- 返回统一基础命中结构

---

## 16. 配置设计

### 16.1 环境变量建议

```env
# Retrieval runtime
RETRIEVAL_DEFAULT_TOP_K=10
RETRIEVAL_MAX_TOP_K=50
RETRIEVAL_DEFAULT_SCORE_THRESHOLD=
RETRIEVAL_TIMEOUT_MS=60000
RETRIEVAL_ENABLE_HYBRID=false

# Query embedding
RETRIEVAL_QUERY_LOGICAL_MODEL=embedding_query_default
```

### 16.2 配置原则

- 检索默认参数由统一配置管理
- 上层业务可传业务参数，但不能突破系统上限约束
- query embedding 模型由模型管理模块统一治理
- filters 白名单字段由 Retriever 统一治理

---

## 17. 错误模型建议

系统内部建议至少归一以下错误类型：

- `retrieval_configuration_error`
- `retrieval_validation_error`
- `retrieval_query_empty`
- `retrieval_embedding_error`
- `retrieval_store_timeout`
- `retrieval_store_unavailable`
- `retrieval_filter_error`
- `retrieval_result_error`
- `retrieval_unknown_error`

目标是让上层模块不直接感知底层 Embedding 或向量库后端的原始错误格式。

---

## 18. 观测与审计

每次检索至少记录：

- trace_id
- tenant_id
- app_id
- knowledge_base_id
- query
- retrieval_strategy
- top_k
- score_threshold
- filter_keys
- candidate_count
- total_hits
- latency_ms
- status
- error_code

建议重点关注以下指标：

- 检索总请求量
- 平均延迟
- P95 / P99 延迟
- 平均命中数
- 零命中率
- 过滤命中率
- 检索失败率

---

## 19. 风险与约束

### 19.1 风险

- 如果 Retriever 不统一，后续 RAG、Agent、知识库会各自维护检索逻辑
- 如果过滤条件不前置，可能导致越权召回或无效召回
- 如果结果结构不统一，RAG 与 Rerank 会被底层后端格式绑定
- 如果 query embedding 与索引 embedding 版本不一致，召回效果会明显下降
- 如果不保留来源位置信息，后续引用与回源能力会受影响

### 19.2 约束

- V1 必须优先保证边界清晰
- V1 必须先保证单路向量检索稳定可跑
- V1 不应把 Rerank、Hybrid、Query Rewrite 全部挤进第一阶段
- V1 不应让上层模块绕过 Retriever 直接查询底层后端

---

## 20. 分阶段落地建议

### 20.1 第一阶段

- 定义 RetrievalRequest / RetrievalResult 协议
- 打通 query embedding
- 打通单路向量召回
- 打通结果标准化
- 打通知识库查询主链路

### 20.2 第二阶段

- 增加过滤条件白名单治理
- 增加去重与截断策略
- 增加调试信息与召回指标记录
- 增加 Agent 与工作流复用

### 20.3 第三阶段

- 增加 Query Rewrite
- 增加关键词检索
- 增加 Hybrid 融合
- 增加与 Rerank 模块的标准衔接

---

## 21. 验收标准

### 21.1 功能验收

- 上层模块可以通过统一接口发起检索
- query text 可以稳定完成 query embedding 并进入召回
- 召回结果可以统一返回标准 `RetrievalHit`
- 检索结果可以携带来源 document_id、chunk_id 和位置元数据
- 可支持 knowledge_base 级别和 document 级别过滤

### 21.2 架构验收

- 上层业务不直接依赖向量库 SDK
- 上层业务不直接拼装检索协议
- Retriever、Embedding、向量库接入、Rerank、RAG 边界清晰
- 检索后端差异被收敛在 `integrations/vector_stores/`

### 21.3 数据验收

- 每次检索均有 trace_id
- 可回溯 query、knowledge_base_id、top_k、filters 和命中结果
- 可区分检索阶段错误与生成阶段错误

---

## 22. 最终结论摘要

Retriever 模块不应散落在知识库、Agent、工作流或 RAG 业务流程中，而应作为知识库与检索层中的独立标准能力实现。

正确的链路应是：

```text
文档解析 -> Chunking -> Embedding -> 索引构建 -> 向量库接入
                                      ^
                                      |
用户 Query -> Retriever -> Query Embedding -> 向量召回 -> 标准结果 -> RAG / Agent
```

这意味着：

- Embedding 负责“文本到向量”
- 向量库接入负责“底层查询协议”
- Retriever 负责“检索流程编排与结果标准化”
- RAG 和 Agent 只消费统一检索结果

这样做的结果是：

- 架构边界更清晰
- 业务模块更轻
- 后续接入 Hybrid、Rerank、Query Rewrite 更容易
- 检索治理、评测和优化更容易落地
