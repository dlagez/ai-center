# 01、接入LangSmith观测评测模块

## 1. 文档目标

本文用于明确当前 `ai-center` 仓库如何接入 **LangSmith**，把现有已经实现的：

- 模型与工具抽象层
- Embedding 与向量库层
- Retrieval / RAG 编排层
- 基础 metrics recorder

进一步升级为一套可用于：

- 线上观测
- 离线评测
- 在线评测
- 人工反馈闭环
- 后续部署演进

的标准化观测评测体系。

本文重点回答以下问题：

- 当前仓库为什么适合现在接入 LangSmith
- LangSmith 接入后，RAG 内部链路如何被看见
- 应该优先采用哪种接入方式
- tracing、evaluation、feedback、deployment 分别如何落位
- 需要新增哪些配置、目录、服务和脚本
- 分阶段实施顺序与验收标准是什么

本文不是 LangSmith 使用教程，也不是直接的代码实现说明，而是面向当前仓库的接入设计文档。

---

## 2. 当前现状

### 2.1 现有能力已经具备

当前仓库已经有一条完整的最小 RAG 主链路：

```text
文档 / 文本
-> parse_and_chunk
-> embedding
-> vector upsert
-> retrieval
-> prompt assembly
-> llm answer
```

对应实现已经存在：

- 文档切块编排：`app/modules/knowledge_center/services/document_chunk_service.py`
- 入库编排：`app/modules/knowledge_center/services/knowledge_index_service.py`
- RAG 问答编排：`app/modules/knowledge_center/services/simple_rag_service.py`
- Embedding 网关：`app/runtime/embedding/gateway_service.py`
- Retrieval 网关：`app/runtime/retrieval/gateway_service.py`
- Vector Store：`app/runtime/retrieval/vector_store/service.py`
- LLM 网关：`app/runtime/llm/gateway_service.py`

### 2.2 当前观测能力的边界

当前仓库已经有一层轻量观测记录器：

- `app/observability/metrics/llm_call_recorder.py`
- `app/observability/metrics/embedding_call_recorder.py`
- `app/observability/metrics/retrieval_call_recorder.py`
- `app/observability/metrics/vector_store_call_recorder.py`

这些 recorder 的价值是：

- 单元测试友好
- 能记录调用结果、耗时、状态和部分 metadata
- 不依赖外部平台

但当前也有明显边界：

- 记录仅在进程内存中
- 没有统一的 trace tree
- 看不到父子调用关系
- 不能在 UI 中按项目、会话、标签、metadata 做过滤和分析
- 没有离线评测、在线评测、人工标注队列能力

### 2.3 当前问题本质

当前不是“没有 trace_id”，而是“**缺少可视化、可查询、可评测的统一 trace 系统**”。

例如当前一次 `SimpleRAGService.answer()` 内部已经会产生：

- RAG trace_id
- retrieval trace_id
- embedding trace_id
- vector store trace_id
- llm trace_id

但这些 trace_id 彼此是并列散落的，不是一个真正可浏览的 run tree。

---

## 3. 接入 LangSmith 的总体结论

### 3.1 结论

当前仓库**非常适合现在接入 LangSmith**。

原因不是因为项目已经足够复杂，而是因为：

1. 现有 RAG 主链路已经跑通，具备可观测对象。
2. 现有服务边界足够清晰，便于按步骤打 span。
3. 当前 `app/observability/tracing`、`app/observability/evals`、`app/observability/feedback` 目录还是空的，正适合按统一方案落位。
4. `requirements.txt` 已经包含 `langsmith==0.7.22`，具备直接接入基础。

### 3.2 推荐路线

本仓库推荐采用“两阶段接入策略”：

1. **第一阶段：LangSmith SDK 直接接入 tracing 与离线评测**
2. **第二阶段：按需要扩展到 OpenTelemetry、在线评测、告警与自托管**

原因：

