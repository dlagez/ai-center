# 向量库接入模块 PRD（V1）
## 1. 文档目的

本文档用于明确 AI 中台在 V1 阶段如何建设统一的“向量库接入模块”，并回答以下问题：

- 向量库接入模块在当前架构中的定位
- 向量库接入与 Embedding、索引构建、Retrieval 之间的职责边界
- 向量库接入能力应落在哪些目录与模块
- 如何定义统一的 collection、schema、upsert、query、delete 协议
- 知识库、Agent、工作流如何复用统一的向量库接入能力
- V1 的实现范围、验收标准和后续演进方向

本文档要解决的问题不是“要不要接向量库”，而是“在当前项目架构下，如何把不同向量库后端的差异收敛为统一、可治理、可扩展的标准能力，而不是散落在知识库入库和检索流程中的 SDK 直连代码”。
---

## 2. 背景

根据当前架构，知识库与检索层由以下关键能力组成：

- 文档解析
- Chunking
- Embedding
- 索引构建
- 向量库接入
- Retrieval
- RAG / Graph RAG

其中：

- 文档解析负责把原始文件还原为标准化文档结构
- Chunking 负责把长文档切成可索引片段
- Embedding 负责把片段映射为向量
- 索引构建负责组织写入批次、索引版本和元数据
- 向量库接入负责把标准化索引记录写入具体向量后端，并提供统一查询与删除协议
- Retrieval 负责基于 query、过滤条件和召回策略消费向量库能力

如果不把向量库接入模块独立出来，后续通常会出现以下问题：

- 知识库入库流程直接绑定某个向量库 SDK
- Retrieval 模块再单独实现一套 query 逻辑
- 删除、重建、collection 管理、索引版本切换逻辑散落在多个业务服务中
- 替换向量库后端时影响面过大
- 无法统一做租户隔离、索引命名、过滤字段约束、观测与审计

因此，V1 需要建立统一的向量库接入模块，作为“索引记录到具体向量库后端”的标准适配层。
---

## 3. V1 目标

### 3.1 产品目标

- 提供统一的向量库写入接口
- 提供统一的向量库查询接口
- 提供统一的删除、重建、collection 管理接口
- 支持至少 1 种向量库后端接入
- 支持知识库入库流程复用统一向量库能力
- 支持 Retrieval / RAG 复用统一查询能力
- 支持后续扩展更多向量库后端而不改上层主流程
- 支持基础 trace、耗时、状态、失败记录与索引版本信息

### 3.2 业务价值

- 降低向量库 SDK 直连带来的耦合
- 为索引构建和 Retrieval 提供统一数据访问边界
- 为后续切换 pgvector、Milvus、Qdrant 等后端预留清晰接口
- 为租户隔离、权限过滤、索引治理、重建治理提供统一抓手
- 为后续混合检索、多索引、多版本演进提供稳定底座
---

## 4. V1 非目标

以下内容不属于本次 V1 必做范围：

- 不做完整的向量库管理后台 UI
- 不做多向量字段、多 embedding 视图的复杂管理体系
- 不做自动 ANN 参数调优
- 不做完整的混合检索编排平台
- 不做跨区域多活容灾架构
- 不做细粒度到财务级别的向量库存储成本结算
- 不做所有向量库特性的最优抽象覆盖

说明：
V1 的重点是先把“统一协议 + 单后端打通 + 上层复用”这条主链路跑通。
---

## 5. 术语说明

### 5.1 Vector Store

负责存储向量并支持相似度检索的后端系统，例如：

- pgvector
- Milvus
- Qdrant
- Elasticsearch 向量索引

### 5.2 Collection / Index

向量库中的逻辑存储单元。不同后端名称可能不同，但在本项目中统一抽象为“collection”。

### 5.3 Index Record

索引构建模块输出的标准写入单元，通常包含：

- chunk_id
- document_id
- text
- vector
- metadata

### 5.4 Filterable Metadata

可被检索过滤条件消费的元数据字段，例如：

- tenant_id
- app_id
- knowledge_base_id
- document_id
- source_type
- tags

### 5.5 Similarity Search

基于 query vector 在向量库中执行近似相似度检索的能力。

