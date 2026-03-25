# Chunking 模块实现 PRD（V1）

## 1. 文档目的

本文档用于明确 AI 中台在 V1 阶段如何落地 `Chunking` 模块，并把以下内容写清楚：

- Chunking 在当前架构中的定位
- Chunking 与文档解析、OCR、Embedding、索引、检索之间的边界
- Chunking 模块应该落在哪些目录
- Chunking 的统一输入、输出、配置和策略设计
- 知识库、Agent、工作流如何复用统一 Chunking 能力
- V1 的实现范围、验收标准和演进方向

本文档解决的问题不是“文档要不要切分”，而是“在当前项目架构下，文档切分应如何以统一、可治理、可扩展的方式实现”。

---

## 2. 背景

根据当前架构文档，`知识库与检索层` 由以下关键能力组成：

- 文档解析
- Chunking
- 索引构建
- 向量化
- Retriever / Hybrid
- RAG / Graph RAG

其中：

- OCR 负责把扫描件还原为文本
- 文档解析负责把文件还原为标准化文档结构
- Chunking 负责把长文档切成适合索引、检索和生成的语义片段
- Embedding 负责把切分后的片段映射为向量
- Retrieval 负责按索引和策略召回切分后的片段

因此，Chunking 不应被简单理解成“字符串按长度截断”，而应是知识库链路中的一个独立标准能力。

如果不把 Chunking 模块独立出来，后续通常会出现以下问题：

- OCR 结果自己切一套
- PDF 解析结果自己切一套
- 网页抓取结果自己切一套
- 不同知识库、不同 Agent 对切分粒度理解不一致
- Embedding 输入长度、重叠策略、标题保留策略散落在业务代码里
- 后续要改切分策略时影响面大、难回溯

因此，V1 应先建立统一 Chunking 模块，作为知识库入库链路和后续 RAG 检索的标准中间层。

---

## 3. V1 目标

### 3.1 产品目标

- 提供统一 Chunking 内部调用入口
- 支持标准化解析结果的切分
- 支持按文本长度、段落、标题层级等基础规则切分
- 支持 overlap 配置
- 支持输出稳定的 chunk 元数据
- 支持知识库模块复用
- 支持 Agent / 工作流在需要时复用
- 支持后续接入不同切分策略而不改上层业务

### 3.2 业务价值

- 为索引构建提供统一上游输入
- 为检索召回质量提供稳定基础
- 降低切分策略散落在各业务模块中的维护成本
- 为后续 chunk 评估、召回优化、A/B 策略提供可治理基础

---

## 4. V1 非目标

以下内容不属于本次 V1 必做范围：

- 不做复杂的自学习动态切分
- 不做图文混排、多模态块级理解的完整产品化
- 不做面向所有文件类型的最优策略自动学习
- 不做完整的离线评测平台
- 不做向量数据库绑定逻辑
- 不做检索排序、rerank、query rewrite

说明：

V1 只先把“统一输入 -> 标准切分 -> 标准 chunk 输出 -> 知识库可用”这条主链路跑通。

---

## 5. 术语说明

### 5.1 Parsed Document

由文档解析模块输出的标准化文档对象，包含：

- 文档级元信息
- 页级内容
- 块级结构
- 文本内容

Chunking 模块不直接处理原始文件，而优先处理 Parsed Document。

### 5.2 Chunk

用于索引、Embedding、检索和生成的最小语义片段。

一个 Chunk 不只是字符串，还应附带来源和上下文元数据。

### 5.3 Overlap

相邻两个 Chunk 之间保留的重复上下文，目的是减少切分边界导致的语义断裂。

### 5.4 Chunk Policy

切分策略配置，例如：

- 最大字符数
- 最大 token 数
- overlap
- 按标题切分
- 按段落切分
- 是否保留标题前缀

---

## 6. 方案结论

V1 采用以下统一方案：