- 当前仓库还没有 OpenTelemetry 基础设施。
- 直接使用 LangSmith SDK 改动更小，见效最快。
- 先让 `RAG / ingest` 的内部步骤在 LangSmith 中可见，价值最大。
- OpenTelemetry 更适合后续要接统一采集管道、多观测后端或跨服务分布式 tracing 时再引入。

### 3.3 本次设计的核心原则

- 不替换当前 recorder，先与 LangSmith 并行。
- 不打破现有 service API 和返回结构。
- 不要求业务层直接依赖 LangSmith SDK。
- 不把所有底层私有细节都暴露到 trace 中。
- tracing 优先覆盖业务主链路，而不是先把所有 adapter 全部埋满。

---

## 4. 为什么选择 LangSmith

结合官方能力和当前仓库场景，LangSmith 的匹配点主要有：

- 支持把一次请求表示为 trace，把内部步骤表示为 runs/spans。
- 支持在 trace 上附加 tags、metadata、feedback。
- 支持对中间 run 打分，不只支持根节点。
- 支持离线评测数据集、实验对比、回归评测。
- 支持在线 evaluator，对生产 traces 做实时质量检查。
- 支持 dashboard 和 alert，适合后续做 RAG 质量与延迟监控。
- 部署层是可选项，观测和评测并不依赖必须把应用部署到 LangSmith 上。

因此，LangSmith 对当前仓库最直接的价值是：

1. 把“RAG 内部怎么走的”完整展开出来。
2. 把“效果好不好”从肉眼验收升级为可复用评测。
3. 把“线上出现了哪些坏样本”沉淀为数据集和反馈闭环。

---

## 5. 接入边界与非目标

### 5.1 本次要做

- 为 RAG 与知识入库链路建立 LangSmith trace tree
- 为离线评测建立 dataset / evaluator / experiment 基础能力
- 为线上 traces 建立在线 evaluator 与人工反馈入口设计
- 为后续 deployment / self-hosted 预留边界

### 5.2 本次不做

- 不把全部业务代码都重写成 LangChain / LangGraph 风格
- 不要求所有 HTTP 接口立刻接入 LangSmith
- 不强依赖 OpenTelemetry
- 不直接引入 LangSmith Deployment 替代现有服务部署
- 不把所有原始文档全文无脑上传到 trace

---

## 6. 推荐架构方案

### 6.1 总体方案

推荐把 LangSmith 接入拆成三层：

```text
app/observability/
├── tracing/
│   ├── __init__.py
│   ├── context.py
│   ├── langsmith_tracer.py
│   ├── sanitizers.py
│   └── project_router.py
├── evals/
│   ├── __init__.py
│   ├── rag_dataset_service.py
│   ├── rag_offline_evaluator.py
│   ├── retrieval_metrics.py
│   └── scripts_support.py
└── feedback/
    ├── __init__.py
    └── langsmith_feedback_service.py
```

### 6.2 各层职责

`tracing/` 负责：

- 初始化 LangSmith client
- 控制 tracing 开关
- 路由 project name
- 包装 root trace 和 child span
- 统一做 metadata 清洗与输入裁剪
- 提供 `flush()` 能力给脚本和批任务

`evals/` 负责：

- 管理离线评测数据集
- 管理实验命名与执行
- 定义离线 evaluator
- 把线上坏样本沉淀为离线评测集

`feedback/` 负责：

- 把人工反馈和系统反馈写回 LangSmith
- 统一管理反馈 key 命名
- 建立根 run、retrieval run、llm run 的反馈绑定策略

### 6.3 与现有 recorder 的关系

当前 `metrics/*_call_recorder.py` 不建议删除。

建议关系如下：

- recorder：保留，服务于单测、轻量本地调试、结构化断言
- LangSmith：新增，服务于远程观测、可视化、评测、反馈、监控

二者不是互斥关系，而是：

```text
业务服务
-> 现有 InMemory Recorder
-> LangSmith Tracer
```

---

## 7. 配置设计

### 7.1 官方 LangSmith 配置

根据 LangSmith 官方文档，最小接入需要的官方配置包括：