### 5.6 Namespace

用于表达租户、应用、知识库、索引版本等逻辑隔离边界的统一命名空间概念。
---

## 6. 方案结论

V1 采用以下统一方案：

1. 向量库接入作为独立基础能力落在 `app/runtime/retrieval/vector_store/`
2. 具体后端适配放在 `app/integrations/vector_stores/`
3. 索引构建模块只负责组织标准 `IndexRecord`，不直接依赖具体向量库 SDK
4. Retrieval 模块只调用统一向量库查询接口，不直接依赖具体向量库 SDK
5. collection 命名、schema 约束、版本命名、过滤字段约束由向量库接入模块统一治理
6. 后端切换通过 adapter 与配置完成，而不是修改知识库入库和 Retrieval 主流程

换句话说：

- `runtime/retrieval/vector_store` 管“统一协议、数据面操作与治理规则”
- `integrations/vector_stores` 管“Milvus / pgvector / Qdrant 等后端差异”
- `runtime/retrieval/indexing` 管“上游索引记录的组织与写入编排”
- `runtime/retrieval` 管“检索策略与召回流程”
---

## 7. 与其他模块的职责边界

### 7.1 与 Embedding 模块

Embedding 负责：

- 文本到向量
- provider / model 调用
- 向量维度返回

向量库接入模块负责：

- 向量的存储
- 向量的查询
- collection / schema / upsert / delete

向量库接入模块不负责：

- 生成向量
- 选择 embedding 模型
- provider fallback

### 7.2 与索引构建模块

索引构建模块负责：

- 组织 `IndexRecord`
- 组织批次写入请求
- 管理索引版本语义

向量库接入模块负责：

- 校验 collection 是否存在
- 写入记录
- 维护后端 schema 兼容性
- 提供统一 upsert / delete / query 接口

向量库接入模块不负责：

- 决定 chunk 结构
- 决定 embedding 模型
- 直接编排入库主流程

### 7.3 与 Retrieval / RAG 模块

Retrieval 负责：

- query 理解
- query 改写
- 混合检索编排
- rerank 与结果组装

向量库接入模块负责：

- 相似度检索
- 过滤条件透传
- top_k 查询
- 返回统一命中结果结构

向量库接入模块不负责：

- 最终召回策略决策
- 多路检索融合
- rerank

### 7.4 与知识库模块

知识库模块负责：

- 文档上传
- 入库任务编排
- 触发文档解析、Chunking、Embedding、索引构建

向量库接入模块不负责：

- 入库业务状态机
- 文档生命周期管理
- 知识库权限业务规则本身

### 7.5 与模型管理模块

模型管理模块负责：

- Embedding 模型配置与路由

向量库接入模块负责：

- 向量库后端配置与能力适配

二者边界必须清晰：模型管理不管理向量库存储细节，向量库接入不管理 embedding 模型路由。
---

## 8. 用户与使用场景

### 8.1 知识库入库场景

- 作为知识库模块，我希望标准索引记录可以统一写入向量库，而不是每条入库链路各自维护 SDK 逻辑
- 我希望重试、覆盖写入、删除旧版本索引时有统一能力
- 我希望未来切换向量库后端时不修改入库主流程

### 8.2 Retrieval 场景

- 作为 Retrieval 模块，我希望只关心 query vector、filter 和 top_k，不关心底层向量库协议差异
- 我希望不同后端返回统一的命中结果结构
- 我希望召回结果能稳定回溯到 chunk 与 document 元数据

### 8.3 平台治理场景

- 作为平台，我希望统一记录 collection、索引版本、写入批次、查询耗时和失败原因
- 我希望统一治理租户隔离、字段约束和后端配置
- 我希望后续支持多个向量库后端并保持上层接口稳定
---

## 9. 范围定义

### 9.1 V1 必做范围

- 统一的 collection 管理协议
- 统一的 upsert 协议
- 统一的 similarity query 协议
- 统一的 delete 协议
- 统一的 schema / metadata 字段约束
- 至少 1 种向量库后端 adapter
- 知识库入库主链路复用
- Retrieval 查询主链路复用
- 基础 trace 与错误归一

### 9.2 V1 预留但不强制实现

