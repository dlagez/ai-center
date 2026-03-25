# 文档解析模块 PRD（V1）

## 1. 文档目的

本文档用于明确 AI 中台在 V1 阶段如何建设统一的“文档解析模块”，并回答以下问题：

- 文档解析模块是否应该作为所有文件解析能力的统一入口
- OCR 是否应该下沉为文档解析模块中的一种解析策略
- PDF、Word、Excel、PPT、图片等文件是否应该统一走文档解析链路
- 文件 hash 判重、解析结果缓存、重复请求复用应该落在哪一层
- 知识库、Agent、工作流如何复用统一文档解析能力

本文档的结论不是“是否还需要 OCR”，而是“OCR 不应再作为孤立能力被单独治理，而应纳入统一文档解析模块，由模块统一完成文件识别、解析策略选择、缓存复用与结果输出”。

---

## 2. 背景

当前项目已经具备以下基础能力：

- `app/runtime/tools/` 中存在统一 OCR Tool 入口
- `app/integrations/ocr_providers/` 中存在 OCR provider adapter
- `knowledge_center` 和 `agent_center` 已经可以复用 OCR Tool

但当前 OCR 链路仍然存在明显不足：

- OCR Tool 每次请求都会直接调用 OCR provider
- 没有统一的文件身份标识
- 没有基于文件内容的 hash 判重
- 没有解析结果缓存
- 没有“同一文件已经解析过则直接返回”的能力
- PDF、Word、Excel、PPT、图片等文件尚未纳入统一解析入口

如果继续按“每种文件能力各自实现”的方式推进，后续会出现：

- OCR 单独一套入口
- Office 文档解析又一套入口
- 表格解析、附件预处理、文档清洗再一套入口
- 知识库和 Agent 分别处理重复文件与缓存逻辑
- 文件重复上传、重复解析、重复计费无法统一治理

因此，V1 需要建立一个统一的文档解析模块，作为“文件到标准解析结果”的唯一入口。

---

## 3. 方案结论

V1 采用以下统一方案：

1. 新建统一的文档解析模块，负责所有文档类输入的解析入口与编排
2. OCR 作为文档解析模块中的一种解析策略存在，不再由上层业务直接决定是否调用 OCR provider
3. PDF、图片、Word、Excel、PPT、TXT、Markdown、HTML、CSV 等文件统一进入文档解析模块
4. 文档解析模块基于文件内容 hash 建立统一身份，并负责判重与缓存复用
5. 文档解析模块统一输出标准化解析结果，不向上层暴露底层 provider 差异
6. 知识库、Agent、工作流均复用文档解析模块，而不是分别维护各自的文件解析逻辑

换句话说：

- Agent 层不负责判断文件是否已经 OCR 过
- 知识库层不负责维护文件解析缓存
- OCR provider adapter 不负责判重与结果治理
- 文档解析模块统一负责“识别文件 -> 选择解析策略 -> 查询缓存 -> 执行解析 -> 存储结果 -> 输出标准结果”

---

## 4. 产品目标

### 4.1 产品目标

- 提供统一的文档解析内部调用接口
- 支持常见文件类型的文本提取与结构化解析
- 支持基于文件 hash 的去重判定
- 支持解析结果缓存与重复请求复用
- 支持输出最小可用的原文定位信息，供后续 RAG 回溯原文使用
- 支持 OCR、Office 解析、纯文本提取等策略的统一编排
- 支持知识库、Agent、工作流复用统一解析结果
- 支持基础 trace、耗时、缓存命中、错误归一与观测

### 4.2 业务价值

- 降低重复解析带来的成本与时延
- 避免相同文件在不同模块中被重复处理
- 为后续文档清洗、Chunking、索引构建、结构化抽取打好统一入口
- 为后续支持更多文件类型与更多解析引擎预留扩展点
- 为缓存治理、版本升级、失效重建提供统一控制面

---

## 5. 非目标

以下内容不属于本次 V1 必做范围：

- 不做完整的文档管理后台 UI
- 不做复杂版式分析产品化配置台
- 不做全文预览、在线编辑、批注协同
- 不做大规模离线批处理调度平台
- 不做完整的文档资产中心或文件生命周期治理系统
- 不做细粒度到财务级别的成本结算
- 不做所有复杂表格语义恢复
- 不做多版本文档比对与差异分析