```env
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_PROJECT=default
LANGSMITH_WORKSPACE_ID=
```

说明：

- `LANGSMITH_TRACING` 是 SDK tracing 总开关。
- `LANGSMITH_API_KEY` 是认证凭证。
- `LANGSMITH_ENDPOINT` 在 Cloud 模式下一般为官方地址；自托管时替换成自有地址。
- `LANGSMITH_PROJECT` 是默认 project。
- `LANGSMITH_WORKSPACE_ID` 在一个 API key 对应多个 workspace 时需要显式设置。

### 7.2 应用内建议新增配置

除了官方配置，建议在 `app/core/config.py` 中新增一组应用内配置，避免所有策略都挤在官方 env 上：

```env
APP_LANGSMITH_ENABLED=true
APP_LANGSMITH_PROJECT_RAG=ai-center-rag-dev
APP_LANGSMITH_PROJECT_INGEST=ai-center-ingest-dev
APP_LANGSMITH_PROJECT_EVAL=ai-center-eval-dev
APP_LANGSMITH_SAMPLE_RATE=1.0
APP_LANGSMITH_MAX_TEXT_CHARS=4000
APP_LANGSMITH_CAPTURE_RETRIEVED_TEXT=true
APP_LANGSMITH_CAPTURE_PROMPTS=true
APP_LANGSMITH_REDACT_PII=false
APP_LANGSMITH_OTEL_ENABLED=false
APP_LANGSMITH_OTEL_ONLY=false
```

### 7.3 配置原则

- `LANGSMITH_*` 保持兼容官方 SDK。
- `APP_LANGSMITH_*` 只表达本仓库自己的运行策略。
- tracing 是否真正开启，取决于：
  - 官方 `LANGSMITH_TRACING`
  - 应用内 `APP_LANGSMITH_ENABLED`
- project 不建议只用一个默认值，至少拆分为：
  - `RAG tracing`
  - `Ingest tracing`
  - `Offline eval`

---

## 8. 项目与会话设计

### 8.1 Project 规划

推荐 project 规划如下：

```text
ai-center-rag-dev
ai-center-rag-test
ai-center-rag-prod

ai-center-ingest-dev
ai-center-ingest-test
ai-center-ingest-prod
```

原因：

- RAG 与 ingest 的链路特征不同
- ingest traces 不适合与问答 traces 混在同一监控面板里
- 在线 evaluator 主要作用于 RAG 项目
- 告警和 dashboard 可以按项目隔离配置

### 8.2 Thread / Session 规划

LangSmith 官方支持通过 `session_id`、`thread_id`、`conversation_id` 之类的 metadata 键把多个 traces 归为同一线程。

因此建议：

- 单轮 `smoke` 和批任务：不强制线程化
- 多轮聊天问答：优先使用 `conversation_id`
- 如果当前请求对象里还没有 `conversation_id`，则先从 `request.metadata` 中读取

V1 建议规则：

```text
conversation_id 优先
否则 metadata.session_id
否则不建线程，只保留单 trace
```

---

## 9. Tracing 设计

### 9.1 推荐接入方式

V1 推荐优先使用 **LangSmith SDK 直接打点**，即：

- `@traceable`
- `trace` context manager
- `tracing_context`
- `Client.flush()`

不推荐 V1 先用 `RunTree` 手工拼装整棵树，也不推荐一开始就强上 OTEL。

原因：

- `RunTree` 手工传播上下文更容易出错
- OTEL 需要新增 exporter / collector / attribute mapping 约束
- 当前代码是单体进程内服务调用，SDK 直接打点已经足够

### 9.2 根链路设计

#### 9.2.1 RAG 问答链路

根 run：

```text
rag.answer
```

推荐 run tree：

```text
rag.answer (chain)
├── retrieval.retrieve (retriever)
│   ├── embedding.query (embedding)
│   └── vector_store.query_vectors (tool)
└── llm.invoke_chat (llm)
```

#### 9.2.2 知识入库链路

根 run：

```text
knowledge.ingest
```