1. `Chunking` 作为独立运行时能力，落在 `app/runtime/retrieval/` 下
2. 上层知识库与 Agent 不直接实现切分逻辑，只依赖 Chunking 服务
3. `Chunking` 的输入优先是标准化文档解析结果，而不是原始文件
4. `Chunking` 输出统一 `ChunkDocument` 结构，不向上层暴露底层切分细节
5. 切分策略通过配置对象传入，而不是写死在业务流程里
6. V1 先支持规则型切分，不做复杂自适应切分

换句话说：

- 文档解析模块负责“把文件转成可消费文本结构”
- Chunking 模块负责“把结构化文本转成可索引片段”
- Embedding 模块负责“把片段转成向量”
- Retrieval 模块负责“按检索策略召回片段”

---

## 7. 与其他模块的职责边界

### 7.1 与 OCR 模块

OCR 负责：

- 从图片/PDF 中提取文本

Chunking 不负责：

- 图片识别
- OCR 厂商协议适配

关系是：

```text
OCR -> 文档解析 -> Chunking
```

### 7.2 与文档解析模块

文档解析负责：

- 统一还原文档结构
- 页级/块级文本整理
- 记录原文位置
- 输出标准化 Parsed Document

Chunking 负责：

- 基于 Parsed Document 生成标准 Chunk
- 继承并聚合解析层输出的原文位置

文档解析不负责：

- 决定索引切片大小
- 直接输出最终 Embedding 输入

### 7.3 与 Embedding 模块

Embedding 负责：

- 把 Chunk 转成向量

Chunking 不负责：

- 向量化
- 模型调用
- 索引写入

### 7.4 与 Retrieval / RAG 模块

Retrieval 负责：

- 召回 Chunk
- 混合检索
- 排序和后续组装

Chunking 不负责：

- 查询理解
- 召回排序
- 最终答案生成

---

## 8. 用户与使用场景

### 8.1 知识库场景

- 作为知识库模块，我希望文档上传后得到统一的 chunk 列表，再进入 embedding 和索引流程
- 我希望不同文件来源最终都走同一套切分逻辑
- 我希望未来切分策略可以升级，而不需要改知识库入库主流程

### 8.2 Agent 场景

- 作为 Agent，我希望在处理长文本资料时，可以复用统一 Chunking 模块进行切片
- 我希望 Agent 不直接维护一套独立切分逻辑

### 8.3 平台治理场景

- 作为平台，我希望能够记录 chunk 生成数量、策略版本、来源文档和切分参数
- 我希望后续能基于召回质量回溯是哪种切分策略生成了当前索引

---

## 9. 范围定义

### 9.1 V1 必做范围

- 统一 Chunking 请求和响应协议
- 支持从标准化 Parsed Document 切分
- 支持基础规则型切分
- 支持字符长度控制
- 支持 overlap
- 支持标题/段落优先切分
- 支持输出 chunk 元数据
- 支持知识库入库流程复用
- 支持 Agent 侧按需复用

### 9.2 V1 预留但不强制实现

- token 级精确切分
- 代码语义切分
- 表格专用切分
- 多语言自适应切分
- 基于召回质量的动态切分优化
- chunk 去重缓存
- chunk 质量评估体系

---

## 10. 推荐目录落位

建议后续按以下目录落位：

```text
app/
├─ runtime/
│  ├─ retrieval/
│  │  ├─ chunking/
│  │  │  ├─ schemas.py
│  │  │  ├─ base.py
│  │  │  ├─ policies.py
│  │  │  ├─ text_chunker.py
│  │  │  ├─ document_chunker.py
│  │  │  └─ service.py
│  │  └─ ...
├─ modules/
│  ├─ knowledge_center/
│  │  ├─ services/
│  │  │  ├─ document_parse_service.py
│  │  │  ├─ document_chunk_service.py
│  │  │  └─ ingestion_service.py
│  ├─ agent_center/
│  └─ ...
```

说明：

- `runtime/retrieval/chunking/` 是切分能力的主落点
- `knowledge_center` 只负责调用和编排，不直接实现切分算法
- 如果 Agent 也需要长文切片，则复用同一套 `ChunkingService`

---

## 11. 核心产品规则

### 11.1 单一切分入口规则

上层业务只允许通过统一 Chunking Service 调用切分能力，不允许各自手写一套切分逻辑。