V1 的重点是先把“统一解析入口 + hash 判重 + 结果缓存 + 基础策略路由”这一条主链路跑通。

---

## 6. 术语说明

### 6.1 Source Asset

待解析的原始文件输入。可以是：

- 本地文件路径
- URL
- Base64
- 对象存储引用

### 6.2 Document Parse Module

统一的文档解析模块，负责文件规范化、文件身份识别、策略选择、缓存复用、解析执行和结果输出。

### 6.3 Parse Strategy

具体的解析策略，例如：

- 文本层提取
- OCR 识别
- Word 文本提取
- Excel 表格提取
- PPT 文本提取
- HTML 清洗
- CSV 结构化读取

### 6.4 Parse Result

标准化的解析结果对象，供知识库、Agent、工作流等上层模块消费。

### 6.5 Parse Cache

基于文件身份与解析参数生成的缓存记录，用于复用已完成的解析结果。

---

## 7. 核心设计原则

### 7.1 单一入口原则

所有文档解析必须统一经过文档解析模块，不允许上层业务模块直接调用某个 OCR SDK、Office SDK 或第三方文件解析服务。

### 7.2 先判重后解析原则

任何文件在真正进入解析引擎之前，必须先建立文件身份并查询缓存。

### 7.3 先低成本解析后高成本解析原则

例如：

- PDF 先尝试文本层提取
- 若提取不到有效文本，再进入 OCR
- Office 文件优先走原生文本提取，不进入 OCR

### 7.4 结果标准化原则

无论底层是 OCR、Office 库、HTML parser 还是 CSV reader，上层都只消费统一结果结构。

### 7.5 可扩展策略原则

文档解析模块应该支持新增解析器，而不是把文件类型判断和解析逻辑写死在某个业务服务中。

### 7.6 缓存可治理原则

缓存命中与失效必须可观测、可配置、可回溯，不能做成不可控的内存黑盒。

---

## 8. 模块定位与职责边界

### 8.1 推荐模块落位

建议新增独立模块：

```text
app/
└── modules/
    └── document_center/
        ├── services/
        │   ├── document_parse_service.py
        │   ├── file_identity_service.py
        │   ├── parse_cache_service.py
        │   └── parser_router_service.py
        ├── parsers/
        │   ├── base.py
        │   ├── pdf_parser.py
        │   ├── image_parser.py
        │   ├── docx_parser.py
        │   ├── xlsx_parser.py
        │   ├── pptx_parser.py
        │   ├── text_parser.py
        │   └── html_parser.py
        └── repositories/
            └── parse_cache_repository.py
```

说明：

- `document_center` 负责统一文档解析能力
- `runtime/tools/ocr_tool.py` 后续应委托给 `document_center`
- `integrations/ocr_providers/` 仍只负责外部 OCR provider 对接

### 8.2 文档解析模块职责

- 接收统一文档解析请求
- 规范化文件输入
- 生成文件 hash 与文件身份
- 判断是否命中缓存
- 根据文件类型选择解析策略
- 在需要时调用 OCR 能力
- 对解析结果做标准化封装
- 持久化缓存记录与观测信息

### 8.3 非职责

- 不负责向量化、Chunking、索引构建
- 不负责 Agent 对话推理
- 不负责知识库召回逻辑
- 不负责文件上传存储本身
- 不直接承担业务审批、权限编排等上层流程

---

## 9. 上下游关系

### 9.1 上游调用方

- 知识库文档入库流程
- Agent 附件理解流程
- 工作流中的文件处理节点
- 内部系统的附件抽取能力

### 9.2 下游能力

- OCR provider
- PDF 文本提取引擎
- Office 文档解析引擎
- HTML / CSV / Markdown 解析器
- 文件元数据提取器

### 9.3 与 OCR Tool 的关系

文档解析模块建立后，OCR Tool 不应继续自己直接决定是否调用 OCR provider，而应调整为：

```text
OCR Tool
-> Document Parse Module
-> Parser Router
-> OCR Strategy / PDF Strategy / Office Strategy
```

即：

- OCR Tool 仍可保留为 Agent 工具入口
- 但实际执行应委托给统一文档解析模块
- OCR 只是一种解析策略，而不是平台唯一的文件处理入口

---

## 10. 支持范围

