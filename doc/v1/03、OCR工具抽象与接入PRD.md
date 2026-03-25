# OCR 工具抽象与接入 PRD（V1）

## 1. 文档目的

本文档用于明确 AI 中台在 V1 阶段如何落地 OCR 能力，并把以下内容写清楚：

- OCR 在当前架构中的定位
- 为什么 OCR 应落在 `app/runtime/tools/`
- 为什么具体厂商实现应落在 `app/integrations/`
- OCR 如何被知识库模块复用
- OCR 如何被 Agent / 工作流复用
- 接口约定、配置要求、数据模型和验收标准

本文档解决的问题不是“要不要做 OCR”，而是“在当前项目架构下，OCR 应该如何以可复用、可扩展、可治理的方式接入”。

---

## 2. 背景

根据当前架构文档，`模型与工具抽象层` 包含：

- Embedding 统一适配
- Reranker
- Structured Output
- Tool Calling
- Tools：SQL / Python / 搜索 / OCR / 邮件 / 日历 / HTTP API / MCP / 内部系统

对应目录设计中：

- `app/runtime/tools/`
  用于 Tool Calling 与工具注册
- `app/integrations/`
  用于第三方系统与外部能力接入

因此，OCR 不应直接散落在知识库模块、Agent 模块或某个业务接口里单独实现，而应被沉淀为一项“统一工具能力”。

如果不这么做，后续会出现以下问题：

- 知识库上传链路自己接一套 OCR
- Agent 自己再接一套 OCR
- 不同模块对同一 OCR 厂商的请求、错误处理、超时、结果格式各自维护
- 后续替换 OCR 厂商时影响面过大
- 无法统一做限流、审计、观测和成本统计

因此，V1 应先建立：

- 统一 OCR 工具抽象
- 统一 OCR provider adapter 规范
- 统一 OCR 结果结构
- 统一的知识库 / Agent 复用方式

---

## 3. V1 目标

### 3.1 产品目标

- 提供统一的 OCR 内部调用接口
- 支持图片与 PDF 的基础 OCR 识别
- 支持接入至少一种 OCR provider
- 支持后续平滑扩展多 provider
- 支持知识库上传流程复用 OCR
- 支持 Agent / 工作流通过工具调用复用 OCR
- 支持基础 trace、耗时、状态、错误记录

### 3.2 业务价值

- 避免 OCR 能力在多个模块重复建设
- 降低未来更换 OCR 厂商或增加自建 OCR 的成本
- 让知识库和 Agent 共用一套能力底座
- 为后续文档解析、表格提取、版面分析、多模态流程提供基础

---

## 4. V1 非目标

以下内容不属于本次 V1 必做范围：

- 不做完整的 OCR 管理后台 UI
- 不做多 OCR provider 的自动路由
- 不做复杂版面分析、表格结构化、公式识别的完整产品化
- 不做图片理解与 OCR 深度融合编排
- 不做通用文件解析平台的完整闭环
- 不做精确到财务级别的 OCR 成本结算系统
- 不做大规模异步任务调度平台

说明：

V1 只先把“统一 OCR 工具抽象 + provider adapter + 知识库/Agent 复用”这条主链路跑通。

---

## 5. 术语说明

### 5.1 OCR Tool

运行时对上层暴露的统一 OCR 能力，不关心底层是阿里云、百度云、PaddleOCR 还是自建服务。

### 5.2 OCR Provider Adapter

对接具体 OCR 服务商或内部 OCR 服务的适配器，负责协议差异、认证差异、响应结构差异的封装。

### 5.3 Document Asset

待识别的文档输入对象，可以是：

- 本地文件路径
- 对象存储 URL
- Base64 内容
- 业务系统附件引用

### 5.4 OCR Result

统一的 OCR 识别结果对象，面向知识库、Agent 和其他业务模块消费。

---

## 6. 方案结论

V1 采用以下统一方案：