### 11.2 单一 Chunk 输出规则

无论输入来自 OCR、PDF、Markdown、网页还是纯文本，切分后对上层暴露的都应是统一 Chunk 结构。

### 11.3 解析与切分分层规则

文档解析输出可消费文本结构，Chunking 再基于该结构切分。

不允许：

- OCR 直接输出最终 chunk
- 文档解析模块直接耦合 embedding 输入长度

### 11.4 策略配置化规则

chunk size、overlap、标题保留、段落合并等都应通过策略对象管理，而不是硬编码在业务流程里。

### 11.5 可回溯规则

每个 Chunk 应可追溯到：

- 来源文档
- 来源页码或块
- 原文位置范围
- 使用的切分策略
- chunk 顺序

### 11.6 位置透传与聚合规则

如果文档解析模块已经记录了原文位置，Chunking 不允许丢弃这部分数据，而应执行以下规则：

- 单个解析块完整进入某个 chunk 时，原样保留该块的位置
- 多个解析块合并进入某个 chunk 时，聚合保留多个来源位置
- 单个解析块被切成多个 chunk 时，每个 chunk 需要记录其对应的原文子区间
- 若解析层只提供页码级位置，则至少保留页码级映射
- 若解析层提供块级、段落级、字符级 offset 或锚点信息，则 Chunking 应透传这些信息，不应降级丢失

也就是说，Chunking 不只是输出“切分后的文本”，还必须输出“这段文本来自原文哪里”。

---

## 12. 功能需求

### 12.1 统一 Chunking 入口

系统必须提供统一内部调用接口，例如：

```python
chunk_document(request: ChunkingRequest) -> ChunkingResult
```

### 12.2 输入支持

V1 至少支持以下输入：

- 纯文本
- Parsed Document
- OCR + 文档解析后的标准文本结构

其中建议优先支持 Parsed Document，因为它包含标题、页码、块级信息，最利于高质量切分。

### 12.3 切分策略支持

V1 至少支持以下规则：

- 按标题优先切分
- 按段落优先切分
- 按最大字符数切分
- 相邻 chunk overlap
- 标题保留到 chunk 前缀

### 12.4 Chunk 元数据要求

每个 chunk 至少包含：

- `chunk_id`
- `document_id`
- `chunk_index`
- `text`
- `title_path`
- `page_range`
- `source_block_ids`
- `source_positions`
- `policy_name`
- `metadata`

其中：

- `page_range` 用于快速页级定位
- `source_block_ids` 用于回溯解析层 block
- `source_positions` 用于记录更精确的原文位置映射

### 12.5 知识库复用能力

知识库模块必须支持：

1. 先走文档解析
2. 再走统一 Chunking 模块
3. 获取标准 chunk 列表
4. 再进入 embedding / index 流程

### 12.6 Agent / 工作流复用能力

Agent / 工作流若需要长文切分，应直接调用 Chunking Service，不自行实现切分逻辑。

---

## 13. 接口约定

### 13.1 Chunking 请求对象

建议定义如下内部请求对象：

```python
from pydantic import BaseModel, Field

class ChunkingPolicyConfig(BaseModel):
    policy_name: str = "default"
    max_chars: int = 1200
    overlap_chars: int = 150
    split_by_heading: bool = True
    split_by_paragraph: bool = True
    keep_heading_prefix: bool = True


class ChunkingRequest(BaseModel):
    tenant_id: str
    app_id: str
    document_id: str
    scene: str
    parsed_document: dict | None = None
    raw_text: str | None = None
    policy: ChunkingPolicyConfig = Field(default_factory=ChunkingPolicyConfig)
    metadata: dict = Field(default_factory=dict)
```

### 13.2 Chunk 输出对象

建议定义如下统一输出：

```python
from pydantic import BaseModel, Field

class ChunkDocument(BaseModel):
    chunk_id: str
    document_id: str
    chunk_index: int
    text: str
    title_path: list[str] = Field(default_factory=list)
    page_range: list[int] = Field(default_factory=list)
    source_block_ids: list[str] = Field(default_factory=list)
    source_positions: list[dict] = Field(default_factory=list)
    policy_name: str
    metadata: dict = Field(default_factory=dict)


class ChunkingResult(BaseModel):
    document_id: str
    total_chunks: int
    chunks: list[ChunkDocument] = Field(default_factory=list)
    policy_name: str
    metadata: dict = Field(default_factory=dict)
```