推荐 run tree：

```text
knowledge.ingest (chain)
├── document.parse_and_chunk (chain)
├── embedding.index (embedding)
├── vector_store.ensure_collection (tool)
└── vector_store.upsert_records (tool)
```

### 9.3 各服务落位建议

优先接入这些现有方法：

- `SimpleRAGService.answer`
- `KnowledgeIndexService.ingest_source`
- `KnowledgeIndexService.ingest_raw_text`
- `KnowledgeIndexService.delete_document`
- `RetrieverService.retrieve`
- `EmbeddingGatewayService.embed`
- `VectorStoreService.ensure_collection`
- `VectorStoreService.upsert_records`
- `VectorStoreService.query_vectors`
- `VectorStoreService.delete_records`
- `GatewayService.invoke_chat`

### 9.4 建议的 metadata

每个 root trace 至少带：

- `tenant_id`
- `app_id`
- `knowledge_base_id`
- `index_name`
- `index_version`
- `scene`
- `env`
- `git_sha`
- `rag_trace_id` 或 `ingest_trace_id`

RAG 相关子 run 建议补充：

- `document_ids`
- `filter_keys`
- `top_k`
- `score_threshold`
- `retrieved_chunk_ids`
- `retrieved_document_ids`
- `retrieved_scores`
- `query_logical_model`
- `llm_logical_model`
- `final_channel`
- `final_provider`
- `final_model`
- `fallback_count`

### 9.5 建议的 tags

推荐 tags：

- `env:dev`
- `pipeline:rag`
- `pipeline:ingest`
- `provider:qdrant`
- `provider:litellm_proxy`
- `scene:knowledge_qa`
- `scene:knowledge_index`

### 9.6 输入输出裁剪原则

不要把 trace 当作原始数据仓库。

V1 建议：

- 不上传二进制文件内容
- 不上传 base64 原文
- 对 chunk 文本和 prompt 做截断
- 默认保留检索文本，但限制长度
- API key、Authorization、Cookie 等敏感字段必须清洗
- 如果后续有强合规要求，允许在生产关闭 `capture_prompts`

### 9.7 与现有 trace_id 的关系

当前业务侧已有 `trace_id`，例如：

- `RAGAskResult.trace_id`
- `RetrievalResult.trace_id`
- `LLMInvokeResult.trace_id`

这些字段**不要立即废弃**。

建议策略：

- 业务侧 trace_id 继续保留，作为应用内 trace id
- LangSmith 使用自己的 run / trace 标识
- 应用内 trace_id 放入 LangSmith metadata，便于双向排查

这样可以避免：

- API 返回结构突变
- 测试用例大面积重写
- 内部排障链路断裂

---

## 10. 评测设计

### 10.1 评测目标

LangSmith 评测层需要覆盖三类问题：

1. 检索到了没有
2. 回答对不对
3. 回答是否基于检索结果

### 10.2 离线评测数据集设计

建议首先建立 3 组数据集：

1. `rag_qa_regression`
2. `retrieval_regression`
3. `rag_badcases_from_prod`

每条样本建议包含：

```json
{
  "inputs": {
    "tenant_id": "demo-tenant",
    "app_id": "demo-app",
    "knowledge_base_id": "kb-demo",
    "question": "这份文件主要讲了什么？",
    "document_ids": ["doc-001"]
  },
  "reference_outputs": {
    "expected_answer": "节假日机房安全巡检工作部署",
    "expected_chunk_ids": ["chunk-1", "chunk-2"]
  },
  "metadata": {
    "split": "regression",
    "language": "zh",
    "doc_type": "docx",
    "difficulty": "easy"
  }
}
```

### 10.3 离线 evaluator 设计

V1 建议优先落这 4 个 evaluator：

1. `retrieval_hit_rate`
2. `citation_accuracy`
3. `answer_correctness`
4. `groundedness`

说明：

- `retrieval_hit_rate`
  - 判断召回结果是否包含目标 chunk / document
  - 更适合 code evaluator