- 多向量字段
- 稀疏向量与倒排混合索引协同
- 多 collection 联邦查询
- 自动建索引参数优化
- 向量压缩与量化优化
- 向量库冷热分层
- 查询缓存
- 分片迁移与在线重平衡
---

## 10. 推荐目录落位

建议后续按以下目录落位：

```text
app/
├─ runtime/
│  ├─ retrieval/
│  │  ├─ vector_store/
│  │  │  ├─ schemas.py
│  │  │  ├─ base.py
│  │  │  ├─ collection_service.py
│  │  │  ├─ query_service.py
│  │  │  ├─ write_service.py
│  │  │  └─ capability_registry.py
│  │  └─ indexing/
│  │     ├─ service.py
│  │     └─ index_builder.py
├─ integrations/
│  ├─ vector_stores/
│  │  ├─ base.py
│  │  ├─ pgvector_adapter.py
│  │  ├─ milvus_adapter.py
│  │  └─ qdrant_adapter.py
├─ modules/
│  └─ knowledge_center/
│     └─ services/
│        ├─ ingestion_service.py
│        └─ retrieval_service.py
```

说明：

- `runtime/retrieval/vector_store/` 负责统一协议与调用编排
- `integrations/vector_stores/` 负责具体后端适配
- `runtime/retrieval/indexing/` 只组织写入，不直连后端 SDK
- `knowledge_center` 与 Retrieval 服务只依赖统一接入层
---

## 11. 核心产品规则

### 11.1 单一向量库入口规则

上层业务只能通过统一向量库接入模块操作向量后端，不允许直接依赖具体 SDK。

### 11.2 单一命名规则

collection 命名必须通过统一规则生成，不允许业务层随意拼接，至少应包含：

- tenant_id
- app_id 或 knowledge_base_id
- index_name
- index_version

### 11.3 单一 schema 约束规则

所有写入向量库的记录都必须符合统一 metadata 字段白名单与类型约束，不允许各业务自行扩展为不可治理结构。

### 11.4 单一 upsert 语义规则

对同一 `collection + chunk_id` 的重复写入必须具备稳定 upsert 语义，不允许产生不可控重复记录。

### 11.5 查询结果标准化规则

无论底层后端是什么，返回给 Retrieval 的结果都必须包含统一字段：

- chunk_id
- document_id
- score
- text
- metadata

### 11.6 权限过滤前置规则

向量库查询必须支持 tenant、app、knowledge_base、document 等过滤字段透传，不能把权限控制完全推迟到结果返回后再做。
---

## 12. 功能需求

### 12.1 collection 管理能力

系统必须支持统一的 collection 生命周期能力，例如：

```python
ensure_collection(request: EnsureCollectionRequest) -> EnsureCollectionResult
```

至少支持：

- 检查 collection 是否存在
- 不存在时创建
- 校验维度是否兼容
- 校验关键 metadata schema 是否兼容

### 12.2 向量写入能力

系统必须支持统一的写入接口，例如：

```python
upsert_records(request: VectorUpsertRequest) -> VectorUpsertResult
```

至少支持：

- 批量 upsert
- 幂等主键
- 成功数 / 失败数
- 批次级错误返回

### 12.3 向量查询能力

系统必须支持统一的查询接口，例如：

```python
query_vectors(request: VectorQueryRequest) -> VectorQueryResult
```

至少支持：

- query vector 查询
- top_k
- metadata filter
- score 返回

### 12.4 删除能力

系统必须支持统一的删除接口，例如：

```python
delete_records(request: VectorDeleteRequest) -> VectorDeleteResult
```

至少支持：

- 按 chunk_id 删除
- 按 document_id 批量删除
- 按 collection / index_version 级别清理

### 12.5 schema 校验能力

V1 必须支持最小 schema 校验：

- vector dimension
- 主键字段
- tenant / app / knowledge_base 等过滤字段
- text 与 metadata 字段存在性

### 12.6 能力探测能力

由于不同向量库特性差异较大，适配层需要暴露最小能力集，例如：

- 是否支持 metadata filter
- 是否支持删除表达式
- 是否支持 collection 级 schema
- 是否支持命名空间隔离