### 13.3 对上层的最小契约

知识库和 Agent 最关心的是：

- `chunks[i].text`
- `chunks[i].chunk_id`
- `chunks[i].page_range`
- `chunks[i].source_positions`
- `chunks[i].metadata`

因此这些字段必须稳定。

### 13.4 原文位置最小模型建议

如果解析层已提供结构化位置信息，V1 建议 Chunking 至少支持以下最小位置模型：

```python
class ChunkSourcePosition(BaseModel):
    page_no: int | None = None
    block_id: str | None = None
    paragraph_id: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    metadata: dict = Field(default_factory=dict)
```

说明：

- `page_no` 用于页级快速定位
- `block_id` 用于关联解析层 block
- `paragraph_id` 用于关联段落节点
- `start_offset/end_offset` 用于标识 chunk 在原始文本或规范化文本中的相对区间

如果当前解析层暂时没有提供这么细的位置信息，Chunking 也应预留该结构，避免后续接口破坏性升级。

---

## 14. 运行流程

### 14.1 知识库入库主链路

标准链路如下：

```text
文件上传
-> OCR（若需要）
-> 文档解析
-> Chunking
-> Embedding
-> 向量索引 / 倒排索引
-> Retrieval 可用
```

### 14.2 Chunking 内部流程

建议流程如下：

```text
输入 Parsed Document / Raw Text
-> 文本规范化
-> 结构识别（标题、段落、页）
-> 候选切分单元生成
-> 按策略合并/截断
-> 生成 overlap
-> 继承并聚合原文位置
-> 生成 Chunk 元数据
-> 输出统一 ChunkingResult
```

### 14.3 Agent 长文处理链路

```text
Agent 获取长文
-> 调用文档解析（若需要）
-> 调用 Chunking
-> 按 chunk 分批摘要 / 检索 / 归纳
```

---

## 15. 推荐切分策略设计

### 15.1 默认策略

V1 建议默认策略：

- `max_chars = 1200`
- `overlap_chars = 150`
- `split_by_heading = true`
- `split_by_paragraph = true`
- `keep_heading_prefix = true`

### 15.2 标题优先策略

适用于：

- Markdown
- 规整文档
- 技术文档
- 规章制度

思路：

- 优先按标题树切
- 在标题节点内部再按段落和长度切

### 15.3 段落优先策略

适用于：

- OCR 结果
- 扫描件
- 无明显标题结构的文本

思路：

- 先按段落切
- 再按长度合并或截断

### 15.4 长文本兜底策略

当单段超长时：

- 允许按字符窗口硬切
- 但必须保留 overlap

---

## 16. 质量要求

V1 的 Chunking 至少应满足以下质量要求：

- 单个 chunk 不应大面积跨越多个无关主题
- 切分边界尽量落在标题或段落边界
- 单个 chunk 长度应适配 embedding 模型输入
- chunk 文本应尽可能保持可读性
- chunk 元数据应足够支撑后续定位来源
- chunk 必须能够映射回原文位置

---

## 17. 观测与审计

每次 chunking 调用至少记录以下字段：

- `tenant_id`
- `app_id`
- `document_id`
- `scene`
- `policy_name`
- `source_type`
- `input_length`
- `total_chunks`
- `avg_chunk_length`
- `max_chunk_length`
- `latency_ms`
- `status`
- `error_code`

后续可扩展：

- chunk 命中率
- 召回质量评估结果
- 检索链路反馈回流

---

## 18. 错误模型建议

系统内部建议至少归一以下错误类型：

- `chunking_configuration_error`
- `chunking_validation_error`
- `chunking_empty_input_error`
- `chunking_bad_document_error`
- `chunking_policy_error`
- `chunking_unknown_error`

目标是让知识库和 Agent 不直接感知底层切分细节错误。