1. OCR 统一抽象放在 `app/runtime/tools/`
2. 具体 OCR provider 对接放在 `app/integrations/ocr_providers/`
3. 知识库模块不直接依赖某个 OCR SDK，只依赖 OCR Tool
4. Agent / 工作流不直接依赖某个 OCR SDK，只依赖 OCR Tool
5. OCR Tool 输出统一结果结构，不向上层暴露 provider 原始响应
6. OCR provider 的切换通过配置和 adapter 完成，而不是修改业务模块

换句话说：

- `runtime/tools` 管“统一能力入口和工具治理”
- `integrations/ocr_providers` 管“厂商对接细节”
- `knowledge_center` 和 `agent_center` 管“业务流程如何使用 OCR”

---

## 7. 用户与使用场景

### 7.1 知识库场景

- 作为知识库模块，我希望在文档上传时先做 OCR，把扫描件中的文字提取出来，再进入切分和索引流程
- 作为知识库模块，我希望不关心底层 OCR 厂商是谁，只拿统一结构的文本结果
- 作为知识库模块，我希望未来可以替换 OCR provider，而不改上传主流程

### 7.2 Agent 场景

- 作为 Agent，我希望在用户上传图片、截图、扫描件时，能够把 OCR 当成一个工具调用
- 作为 Agent，我希望 OCR 的调用方式和其他工具一致，便于进入后续工具编排体系
- 作为 Agent，我希望拿到统一结构结果，再决定是总结、问答还是后续工具调用

### 7.3 平台治理场景

- 作为平台，我希望记录 OCR 请求的 provider、耗时、状态和错误
- 作为平台，我希望对 OCR 能力做权限控制和后续扩展
- 作为平台，我希望后续能接多 provider 或自建 OCR 服务而不打破上层接口

---

## 8. 范围定义

### 8.1 V1 必做范围

- 统一 OCR 工具接口
- OCR 工具注册与执行入口
- 至少一种 provider adapter
- 图片 OCR 调用链路
- PDF OCR 基础调用链路
- 统一 OCR 结果结构
- 知识库上传流程对 OCR 的复用接口
- Agent / 工作流对 OCR 的复用接口
- 基础错误归一和观测埋点

### 8.2 V1 预留但不强制实现

- 多 provider 路由
- provider fallback
- OCR 结果缓存
- 表格结构化抽取
- 版面坐标增强分析
- 批量异步 OCR
- OCR 质量评分与评测体系

---

## 9. 职责边界

### 9.1 `app/runtime/tools/`

职责：

- 定义统一 OCR Tool 接口
- 定义 OCR 请求和响应模型
- 定义工具注册与执行机制
- 向 Agent / 工作流 / 知识库暴露统一调用入口
- 做工具级参数校验、错误归一和结果标准化

非职责：

- 不直接耦合具体 OCR provider SDK
- 不直接写知识库业务逻辑
- 不直接写 Agent 业务编排逻辑

### 9.2 `app/integrations/ocr_providers/`

职责：

- 对接具体 OCR provider
- 封装认证方式、HTTP 协议、请求结构、响应结构差异
- 把 provider 原始结果映射为统一 OCR 中间结果

非职责：

- 不决定业务上什么时候做 OCR
- 不承担知识库切片、索引、问答逻辑
- 不承担 Agent 的工具调度策略

### 9.3 `app/modules/knowledge_center/`

职责：

- 在上传、预处理、切分前决定是否调用 OCR
- 消费统一 OCR 结果
- 把 OCR 文本送入后续 chunking / indexing 流程

非职责：

- 不直接依赖某个 OCR provider
- 不自行维护一套 OCR 返回结构

### 9.4 `app/modules/agent_center/` 与 `app/runtime/workflows/`

职责：

- 在需要时触发 OCR Tool
- 接收统一 OCR 结果并进入后续推理/工具链

非职责：