---

## 13. 数据模型建议

### 13.1 collection 请求对象

```python
class EnsureCollectionRequest(BaseModel):
    tenant_id: str
    app_id: str
    knowledge_base_id: str
    index_name: str
    index_version: str
    dimension: int
    metric_type: str = "cosine"
    metadata_schema: dict = Field(default_factory=dict)
```

### 13.2 写入请求对象

```python
class VectorRecord(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    vector: list[float]
    metadata: dict = Field(default_factory=dict)


class VectorUpsertRequest(BaseModel):
    tenant_id: str
    app_id: str
    knowledge_base_id: str
    collection_name: str
    index_version: str
    records: list[VectorRecord]
    metadata: dict = Field(default_factory=dict)
```

### 13.3 查询请求对象

```python
class VectorQueryRequest(BaseModel):
    tenant_id: str
    app_id: str
    knowledge_base_id: str
    collection_name: str
    query_vector: list[float]
    top_k: int = 10
    filters: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)
```

### 13.4 查询结果对象

```python
class VectorHit(BaseModel):
    chunk_id: str
    document_id: str
    score: float
    text: str | None = None
    metadata: dict = Field(default_factory=dict)


class VectorQueryResult(BaseModel):
    trace_id: str
    collection_name: str
    total_hits: int
    hits: list[VectorHit] = Field(default_factory=list)
    latency_ms: int
    provider: str
```

### 13.5 删除请求对象

```python
class VectorDeleteRequest(BaseModel):
    tenant_id: str
    app_id: str
    knowledge_base_id: str
    collection_name: str
    chunk_ids: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
```
---

## 14. 标准执行流程

### 14.1 入库写入流程

```text
Chunking 输出标准 chunk
-> Embedding 输出向量
-> 索引构建模块组装 IndexRecord
-> 向量库接入模块 ensure collection
-> 向量库接入模块 upsert records
-> 返回写入结果
```

### 14.2 检索查询流程

```text
用户 query
-> Embedding 生成 query vector
-> Retrieval 组装 filter / top_k
-> 向量库接入模块 query
-> 返回统一命中结果
-> Retrieval 后续 rerank / 组装
```

### 14.3 索引重建流程

```text
创建新 index_version 对应 collection
-> 批量写入新版本记录
-> 校验写入完成
-> 上层切换 active index_version
-> 按策略清理旧版本 collection
```
---

## 15. 模块职责设计

### 15.1 runtime/retrieval/vector_store

职责：

- 定义统一协议
- 选择具体 adapter
- 执行 ensure / upsert / query / delete
- 统一错误归一与结果标准化
- 统一命名规则与 schema 校验

非职责：

- 不生成向量
- 不决定召回策略
- 不承担入库任务调度

### 15.2 integrations/vector_stores

职责：

- 对接具体向量库 SDK 或 HTTP API
- 封装 collection、upsert、query、delete 差异
- 映射统一请求和响应结构

非职责：

- 不承担业务权限决策
- 不编排上层工作流
- 不决定 embedding 模型与索引版本策略

### 15.3 runtime/retrieval/indexing

职责：

- 组织 IndexRecord
- 组织索引版本
- 调用向量库接入模块

非职责：

- 不直接依赖具体向量库后端

### 15.4 retrieval service

职责：

- 组织 query vector、filters、top_k
- 消费统一 query 结果

非职责：

- 不直接依赖具体向量库后端
---

## 16. 配置设计

### 16.1 环境变量建议

```env
# Vector store runtime
VECTOR_STORE_PROVIDER=pgvector
VECTOR_STORE_TIMEOUT_MS=60000
VECTOR_STORE_DEFAULT_METRIC=cosine
VECTOR_STORE_COLLECTION_PREFIX=kb_

# pgvector
PGVECTOR_DSN=
PGVECTOR_SCHEMA=public

# milvus
MILVUS_URI=
MILVUS_TOKEN=
MILVUS_DATABASE=default
```

### 16.2 配置原则

- 向量库后端选择通过统一配置完成
- 上层业务不直接保存具体后端凭据
- collection 命名规则统一由接入层管理
- schema 与维度约束必须可配置但不可由业务任意突破
---