- `citation_accuracy`
  - 判断返回引用是否与命中结果一致
- `answer_correctness`
  - 判断最终答案是否覆盖参考答案核心事实
- `groundedness`
  - 判断答案是否可由召回上下文支持

### 10.4 在线 evaluator 设计

生产 tracing 项目建议启用以下在线 evaluator：

1. `online_groundedness`
2. `online_no_answer_policy`
3. `online_citation_presence`
4. `online_output_structure`

说明：

- `online_groundedness`
  - 用于识别“检索到了，但答案编造了”的问题
- `online_no_answer_policy`
  - 当 context 为空时，答案是否遵守“资料不足则明确说明”的规则
- `online_citation_presence`
  - 返回答案时是否携带引用
- `online_output_structure`
  - 对结构化输出或 JSON 输出做格式检查

在线 evaluator 建议先做小流量采样，不建议默认 100% 全量。

### 10.5 评测与测试的关系

需要明确：

- 单元测试解决“代码是否按预期执行”
- 评测解决“模型与 RAG 效果是否达标”

二者不是替代关系。

V1 建议：

- 单测继续保留
- RAG regression 改动前后都跑离线评测
- 线上 badcase 进入 annotation queue 后，再回流到离线数据集

---

## 11. 人工反馈与标注设计

LangSmith 支持对根 trace 和中间 run 做反馈。

这对当前仓库特别有价值，因为 RAG 问题不总是 LLM 问题，也可能是 retrieval 问题。

因此建议反馈拆两层：

### 11.1 根 trace 反馈

绑定到 `rag.answer`：

- `user_helpful`
- `answer_correct`
- `answer_complete`

### 11.2 中间 run 反馈

绑定到 `retrieval.retrieve`：

- `retrieval_relevant`
- `retrieval_missing_key_chunk`
- `retrieval_wrong_document`

绑定到 `llm.invoke_chat`：

- `llm_grounded`
- `llm_hallucination`
- `llm_style_issue`

### 11.3 annotation queue 用法

建议把以下 traces 自动送入 annotation queue：

- 在线 evaluator 低分
- 用户点踩
- context 为空但模型仍给出肯定答案
- citation 缺失

这些样本后续可以：

- 做人工复核
- 转成数据集样本
- 用于回归评测

---

## 12. Deployment 设计

### 12.1 需要先澄清的一点

接入 LangSmith 的 **observability / evaluation**，并不要求当前应用必须部署到 LangSmith。

当前仓库完全可以继续保持：

- 自己的 Python 服务
- 自己的 FastAPI 接口
- 自己的脚本和任务编排
- 自己的 Docker / K8s 部署

LangSmith 先作为：

- tracing 平台
- evaluation 平台
- feedback 平台
- monitoring / alerting 平台

### 12.2 Deployment 的三个层次

#### 方案 A：只接 LangSmith Cloud 观测评测

适合当前阶段。

特点：

- 实现成本最低
- 无需改造现有服务部署方式
- 先解决“看得见”和“能评测”

#### 方案 B：自托管 LangSmith 观测评测

适合有合规、内网、数据驻留要求时使用。

LangSmith 官方支持自托管 “Observability & Evaluation” 模式，不要求同时启用 agent deployment。

#### 方案 C：自托管 LangSmith + Deployment

这是更重的方案。

适合：

- 希望把 agent / graph 的部署管理也统一纳入 LangSmith
- 需要控制平面 + 数据平面
- 有独立 K8s 和平台团队

对当前仓库来说，这不是第一阶段必须项。

### 12.3 当前推荐结论

当前仓库推荐顺序：

1. 先接 LangSmith Cloud tracing + evaluation
2. 再决定是否需要 self-hosted observability/evaluation
3. 最后才评估是否要引入 LangSmith deployment

---

## 13. OpenTelemetry 扩展位

### 13.1 为什么先不把 OTEL 作为默认方案

当前仓库还没有统一 OTEL 基础设施。

如果一开始就走 OTEL，需要同步解决：