- 不直接依赖某个 OCR provider SDK
- 不在 Agent 节点里硬编码 OCR 厂商实现

---

## 10. 推荐目录落位

建议后续按以下目录落位：

```text
app/
├─ runtime/
│  ├─ tools/
│  │  ├─ base.py
│  │  ├─ registry.py
│  │  ├─ executor.py
│  │  ├─ schemas.py
│  │  └─ ocr_tool.py
│  ├─ workflows/
│  └─ retrieval/
├─ integrations/
│  ├─ ocr_providers/
│  │  ├─ base.py
│  │  ├─ aliyun_ocr_adapter.py
│  │  ├─ paddle_ocr_adapter.py
│  │  └─ internal_ocr_adapter.py
├─ modules/
│  ├─ knowledge_center/
│  │  ├─ services/
│  │  │  └─ document_ocr_service.py
│  ├─ agent_center/
│  └─ ...
```

说明：

- `runtime/tools/ocr_tool.py` 是对内统一入口
- `integrations/ocr_providers/*` 是对外部 OCR 服务的适配层
- `knowledge_center` 只依赖 OCR Tool，不碰 provider adapter
- `agent_center` 只依赖 OCR Tool，不碰 provider adapter

---

## 11. 核心产品规则

### 11.1 单一工具抽象规则

上层模块只允许使用统一 OCR Tool，不允许直接依赖具体 OCR 厂商 SDK。

例如上层允许写：

- `ocr_tool.execute(...)`
- `tool_name = "ocr_extract_text"`

不允许在业务模块里直接写：

- `AliyunOCRClient(...)`
- `PaddleOCR(...)`
- 某 provider 的原始 HTTP 调用

### 11.2 单一结果结构规则

无论底层 provider 是谁，上层消费的 OCR 结果结构必须一致。

### 11.3 工具层与适配层分离规则

工具层只关心：

- 输入参数
- 执行语义
- 统一返回
- 工具级治理

适配层只关心：

- 请求怎么发
- provider 怎么鉴权
- provider 的原始结果怎么解析

### 11.4 上层复用规则

知识库、Agent、工作流统一复用 OCR Tool，而不是各自接入 OCR。

---

## 12. 功能需求

### 12.1 统一 OCR Tool 入口

系统必须提供统一 OCR 工具调用入口，例如：

```python
execute_ocr(request: OCRToolRequest) -> OCRToolResult
```

或：

```python
tool_executor.execute("ocr_extract_text", request)
```

该入口对上层屏蔽以下差异：

- provider 协议差异
- 鉴权差异
- 图片与 PDF 接口差异
- 响应字段差异
- 错误结构差异

### 12.2 OCR 输入支持

V1 至少支持：

- 图片文件路径
- PDF 文件路径
- URL 输入

可预留但不强制：

- Base64 输入
- 对象存储引用
- 多页批量文件

### 12.3 OCR 输出能力

V1 至少支持输出：

- 全量纯文本
- 页级文本
- 行级文本列表
- provider 信息
- 文件元信息

可预留但不强制：

- 坐标框
- 表格结构
- 置信度
- 段落结构

### 12.4 知识库复用能力

知识库模块必须支持：

1. 文档上传后判断是否需要 OCR
2. 调用 OCR Tool
3. 获取统一文本结果
4. 将识别结果送入后续切分与索引流程

### 12.5 Agent / 工作流复用能力

Agent / 工作流必须支持：

1. 将 OCR 注册为一个工具
2. 在需要时触发 OCR Tool
3. 获取统一 OCR 结果
4. 将结果继续送给 LLM 或其他工具

---

## 13. 接口约定

### 13.1 OCR Tool 请求对象

建议定义如下内部请求对象：

```python
from pydantic import BaseModel, Field

class OCRToolRequest(BaseModel):
    tenant_id: str
    app_id: str
    scene: str
    source_type: str  # file_path / url / base64
    source_value: str
    file_type: str | None = None  # image / pdf
    language_hints: list[str] = Field(default_factory=list)
    enable_layout: bool = False
    page_range: list[int] | None = None
    metadata: dict = Field(default_factory=dict)
```