## 17. 错误模型建议

系统内部建议至少归一以下错误类型：

- `vector_store_configuration_error`
- `vector_store_validation_error`
- `vector_store_collection_error`
- `vector_store_dimension_mismatch`
- `vector_store_timeout_error`
- `vector_store_authentication_error`
- `vector_store_provider_unavailable`
- `vector_store_write_error`
- `vector_store_query_error`
- `vector_store_delete_error`
- `vector_store_unknown_error`

目标是让上层模块不直接感知具体 SDK 或具体后端的原始错误格式。
---

## 18. 观测与审计

每次 collection 操作至少记录：

- trace_id
- provider
- collection_name
- dimension
- metric_type
- status
- latency_ms

每次 upsert 至少记录：

- trace_id
- tenant_id
- app_id
- knowledge_base_id
- collection_name
- index_version
- batch_size
- success_count
- failed_count
- latency_ms
- status
- error_code

每次 query 至少记录：

- trace_id
- collection_name
- top_k
- filter_keys
- hit_count
- latency_ms
- status
- error_code

建议重点关注以下指标：

- collection 创建次数
- upsert 成功率
- query 平均耗时
- query P95 / P99
- 删除成功率
- 维度不兼容错误数
- 后端不可用错误数
---

## 19. 风险与约束

### 19.1 风险

- 如果索引构建和 Retrieval 分别直连不同 SDK，后续会形成双接入层
- 如果 collection 命名不统一，版本切换和租户隔离会失控
- 如果 metadata 字段不做白名单约束，后续过滤条件会难以治理
- 如果不统一标准化 query 结果，Retrieval 层会被多个后端格式绑死
- 如果维度和 schema 校验缺失，索引重建和模型切换时容易产生脏数据

### 19.2 约束

- V1 必须优先保证边界清晰
- V1 必须支持单后端稳定跑通
- V1 必须保证知识库入库与 Retrieval 都走同一接入层
- V1 不应为了兼容所有后端特性而破坏统一协议
---

## 20. 分阶段落地建议

### 20.1 第一阶段

- 定义统一协议
- 实现 1 个向量库 adapter
- 打通知识库入库写入链路
- 打通 Retrieval 查询链路

### 20.2 第二阶段

- 增加删除与重建能力
- 增加 collection schema 校验
- 增加索引版本切换支持
- 增加基础能力探测

### 20.3 第三阶段

- 增加更多向量库后端
- 增加混合检索协同接口
- 增加查询缓存与更丰富的治理指标
- 增加多版本索引运维治理能力
---

## 21. 验收标准

### 21.1 功能验收

- 标准 `IndexRecord` 可统一写入至少 1 个向量库后端
- Retrieval 可通过统一 query 接口完成向量召回
- 同一 collection + chunk_id 重复写入具备稳定 upsert 语义
- 可按 document_id 或 chunk_id 执行删除
- 可按 index_version 支持重建与切换

### 21.2 架构验收

- 上层业务不直接依赖具体向量库 SDK
- Embedding、索引构建、向量库接入、Retrieval 边界清晰
- 具体后端差异被收敛在 `integrations/vector_stores/`
- collection 命名与 schema 治理由统一模块负责

### 21.3 数据验收

- 每次写入与查询均有 trace_id
- 可回溯 provider、collection、index_version
- 命中结果可回溯 chunk_id 与 document_id
- 维度不兼容与 schema 错误可被识别和归类
---

## 22. 最终结论摘要

向量库接入模块不应散落在知识库入库、Retrieval 或 Agent 业务流程中，而应作为知识库与检索层中的独立标准能力实现。

正确的链路应是：

```text
文档解析 -> Chunking -> Embedding -> 索引构建 -> 向量库接入 -> Retrieval / RAG
```

这意味着：

- Embedding 负责“文本到向量”
- 索引构建负责“组织标准写入记录”
- 向量库接入负责“把记录写入、查询、删除到具体后端”
- Retrieval 负责“基于统一查询结果做召回编排”

这样做的结果是：

- 架构边界更清晰
- 后端切换成本更低
- 治理与观测更集中
- 后续混合检索、多版本索引和多后端扩展更容易落地