- tracer provider 初始化
- exporter 配置
- span attribute 规范
- trace context 传播
- 多后端采集策略

这会明显扩大第一阶段接入范围。

### 13.2 什么时候适合引入 OTEL

当出现以下任一情况时，可以把第二阶段升级为 OTEL：

- 需要把 tracing 同时送到多个后端
- 需要跨进程 / 跨服务分布式追踪
- 需要统一接入现有基础观测平台
- 需要用 OTEL 统一 AI 与非 AI 服务链路

### 13.3 OTEL 接入时的关键属性

如果未来切到 OTEL，LangSmith 官方支持将 OTEL 属性映射为 LangSmith 字段。

对当前仓库最重要的是：

- `langsmith.trace.name`
- `langsmith.span.kind`
- `langsmith.trace.session_id`
- `langsmith.metadata.*`
- `retrieval.documents.{n}.document.content`
- `retrieval.documents.{n}.document.metadata`

用于评测实验时，还需要：

- `langsmith.reference_example_id`

---

## 14. 推荐落地步骤

### 14.1 第一阶段：Tracing 打通

- 在 `app/core/config.py` 中新增 LangSmith 配置类
- 在 `app/observability/tracing/` 中实现 `langsmith_tracer.py`
- 为 `SimpleRAGService.answer` 增加 root trace
- 为 `RetrieverService.retrieve`、`EmbeddingGatewayService.embed`、`VectorStoreService.*`、`GatewayService.invoke_chat` 增加子 spans
- 为 `KnowledgeIndexService.ingest_*` 增加入库 root trace
- 为 `scripts/smoke_rag.py` 增加 `flush()`

第一阶段目标不是“看所有细节”，而是先在 LangSmith UI 中看到完整 run tree。

### 14.2 第二阶段：离线评测

- 在 `app/observability/evals/` 中增加 dataset / evaluator 封装
- 新增 `scripts/eval_rag_langsmith.py`
- 建立第一批 regression dataset
- 接入 4 个基础 evaluator
- 在 CI 或人工发布前执行离线评测

### 14.3 第三阶段：在线评测与反馈

- 为生产 tracing project 配置在线 evaluator
- 配置 annotation queue
- 对用户反馈与低分 traces 建立回流机制
- 建立 dashboard 和 alert

### 14.4 第四阶段：OTEL / Self-hosted / Deployment

- 根据合规和平台要求决定是否引入 OTEL
- 根据数据驻留要求决定是否自托管 LangSmith
- 根据 agent deployment 需求决定是否启用 LangSmith Deployment

---

## 15. 验收标准

### 15.1 观测验收

- 从 `smoke_rag.py` 触发一次问答，可以在 LangSmith 中看到完整 trace
- trace 中可见 `retrieval.retrieve`、`vector_store.query_vectors`、`llm.invoke_chat`
- trace 可按 `tenant_id/app_id/knowledge_base_id` 过滤
- trace 可按 `scene/env/pipeline` 过滤
- 根 trace 与中间 spans 可以看到 latency、状态、模型、provider

### 15.2 评测验收

- 能创建 LangSmith dataset
- 能运行至少一组离线 experiment
- 能看到 evaluator 分数
- 能对两个实验结果进行对比
- 能把线上坏样本回流到 dataset

### 15.3 反馈验收

- 能对 `rag.answer` 根 trace 添加人工反馈
- 能对 `retrieval.retrieve` 或 `llm.invoke_chat` 中间 run 添加反馈
- annotation queue 能收集失败样本

### 15.4 运维验收

- 能在 project dashboard 上看到 trace 数、错误率、延迟、token/cost
- 能配置至少一个 latency 或 error alert
- 批任务和短生命周期脚本退出前能正确 `flush()`

---

## 16. 风险与约束

### 16.1 数据暴露风险

LangSmith tracing 会把输入输出带到平台侧。

因此必须明确：

- 哪些字段允许上报
- 哪些字段必须脱敏
- 哪些环境允许保留完整 prompt / retrieved text