### 10.1 V1 必做文件类型

- PDF
- PNG / JPG / JPEG / BMP / TIFF / WEBP
- DOCX
- XLSX
- PPTX
- TXT
- Markdown
- HTML
- CSV

### 10.2 V1 可预留但不强制实现

- DOC
- XLS
- PPT
- EML
- EPUB
- ZIP 内部递归解析
- 多附件批量打包解析

### 10.3 文件类型与推荐策略

- PDF：优先文本层提取，失败后再 OCR
- 图片：直接 OCR
- DOCX：原生文本提取
- XLSX：按 sheet 提取单元格与文本
- PPTX：提取幻灯片文本与备注
- TXT / Markdown：直接读取
- HTML：清洗标签后提取正文
- CSV：按行列读取并标准化为文本与结构化表格

---

## 11. 用户与业务场景

### 11.1 知识库场景

- 作为知识库模块，我希望上传任意常见文档后都通过统一入口解析
- 我希望相同文件重复上传时直接复用解析结果
- 我希望 PDF 如果已有文本层，则不要再做 OCR
- 我希望上层拿到统一文本结果，再进入 Chunking 与索引流程

### 11.2 Agent 场景

- 作为 Agent，我希望处理用户上传的图片、PDF、Word、Excel 等附件时，不关心底层解析实现
- 我希望同一附件在同一会话或不同会话中被重复使用时，不重复解析
- 我希望统一拿到标准解析结果，再决定摘要、问答或继续调用其他工具

### 11.3 平台治理场景

- 作为平台，我希望知道哪些文件被重复解析
- 我希望知道缓存命中率、解析耗时、OCR 调用比例
- 我希望在解析器升级后能够控制缓存失效与重建

---

## 12. 核心功能需求

### 12.1 统一解析入口

系统必须提供统一的文档解析调用接口，例如：

```python
parse_document(request: DocumentParseRequest) -> DocumentParseResult
```

或：

```python
document_parse_service.parse(request)
```

上层模块不再分别调用 OCR、PDF 提取、Office 提取等多个入口。

### 12.2 文件身份识别

系统必须为每个待解析文件建立统一身份，至少包括：

- 文件内容 hash
- 文件大小
- 文件名
- MIME type 或扩展名
- 来源信息

其中，文件内容 hash 是判重主键的核心字段。

### 12.3 hash 判重

系统必须基于文件内容 hash 做重复文件识别。

判重目标包括：

- 相同文件重复上传
- 相同文件被知识库和 Agent 分别处理
- 相同文件在不同时间被重复请求解析

### 12.4 解析结果缓存

系统必须在解析前查询缓存，在解析后写入缓存。

缓存 key 不应只包含文件 hash，还必须包含影响解析结果的关键参数，例如：

- 文件 hash
- 解析模式
- 文件类型
- parser 版本
- OCR provider
- language hints
- enable layout
- page range

否则会出现“同一文件不同参数却错误复用结果”的问题。

### 12.5 策略路由

系统必须根据文件类型与文件内容特征选择解析策略。

例如：

- PDF 先做文本层检测
- 图片直接 OCR
- Office 文件直接走原生解析
- HTML 走内容清洗

### 12.6 OCR 降级与触发

OCR 不应默认对所有文件执行，只应在以下场景触发：

- 图片文件
- 无有效文本层的扫描版 PDF
- 特定业务显式要求 OCR

### 12.7 标准结果输出

系统必须输出统一结构，至少包含：

- 标准纯文本
- 页级或段级结果
- 表格/工作表等结构化片段
- 元数据
- 命中缓存信息
- 解析策略信息

### 12.8 位置信息最小要求

文档解析结果需要保留最小可用的位置信息，供后续 RAG 检索命中后定位到原文。

V1 当前只要求保留以下位置信息：

- PDF、图片、PPT、Word 等页式文档保留 `page_no`
- Excel / CSV 等表格类文档优先保留“第几行”，即 `row_index`

说明：

- 当前阶段不强制要求块级坐标、字符级 offset、段落锚点、单元格坐标等更细粒度位置模型
- 当前阶段的目标是先满足“检索后可大致回到原文页或原始行”的基础能力
- 更细的位置信息优化需求，单独沉淀在 `doc/v1/04、01文档解析位置信息需求优化.md`

### 12.9 并发防重