### 13.2 OCR Tool 响应对象

建议定义如下统一响应对象：

```python
from pydantic import BaseModel, Field

class OCRLine(BaseModel):
    text: str
    page_no: int | None = None
    bbox: list[float] | None = None
    confidence: float | None = None

class OCRPage(BaseModel):
    page_no: int
    text: str
    lines: list[OCRLine] = Field(default_factory=list)

class OCRToolResult(BaseModel):
    trace_id: str
    provider: str
    model: str | None = None
    source_type: str
    source_value: str
    text: str
    pages: list[OCRPage] = Field(default_factory=list)
    usage: dict = Field(default_factory=dict)
    latency_ms: int
    raw_response: dict | None = None
```

说明：

- `text` 是知识库最常用的统一主字段
- `pages` 供分页场景和后续扩展使用
- `raw_response` 仅用于调试和审计，不建议业务直接依赖

### 13.3 OCR Provider Adapter 协议

建议定义统一适配器接口：

```python
class BaseOCRProviderAdapter(ABC):
    @abstractmethod
    def extract_text(self, request: OCRToolRequest) -> OCRToolResult:
        raise NotImplementedError
```

后续不同 provider 都实现这一个协议。

---

## 14. 运行流程

### 14.1 知识库上传链路

标准流程如下：

```text
用户上传文档
-> knowledge_center 判断文件是否需要 OCR
-> 调用 OCR Tool
-> OCR Tool 选择 provider adapter
-> provider adapter 调用外部 OCR 服务
-> OCR Tool 统一结果结构
-> knowledge_center 获取 text/pages
-> 后续 chunking / indexing
```

### 14.2 Agent 工具调用链路

标准流程如下：

```text
用户上传图片或 PDF
-> Agent / workflow 判断需要 OCR
-> ToolExecutor 执行 ocr_extract_text
-> OCR Tool 选择 provider adapter
-> provider adapter 调用 OCR 服务
-> OCR Tool 返回统一结构
-> Agent 将 OCR 文本继续送入 LLM 推理
```

### 14.3 后续多 provider 扩展链路

未来若支持多 provider，可演进为：

```text
OCR Tool
-> provider resolver / policy
-> aliyun_ocr_adapter 或 paddle_ocr_adapter 或 internal_ocr_adapter
```

但 V1 不强制实现复杂路由。

---

## 15. 配置设计

### 15.1 应用侧环境变量建议

建议在 `.env.example` 中补充：

```env
# OCR runtime
OCR_DEFAULT_PROVIDER=aliyun_ocr
OCR_TIMEOUT_MS=60000
OCR_ENABLE_LAYOUT=false

# Aliyun OCR
ALIYUN_OCR_BASE_URL=
ALIYUN_OCR_API_KEY=
ALIYUN_OCR_APP_CODE=
```

如果后续接自建 OCR，可继续增加：

```env
INTERNAL_OCR_BASE_URL=
INTERNAL_OCR_API_KEY=
```

### 15.2 配置原则

- OCR 默认 provider 通过配置指定
- 上层业务不直接保存和使用 provider 级别凭据
- provider 凭据统一由配置层管理

---

## 16. 错误模型

系统内部建议至少归一以下错误类型：

- `ocr_configuration_error`
- `ocr_validation_error`
- `ocr_authentication_error`
- `ocr_permission_error`
- `ocr_timeout_error`
- `ocr_provider_unavailable`
- `ocr_bad_response_error`
- `ocr_unsupported_file_type`
- `ocr_unknown_error`

目标是让上层模块不直接感知 provider 的原始错误格式。

---

## 17. 观测与审计

每次 OCR 调用至少记录以下字段：

