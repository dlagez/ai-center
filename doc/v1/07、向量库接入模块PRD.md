# 向量库接入模块 PRD（V1）

## 1. 文档目的

本文档用于明确 AI 中台在 V1 阶段如何建设统一的“向量库接入模块”，并将 **Qdrant** 作为默认且唯一的生产向量库后端。

本文档重点回答以下问题：

- 向量库接入模块在当前架构中的定位
- 向量库接入与 Embedding、索引构建、Retrieval 之间的职责边界
- 为什么 V1 选择 Qdrant
- 如何定义统一的 collection、payload、upsert、query、delete 协议
- 知识库、Retriever、Agent 如何复用统一的向量库能力
- V1 的实现范围、验收标准与后续演进方向

本文档要解决的问题不是“要不要接向量库”，而是“如何把 Qdrant 作为统一向量存储能力沉到检索基础设施层，而不是散落在知识库和检索代码中直接使用 SDK”。

---

## 2. 背景

当前知识库主链路已经拆分为以下几个能力层：

- 文档解析
- Chunking
- Embedding
- 索引构建
- 向量库接入
- Retrieval / RAG

其中：

- 文档解析负责把原始文件还原为标准化文本与结构化结果
- Chunking 负责把长文本切分为可索引片段
- Embedding 负责把片段映射为向量
- 索引构建负责把 chunk、vector、metadata 组织成标准索引记录
- 向量库接入负责把标准索引记录写入向量库并提供查询、删除能力
- Retrieval 负责基于 query vector 和过滤条件完成召回

如果不建立统一的向量库接入层，通常会出现以下问题：

- 知识库入库流程直接绑定某个向量库 SDK
- Retrieval 自己再写一套 query 逻辑
- collection 命名、过滤字段、版本隔离规则分散在多个模块
- 后续切换向量库或升级 schema 的影响面过大
- 无法统一做 trace、错误归一、权限过滤和观测

因此，V1 需要建立统一的向量库接入模块，并明确：

- **Qdrant 是 V1 的标准生产向量后端**
- 当前本地 `local_file` 方案仅保留为开发调试或单测兜底，不作为生产方案

---

## 3. V1 方案结论

### 3.1 总体结论

V1 采用以下统一方案：

1. 向量库接入能力落在 `app/runtime/retrieval/vector_store/`
2. 具体后端适配放在 `app/integrations/vector_stores/`
3. V1 生产环境统一使用 **Qdrant**
4. 知识库入库与 Retrieval 都只能通过统一向量库接口访问 Qdrant
5. collection 命名、payload 结构、过滤字段、索引版本规则由向量库接入层统一治理
6. `local_file` 仅保留为开发/测试 fallback，不作为正式部署目标

### 3.2 选择 Qdrant 的原因

V1 选择 Qdrant，主要基于以下考虑：

- 对向量检索场景聚焦，语义清晰，接入成本低
- 原生支持 payload filter，适合 `tenant_id/app_id/knowledge_base_id/document_id` 这类过滤
- 支持 collection 管理，适合做索引版本切换
- 支持 HTTP 与 Python SDK，便于统一封装
- 支持余弦、点积、欧式距离，能覆盖当前 embedding 检索需求
- 适合中小规模到中大规模知识库场景，运维复杂度低于自建 pgvector 方案

### 3.3 不采用其他方案作为 V1 主方案的原因

- `local_file`：只适合开发和单测，不适合生产检索、并发写入和可观测治理
- `pgvector`：适合与关系库强耦合场景，但 V1 重点不是关系查询整合，而是尽快建立标准检索底座
- `Milvus`：能力强，但 V1 当前复杂度和运维成本偏高

---

## 4. 目标与非目标

### 4.1 V1 目标

- 提供统一的向量写入接口
- 提供统一的向量查询接口
- 提供统一的删除接口
- 使用 Qdrant 落地知识库索引存储
- 支持 collection 级索引版本隔离
- 支持 metadata filter
- 支持基础 trace、错误归一、调用耗时记录
- 让知识库入库和 Retrieval 走同一套向量库能力

### 4.2 V1 非目标

- 不做完整的向量库管理后台 UI
- 不做多向量字段管理
- 不做稀疏向量/混合检索一体化编排
- 不做自动 ANN 参数调优
- 不做跨地域多活容灾
- 不做多后端同时在线切换治理