对于同一缓存 key 的并发请求，系统应避免同时触发多次解析。

V1 可以支持基础的“单 key 加锁 / 处理中状态”机制。

---

## 13. 数据模型建议

### 13.1 解析请求对象

```python
class DocumentParseRequest(BaseModel):
    tenant_id: str
    app_id: str
    scene: str
    source_type: str  # file_path / url / base64 / object_ref
    source_value: str
    file_name: str | None = None
    file_type: str | None = None
    parse_mode: str = "text"  # text / structured / preview
    provider: str | None = None
    language_hints: list[str] = Field(default_factory=list)
    enable_layout: bool | None = None
    page_range: list[int] | None = None
    metadata: dict = Field(default_factory=dict)
```

### 13.2 解析结果对象

```python
class DocumentParseResult(BaseModel):
    trace_id: str
    asset_hash: str
    parser_name: str
    parser_version: str
    source_type: str
    source_value: str
    file_type: str
    text: str
    pages: list[dict] = Field(default_factory=list)
    tables: list[dict] = Field(default_factory=list)
    locations: list[dict] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    cache_hit: bool
    latency_ms: int
    raw_response: dict | None = None
```

### 13.2.1 位置信息最小模型

V1 建议先采用最小位置信息模型：

```python
class DocumentLocation(BaseModel):
    page_no: int | None = None
    row_index: int | None = None
```

说明：

- 页式文档优先使用 `page_no`
- 表格类文档优先使用 `row_index`
- 暂不强制统一更细粒度的块坐标与字符区间
- 后续扩展需求见 `doc/v1/04、01文档解析位置信息需求优化.md`

### 13.3 缓存记录对象

建议至少包含：

- cache_key
- asset_hash
- parser_name
- parser_version
- parse_params_digest
- status
- result_payload
- created_at
- updated_at
- expire_at

---

## 14. 缓存设计

### 14.1 缓存 key 组成

建议：

```text
cache_key = hash(
    asset_hash
    + file_type
    + parse_mode
    + parser_name
    + parser_version
    + provider
    + language_hints
    + enable_layout
    + page_range
)
```

### 14.2 为什么不能只用文件 hash

因为同一个文件在以下情况下结果可能不同：

- 解析器版本升级
- OCR provider 切换
- page_range 不同
- 是否启用 layout 不同
- 结构化模式与纯文本模式不同

因此“文件 hash”用于识别同一文件，“cache key”用于识别同一解析任务。

### 14.3 缓存命中规则

- 完全命中 cache key，则直接返回缓存结果
- 仅命中文件 hash，但解析参数不同，则允许复用文件身份，不直接复用结果
- parser_version 变化时，旧缓存可保留但默认不命中新版本请求

### 14.4 缓存存储建议

V1 建议采用持久化缓存，而不是仅进程内内存缓存。

可选：

- 数据库表
- Redis + 数据库存档
- 对象存储保存大结果，数据库保存索引

### 14.5 失效策略

V1 至少支持：

- 基于 parser_version 的主动失效
- 基于 TTL 的被动失效
- 基于错误状态的失败结果不缓存或短 TTL 缓存

---

## 15. 标准执行流程

### 15.1 主流程

```text
调用方提交文件
-> 文档解析模块接收请求
-> 规范化输入与文件类型识别
-> 计算 asset_hash
-> 构建 cache_key
-> 查询缓存
-> 若命中则直接返回
-> 若未命中则选择解析策略
-> 执行解析
-> 标准化结果
-> 写入缓存
-> 返回结果
```

### 15.2 PDF 流程

```text
PDF 输入
-> 检测是否有可用文本层
-> 若有文本层，直接提取文本并返回
-> 若无文本层，进入 OCR
-> 标准化结果
-> 写入缓存
```

### 15.3 Agent 场景流程

```text
用户上传附件
-> Agent 调用文档解析入口或 OCR Tool
-> OCR Tool 委托文档解析模块
-> 文档解析模块判重并查缓存
-> 命中则返回
-> 未命中则解析
-> Agent 消费统一解析结果
```

---

## 16. 模块接口边界建议

### 16.1 对上暴露接口

建议对上只暴露统一接口，不暴露具体 parser：

- `parse_document(...)`
- `get_cached_parse_result(...)`
- `detect_file_type(...)`