- `trace_id`
- `tenant_id`
- `app_id`
- `scene`
- `tool_name`
- `provider`
- `source_type`
- `file_type`
- `latency_ms`
- `status`
- `error_code`
- `page_count`
- `metadata`

后续可扩展：

- 计费信息
- provider request id
- OCR 结果字数
- 缓存命中情况

---

## 18. 模块实现建议

### 18.1 `runtime/tools` 核心组件

建议至少包含：

- `schemas.py`
  定义 OCRToolRequest / OCRToolResult
- `base.py`
  定义 Tool 抽象
- `registry.py`
  负责工具注册
- `executor.py`
  负责统一执行
- `ocr_tool.py`
  OCR 工具入口

### 18.2 `integrations/ocr_providers` 核心组件

建议至少包含：

- `base.py`
  定义 OCR provider adapter 抽象
- `aliyun_ocr_adapter.py`
  对接阿里 OCR
- `internal_ocr_adapter.py`
  预留自建 OCR 服务适配

### 18.3 `knowledge_center` 复用点

建议新增一个服务层：

```text
app/modules/knowledge_center/services/document_ocr_service.py
```

职责：

- 判断哪些文件需要 OCR
- 调用 OCR Tool
- 返回适合 chunking 的纯文本结果

### 18.4 `agent_center` / `workflows` 复用点

建议在工具注册阶段把 OCR Tool 注册进去，使 Agent 可通过统一 ToolExecutor 调用。

---

## 19. 分阶段落地建议

### 19.1 第一阶段

- 定义 OCR Tool 请求/响应协议
- 定义 OCR provider adapter 基类
- 实现 1 个 provider adapter
- 打通常规图片 OCR
- 打通知识库上传场景

### 19.2 第二阶段

- 支持 PDF OCR
- 打通 Agent / workflow 工具调用场景
- 补充基础观测和错误归一

### 19.3 第三阶段

- 增加多 provider 支持
- 加入 provider fallback 或策略路由
- 支持表格、坐标、版面信息增强

---

## 20. 验收标准

### 20.1 功能验收

- 知识库上传扫描件时可通过 OCR 获取文本
- Agent 可通过统一工具调用 OCR
- 上层模块不直接依赖 OCR 厂商 SDK
- 更换 provider 时不需要修改知识库和 Agent 的核心业务代码

### 20.2 架构验收

- OCR 工具抽象落在 `app/runtime/tools/`
- OCR provider adapter 落在 `app/integrations/ocr_providers/`
- `knowledge_center` 和 `agent_center` 只依赖 OCR Tool，不依赖 provider adapter

### 20.3 数据验收

- OCR 结果统一输出 `text`
- 至少支持页级结果结构
- 错误可归一
- 调用过程可观测

---

## 21. 风险与约束

### 21.1 风险

- 如果知识库和 Agent 分别直接接 OCR，后续会形成重复实现
- 如果工具层直接耦合 provider SDK，后续替换 provider 成本会很高
- 如果 OCR 结果结构不统一，上层消费将持续分裂
- 如果 V1 过早引入复杂版面分析，会拉高落地复杂度

### 21.2 约束

- V1 必须优先保证边界清晰，而不是功能铺得过宽
- V1 必须先保证“统一抽象 + 单 provider 跑通”
- V1 必须先打通知识库和 Agent 两条主复用链路

---

## 22. 最终结论摘要

基于当前项目架构，OCR 的合理落位应当是：

- `app/runtime/tools/` 负责统一 OCR 工具抽象
- `app/integrations/ocr_providers/` 负责具体 OCR provider adapter
- `app/modules/knowledge_center/` 通过 OCR Tool 复用能力
- `app/modules/agent_center/` 与 `app/runtime/workflows/` 通过 OCR Tool 复用能力

这意味着 OCR 在本项目中不应被实现成某个业务模块的私有能力，而应被实现成“模型与工具抽象层”中的一项标准工具能力。