---

## 5. 架构定位与职责边界

### 5.1 与 Embedding 模块

Embedding 负责：

- 文本到向量
- provider/model 调用
- 向量维度返回

向量库接入模块负责：

- collection 管理
- 向量写入
- 向量查询
- 向量删除
- payload filter 映射

向量库接入模块不负责：

- 生成向量
- 选择 embedding 模型
- provider fallback

### 5.2 与索引构建模块

索引构建模块负责：

- 组织 `IndexRecord`
- 组织批量写入请求
- 管理 `index_version` 语义

向量库接入模块负责：

- 确保 collection 存在
- 校验向量维度
- 执行 upsert / query / delete
- 维护后端 schema 与命名规则

### 5.3 与 Retrieval 模块

Retrieval 负责：

- 生成 query vector
- 组织 filter / top_k
- 处理召回后的阈值过滤、去重、后续 rerank

向量库接入模块负责：

- 执行相似度检索
- 把统一 filter 映射成 Qdrant filter
- 返回统一命中结果结构

### 5.4 与知识库模块

知识库模块负责：

- 文档上传
- 入库任务编排
- 触发解析、Chunking、Embedding、索引构建

向量库接入模块不负责：

- 文档生命周期管理
- 入库业务状态机
- 权限业务规则本身

---

## 6. V1 存储方案

### 6.1 Qdrant 作为正式向量存储

生产环境使用 Qdrant 存储以下内容：

- 向量
- chunk text
- document_id / chunk_id
- 检索过滤所需 payload
- 原文定位信息摘要

### 6.2 local_file 的定位

`local_file` 保留为以下用途：

- 本地开发调试
- 单元测试
- 无外部依赖时的最小可运行模式

但不作为：

- 生产环境向量库
- 压测环境标准后端
- 正式知识库部署方案

---

## 7. 数据模型设计

### 7.1 collection 命名规则

统一规则：

```text
{prefix}{tenant_id}__{app_id}__{knowledge_base_id}__{index_name}__{index_version}
```

默认前缀：

```text
kb_
```

要求：

- 由接入层统一生成
- 上层业务不得自行拼接 collection 名称
- 必须包含租户、应用、知识库、索引名、索引版本

### 7.2 Qdrant point 映射

统一写入 Qdrant 的 point 结构如下：

- `id`: 使用稳定主键，建议为 `chunk_id`
- `vector`: embedding 结果
- `payload`: 统一 metadata

### 7.3 payload 字段建议

V1 标准 payload 至少包含：

- `tenant_id`
- `app_id`
- `knowledge_base_id`
- `index_name`
- `index_version`
- `document_id`
- `chunk_id`
- `text`
- `chunk_index`
- `file_name`
- `file_type`
- `source_type`
- `title_path`
- `page_range`
- `source_block_ids`
- `source_positions`
- `source_position`
- `policy_name`

说明：

- `text` 放入 payload，便于直接返回召回文本
- `source_position` 用于快速返回单一定位
- `source_positions` 用于保留更完整的位置信息

### 7.4 位置信息约束

当前阶段最小定位信息遵循既有 PRD：

- 页式文档只保留 `page_no`
- Excel / CSV 先保留 `row_index`

因此 `source_position` / `source_positions` 中，V1 必须保证：

- PDF / 图片 / PPT 等页式文档可回溯 `page_no`
- Excel / CSV 可回溯 `row_index`

---

## 8. 接口协议

### 8.1 Ensure Collection

```python
ensure_collection(request: EnsureCollectionRequest) -> EnsureCollectionResult
```

职责：

- 检查 collection 是否存在
- 不存在时创建
- 校验向量维度与距离类型

### 8.2 Upsert Records

```python
upsert_records(request: VectorUpsertRequest) -> VectorUpsertResult
```

职责：

- 批量写入 points
- 对同一 `collection + chunk_id` 执行稳定 upsert
- 返回成功数、失败数、错误信息

### 8.3 Query Vectors

```python
query_vectors(request: VectorQueryRequest) -> VectorQueryResult
```

职责：

- 使用 query vector 执行相似度搜索
- 支持 `top_k`
- 支持 metadata filter
- 返回统一命中结构

### 8.4 Delete Records