### 16.2 对下 parser 协议

建议定义统一 parser 抽象：

```python
class BaseDocumentParser(ABC):
    parser_name: str
    parser_version: str

    @abstractmethod
    def supports(self, request: DocumentParseRequest) -> bool:
        raise NotImplementedError

    @abstractmethod
    def parse(self, request: DocumentParseRequest) -> DocumentParseResult:
        raise NotImplementedError
```

### 16.3 OCR parser 的定位

OCR parser 只是 `BaseDocumentParser` 的一种实现，例如：

- `ImageOCRParser`
- `ScannedPDFOCRParser`

OCR provider adapter 仍在 `app/integrations/ocr_providers/` 中，不上浮到业务模块。

---

## 17. 观测与审计

每次文档解析至少记录以下字段：

- trace_id
- tenant_id
- app_id
- scene
- asset_hash
- cache_key
- cache_hit
- parser_name
- parser_version
- file_type
- source_type
- latency_ms
- status
- error_code
- page_count
- text_length
- metadata

建议重点关注以下指标：

- 文档解析总请求量
- 缓存命中率
- OCR 调用占比
- PDF 文本层直出比例
- 平均解析耗时
- 失败率

---

## 18. 风险与约束

### 18.1 风险

- 如果只用文件 hash 做结果复用，容易出现错误命中
- 如果缓存没有 parser_version，升级解析器后结果不可控
- 如果文档解析模块与 OCR Tool 并行演进，容易产生双入口和双缓存
- 如果 Word、Excel、PPT 仍各自在业务层解析，统一模块会被架空

### 18.2 约束

- V1 必须优先保证边界清晰，而不是一次性把所有文件类型做深做全
- V1 必须先建立统一请求/结果模型与缓存协议
- V1 必须先保证知识库和 Agent 两条主复用链路可落地

---

## 19. 分阶段落地建议

### 19.1 第一阶段

- 建立文档解析模块骨架
- 定义统一请求/结果模型
- 建立文件 hash 计算能力
- 建立解析结果缓存协议
- 接入 PDF、图片、TXT

### 19.2 第二阶段

- 接入 DOCX、XLSX、PPTX
- OCR Tool 改为委托文档解析模块
- 打通知识库与 Agent 统一复用
- 增加缓存命中与解析观测指标
- 增加最小位置信息输出能力，至少支持 `page_no` 与 `row_index`

### 19.3 第三阶段

- 增加 HTML、CSV、更多旧版 Office 支持
- 增加结构化模式与表格抽取增强
- 增加并发防重、处理中状态管理
- 增加缓存重建与失效治理
- 视业务需要扩展更细粒度位置信息模型

---

## 20. 验收标准

### 20.1 功能验收

- 相同文件重复上传时可通过 hash 识别重复
- 已解析文件再次请求时可直接返回缓存结果
- PDF 存在文本层时不重复走 OCR
- 图片文件可正常进入 OCR 策略
- DOCX、XLSX、PPTX 可通过统一入口解析
- 知识库与 Agent 均复用同一解析模块

### 20.2 架构验收

- 上层业务不直接依赖具体 OCR 或 Office SDK
- OCR 被收敛为文档解析模块中的一种策略
- 缓存逻辑不散落在知识库、Agent、OCR adapter 中
- 统一文档解析结果结构可被多模块复用

### 20.3 数据验收

- 每次解析均有 trace_id
- 可区分 cache_hit 与 cache_miss
- 可回溯 parser_name 与 parser_version
- 可按 asset_hash 查询历史解析记录
- 页式文档结果可返回 `page_no`
- 表格类文档结果可返回 `row_index`

---

## 21. 最终结论摘要

把“文件 hash 判重 + 解析结果缓存 + OCR/Office/PDF 等能力编排”放在统一文档解析模块中，是合理且推荐的架构方向。

正确的落点不是让 Agent 编排层自己判断“这个文件是否已经 OCR 过”，而是：

- 文档解析模块统一管理所有文件解析能力
- OCR 作为文档解析模块中的一种策略
- 所有文件统一先做文件身份识别与缓存判定
- 命中缓存直接返回
- 未命中再按策略执行解析

这样做的结果是：

- 架构边界更清晰
- 业务模块更轻
- 成本与时延更可控
- 后续扩展更多文件类型时不会重复建设