---

## 19. 模块实现建议

### 19.1 `schemas.py`

负责定义：

- `ChunkingRequest`
- `ChunkingPolicyConfig`
- `ChunkDocument`
- `ChunkingResult`

### 19.2 `policies.py`

负责定义：

- 默认策略
- 标题优先策略
- 段落优先策略

### 19.3 `text_chunker.py`

负责：

- 纯文本场景切分
- 段落拆分
- 窗口截断
- overlap 生成

### 19.4 `document_chunker.py`

负责：

- 基于 Parsed Document 的结构化切分
- 标题层级处理
- 页码和 block 元数据保留

### 19.5 `service.py`

负责：

- 统一入口
- 参数校验
- 选择切分器
- 输出统一结果

### 19.6 `knowledge_center/services/document_chunk_service.py`

负责：

- 在知识库入库链路中调用 Chunking Service
- 返回标准 chunk 列表供 embedding 与索引复用

---

## 20. 分阶段落地建议

### 20.1 第一阶段

- 定义 Chunking 协议
- 实现纯文本切分
- 实现 Parsed Document 基础切分
- 打通知识库入库主链路

### 20.2 第二阶段

- 增加标题层级切分优化
- 增加 OCR 文本友好策略
- 增加 Agent 长文处理复用入口

### 20.3 第三阶段

- token 级切分优化
- 策略评估与召回反馈回流
- 面向不同文档类型的策略集

---

## 21. 验收标准

### 21.1 功能验收

- 知识库上传任意已解析文档后可生成标准 chunk 列表
- 统一输出 chunk 文本和元数据
- 上层不直接实现切分算法
- 切分结果可直接进入 embedding 和索引流程

### 21.2 架构验收

- Chunking 能力落在 `app/runtime/retrieval/chunking/`
- `knowledge_center` 通过服务调用 Chunking，而不是自己实现切分
- 文档解析与 Chunking 具备清晰边界

### 21.3 数据验收

- 每个 chunk 都有稳定 `chunk_id`
- 每个 chunk 都可回溯来源页码或来源块
- 每个 chunk 都保留解析层输出的原文位置映射，至少不低于解析层已有精度
- 至少支持默认策略下的标题/段落/长度混合切分

---

## 22. 风险与约束

### 22.1 风险

- 如果 OCR、解析、知识库各自切分，后续会形成多套不一致逻辑
- 如果一开始过度追求“最优切分”，会显著拉高实现复杂度
- 如果不保留页码和来源块信息，后续检索定位和引用会受影响
- 如果切分后丢失原文位置映射，后续引用高亮、命中定位、原文跳转会受影响
- 如果 chunk 长度控制不稳定，会直接影响 embedding 与召回质量

### 22.2 约束

- V1 必须优先保证边界清晰
- V1 必须先打通知识库主链路
- V1 必须输出统一 chunk 结构
- V1 必须支持后续策略演进而不破坏上层接口

---

## 23. 与已实现模块的衔接建议

当前项目已经具备：

- OCR Tool 抽象
- 文档解析模块 PRD
- 模型网关能力

因此 Chunking 的合理衔接链路应当是：

```text
OCR Tool
-> 文档解析模块
-> Chunking 模块
-> Embedding / Indexing
-> Retrieval / RAG
```

也就是说：

- OCR 输出不是最终索引输入
- 文档解析输出不是最终检索输入
- Chunking 才是知识库“可索引片段”的标准生成层

---

## 24. 最终结论摘要

基于当前项目架构，Chunking 模块应被实现为 `知识库与检索层` 中的独立基础能力，其合理落位是：

- `app/runtime/retrieval/chunking/` 负责统一切分抽象与实现
- `app/modules/knowledge_center/` 负责在入库流程中复用
- `app/modules/agent_center/` 与 `app/runtime/workflows/` 负责按需复用

V1 的核心不是追求最复杂的切分算法，而是先建立一条清晰、统一、可扩展的切分主链路：

```text
标准化文档输入 -> Chunking -> 标准 Chunk 输出 -> Embedding / Indexing / Retrieval
```