```python
delete_records(request: VectorDeleteRequest) -> VectorDeleteResult
```

职责：

- 按 `chunk_id` 删除
- 按 `document_id` 批量删除
- 后续可扩展按 `index_version` 清理

---

## 9. Qdrant 适配规则

### 9.1 距离类型映射

统一 metric 与 Qdrant distance 的映射：

- `cosine` -> `Cosine`
- `dot` -> `Dot`
- `euclidean` -> `Euclid`

### 9.2 filter 映射

统一过滤请求：

```python
filters = {
    "tenant_id": "t1",
    "knowledge_base_id": "kb1",
    "document_id": ["doc1", "doc2"],
}
```

映射为 Qdrant filter 时要求：

- 单值字段使用 `match`
- 多值字段使用 `should` 或等价 `match any`
- 上层不感知 Qdrant 原生 filter 结构

### 9.3 主键策略

V1 统一使用 `chunk_id` 作为 point id。

要求：

- 同一 chunk 重复写入时能覆盖
- 保证删除与回溯简单稳定

### 9.4 collection 维度约束

同一个 collection 只允许一种向量维度。

因此：

- 切换 embedding 模型且维度变化时，必须切换 `index_version`
- 不允许不同维度写入同一 collection

---

## 10. 推荐目录落位

```text
app/
├─ runtime/
│  └─ retrieval/
│     └─ vector_store/
│        ├─ schemas.py
│        ├─ service.py
│        └─ __init__.py
├─ integrations/
│  └─ vector_stores/
│     ├─ base.py
│     ├─ qdrant_adapter.py
│     ├─ local_file_adapter.py
│     └─ __init__.py
└─ modules/
   └─ knowledge_center/
      └─ services/
         └─ knowledge_index_service.py
```

说明：

- `runtime/retrieval/vector_store/` 负责统一协议和治理
- `integrations/vector_stores/qdrant_adapter.py` 负责封装 Qdrant SDK / HTTP API
- `knowledge_center` 和 `retrieval` 只能依赖统一 service，不直接依赖 Qdrant

---

## 11. 配置设计

### 11.1 环境变量建议

```env
# Vector store runtime
VECTOR_STORE_PROVIDER=qdrant
VECTOR_STORE_TIMEOUT_MS=60000
VECTOR_STORE_DEFAULT_METRIC=cosine
VECTOR_STORE_COLLECTION_PREFIX=kb_
VECTOR_STORE_LOCAL_DIR=data/vector_store

# Qdrant
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
QDRANT_GRPC_PORT=6334
QDRANT_PREFER_GRPC=false
QDRANT_HTTPS=false
```

### 11.2 配置原则

- 生产默认 `VECTOR_STORE_PROVIDER=qdrant`
- 上层业务不允许感知 Qdrant 连接细节
- collection 前缀与 metric 由接入层统一治理
- 开发环境可切回 `local_file`，但默认文档和部署说明以 Qdrant 为准

---

## 12. 核心产品规则

### 12.1 单一向量库入口规则

上层业务只能通过统一向量库接入模块访问 Qdrant，不允许业务代码直接调用 Qdrant SDK。

### 12.2 单一命名规则

collection 名称必须由接入层生成，不允许业务层自由拼接。

### 12.3 单一 payload 规则

所有写入 Qdrant 的 point payload 必须符合统一字段规范，不允许各业务模块输出不可治理的自定义结构。

### 12.4 单一 upsert 语义

同一 `collection + chunk_id` 重复写入必须表现为幂等覆盖，而不是产生重复记录。

### 12.5 权限过滤前置规则

检索过滤必须在 Qdrant 查询阶段完成，至少支持：

- `tenant_id`
- `app_id`
- `knowledge_base_id`
- `document_id`

不能依赖“先查出结果再在应用层筛掉”。

---

## 13. 标准执行流程

### 13.1 入库写入流程

```text
文档解析
-> Chunking
-> Embedding
-> 索引构建
-> VectorStoreService.ensure_collection()
-> VectorStoreService.upsert_records()
-> 返回写入结果
```

### 13.2 检索查询流程

```text
用户 query
-> Embedding 生成 query vector
-> Retrieval 组装 filters / top_k
-> VectorStoreService.query_vectors()
-> 返回统一命中结果
-> Retrieval 继续做阈值过滤 / 去重 / rerank
```