### 16.2 trace 体积风险

如果把全文 chunk、大量 metadata、完整 prompt 全量写入 trace，会带来：

- 体积膨胀
- 查询变慢
- 成本上升

因此必须引入截断和裁剪策略。

### 16.3 双重打点风险

如果未来同时混用：

- LangSmith SDK 手工打点
- OTEL 自动打点

而又没有统一边界，容易产生重复 spans。

因此必须坚持：

- V1 以 SDK 为主
- V2 若引入 OTEL，明确哪些路径禁用 SDK 重复埋点

### 16.4 生命周期风险

LangSmith SDK 默认后台线程异步上报。

对短生命周期脚本和批任务，必须在退出前 `flush()`，否则 traces 可能丢失。

---

## 17. 最终结论

当前仓库接入 LangSmith 的正确顺序，不是先追求“大而全的 agent 平台化”，而是先解决两个最现实的问题：

1. RAG 内部到底怎么走
2. RAG 效果到底好不好

因此本仓库的最优路线是：

```text
第一步：LangSmith SDK 直连 tracing
第二步：离线评测数据集与 evaluator
第三步：在线评测、人工反馈、dashboard、alert
第四步：按需升级到 OTEL / self-hosted / deployment
```

对当前 `ai-center` 来说，LangSmith 最先承担的角色应该是：

- RAG 观测平台
- RAG 评测平台
- RAG 反馈闭环平台

而不是第一天就替代现有应用部署方式。

---

## 18. 官方参考

以下为本方案设计时参考的 LangSmith 官方文档：

- LangSmith Observability: [https://docs.langchain.com/langsmith/observability](https://docs.langchain.com/langsmith/observability)
- Observability concepts: [https://docs.langchain.com/langsmith/observability-concepts](https://docs.langchain.com/langsmith/observability-concepts)
- Custom instrumentation: [https://docs.langchain.com/langsmith/annotate-code](https://docs.langchain.com/langsmith/annotate-code)
- Trace without setting environment variables: [https://docs.langchain.com/langsmith/trace-without-env-vars](https://docs.langchain.com/langsmith/trace-without-env-vars)
- LangSmith Evaluation: [https://docs.langchain.com/langsmith/evaluation](https://docs.langchain.com/langsmith/evaluation)
- Evaluation concepts: [https://docs.langchain.com/langsmith/evaluation-concepts](https://docs.langchain.com/langsmith/evaluation-concepts)
- Evaluation quickstart: [https://docs.langchain.com/langsmith/evaluation-quickstart](https://docs.langchain.com/langsmith/evaluation-quickstart)
- Online evaluations: [https://docs.langchain.com/langsmith/online-evaluations](https://docs.langchain.com/langsmith/online-evaluations)
- Online code evaluators: [https://docs.langchain.com/langsmith/online-evaluations-code](https://docs.langchain.com/langsmith/online-evaluations-code)
- Annotate traces and runs inline: [https://docs.langchain.com/langsmith/annotate-traces-inline](https://docs.langchain.com/langsmith/annotate-traces-inline)
- Trace with OpenTelemetry: [https://docs.langchain.com/langsmith/trace-with-opentelemetry](https://docs.langchain.com/langsmith/trace-with-opentelemetry)
- Evaluate with OpenTelemetry: [https://docs.langchain.com/langsmith/evaluate-with-opentelemetry](https://docs.langchain.com/langsmith/evaluate-with-opentelemetry)
- Monitor projects with dashboards: [https://docs.langchain.com/langsmith/dashboards](https://docs.langchain.com/langsmith/dashboards)
- Alerts in LangSmith: [https://docs.langchain.com/langsmith/alerts](https://docs.langchain.com/langsmith/alerts)
- Self-hosted LangSmith: [https://docs.langchain.com/langsmith/self-hosted](https://docs.langchain.com/langsmith/self-hosted)
- Interact with your self-hosted instance: [https://docs.langchain.com/langsmith/self-host-usage](https://docs.langchain.com/langsmith/self-host-usage)