### 13.3 索引重建流程

```text
创建新 index_version 对应 collection
-> 批量写入新版本数据
-> 校验写入完成
-> 上层切换 active index_version
-> 按策略清理旧版本 collection
```

---

## 14. 实现要求

### 14.1 V1 必做

- 新增 Qdrant adapter
- 新增 Qdrant 连接配置
- `VectorStoreService` 默认 provider 切换为 `qdrant`
- 知识库写入链路接到 Qdrant
- Retrieval 查询链路接到 Qdrant
- 支持按 document_id 删除
- 支持统一 metadata filter
- 支持 trace、provider、collection、latency 记录

### 14.2 V1 可选但推荐

- 为高频过滤字段建立 payload index
- 增加 collection 初始化检查
- 增加启动期健康检查

### 14.3 V1 不做

- 稀疏向量
- 多向量字段
- hybrid search 编排
- shard/replica 自动治理

---

## 15. 错误模型建议

系统内部至少归一以下错误类型：

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

目标是让上层模块不直接感知 Qdrant SDK 的原始异常格式。

---

## 16. 观测与审计

每次 collection 操作至少记录：

- `trace_id`
- `provider`
- `collection_name`
- `dimension`
- `metric_type`
- `status`
- `latency_ms`

每次 upsert 至少记录：

- `trace_id`
- `tenant_id`
- `app_id`
- `knowledge_base_id`
- `collection_name`
- `index_version`
- `batch_size`
- `success_count`
- `failed_count`
- `latency_ms`
- `status`
- `error_code`

每次 query 至少记录：

- `trace_id`
- `collection_name`
- `top_k`
- `filter_keys`
- `hit_count`
- `latency_ms`
- `status`
- `error_code`

---

## 17. 风险与约束

### 17.1 风险

- 如果知识库和 Retrieval 分别直连不同 Qdrant 调用实现，会形成双接入层
- 如果 collection 命名不统一，会导致索引版本切换混乱
- 如果 payload 字段不收敛，后续 filter 会难以治理
- 如果维度校验缺失，切换 embedding 模型时容易写出脏数据

### 17.2 约束

- V1 必须优先保证边界清晰
- V1 必须先保证单后端稳定跑通
- V1 必须保证知识库入库与 Retrieval 共用同一接入层
- V1 不为了兼容所有向量库特性而破坏统一协议

---

## 18. 分阶段落地建议

### 18.1 第一阶段

- 定义统一协议
- 增加 Qdrant adapter
- 打通知识库写入链路
- 打通 Retrieval 查询链路

### 18.2 第二阶段

- 增加 payload index
- 增加删除与重建治理
- 增加健康检查与启动自检

### 18.3 第三阶段

- 增加 hybrid search 扩展能力
- 增加更多后端适配
- 增加多版本索引治理能力

---

## 19. 验收标准

### 19.1 功能验收

- 标准 `VectorRecord` 可统一写入 Qdrant
- Retrieval 可通过统一 query 接口完成向量召回
- 同一 `collection + chunk_id` 重复写入具备稳定 upsert 语义
- 可按 `document_id` 或 `chunk_id` 删除
- 可按 `index_version` 支持重建和切换

### 19.2 架构验收

- 上层业务不直接依赖 Qdrant SDK
- Embedding、索引构建、向量库接入、Retrieval 边界清晰
- Qdrant 差异收敛在 `integrations/vector_stores/`
- collection 命名与 payload 规则由统一模块治理

### 19.3 数据验收

- 每次写入与查询都有 `trace_id`
- 可回溯 `provider / collection / index_version`
- 命中结果可回溯 `chunk_id / document_id / source_position`
- 维度不兼容与 schema 错误可被识别并归类

---

## 20. 最终结论摘要

V1 的向量库接入模块应明确以 **Qdrant** 为统一生产后端，而不是继续使用本地文件型向量存储承载正式知识库能力。

正确链路应为：

```text
文档解析 -> Chunking -> Embedding -> 索引构建 -> Qdrant 向量库接入 -> Retrieval / RAG
```

这样做的结果是：

- 架构边界更清晰
- 知识库入库与检索共用同一存储底座
- 向量数据、过滤字段和索引版本更容易治理
- 后续扩展 hybrid search 或替换后端时成本更低
