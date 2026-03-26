# 04、双OCR Provider并存接入PRD

## 1. 文档目标

本文用于明确当前 `ai-center` 仓库如何同时接入两套 OCR provider，并让它们在同一套文档解析链路内并存：

- 现有 OCR 服务：偏 `layout parsing`，返回 `markdown` 风格文本
- 新 OCR 服务：偏 `plain text OCR`，直接返回纯文本

本文重点回答以下问题：

- 当前仓库的 OCR 接入边界在哪里
- 为什么现有 markdown OCR 不适合所有场景
- 新的纯文本 OCR 应该如何接入
- 两套 OCR provider 如何并存而不是互相替换
- 默认路由应该怎么设计
- 在 PDF 分批 OCR、断点续传、RAG 入库场景下如何选择 provider

本文是接入方案 PRD，不是具体代码实现说明。

---

## 2. 背景

### 2.1 当前 OCR 现状

当前仓库里已经有一套内部 OCR 接入，主要用于版面解析，返回结构来自：

- `result.layoutParsingResults[].markdown.text`

当前适配器实现：

- `app/integrations/ocr_providers/internal_ocr_adapter.py`

它的特点是：

- 更偏文档版面解析
- 结果更接近 markdown / layout block
- 更适合保留标题、区块、版式信息

但对某些场景，它并不理想：

- 纯文本抽取时噪声较多
- markdown 标记会干扰下游 chunk
- 对简单 OCR 场景来说处理链路偏重
- 有些 RAG 场景只需要“连续纯文本”，不需要版式语义

### 2.2 新 OCR 服务现状

你现在新增的 OCR 服务，调用方式类似：

- 请求体传 `file`
- `fileType=0/1`
- 返回 `result.ocrResults[].prunedResult.rec_texts`

它的特点是：

- 更偏纯 OCR 文本识别
- 返回内容更直接
- 不强调 markdown / layout 结构
- 更适合作为“纯文本 OCR provider”

因此，本次目标不是替换掉现有 OCR，而是让两套 provider 并存。

---

## 3. 当前代码接入边界

当前 OCR 主链路如下：

```text
OCRTool
-> DocumentParseService
-> OCRExecutionService
-> BaseOCRProviderAdapter
-> 具体 provider adapter
```

对应代码位置：

- OCR 工具入口：
  - `app/runtime/tools/ocr_tool.py`
- 文档解析入口：
  - `app/modules/document_center/services/document_parse_service.py`
- OCR 执行服务：
  - `app/modules/document_center/services/ocr_execution_service.py`
- provider 基类：
  - `app/integrations/ocr_providers/base.py`
- 当前 provider：
  - `app/integrations/ocr_providers/internal_ocr_adapter.py`
  - `app/integrations/ocr_providers/aliyun_ocr_adapter.py`

### 3.1 当前 registry 机制

当前 provider 是通过 `build_default_ocr_adapters()` 注册的。

也就是说，只要新增一个 adapter，并在 registry 里注册，系统就已经具备“双 provider 并存”的基础能力。

这意味着：

- 当前架构不需要推翻
- 只需要新增 provider adapter 和 provider 路由策略

---

## 4. 方案结论

### 4.1 总体结论

建议在现有 `internal_ocr` 之外，再新增一套纯文本 OCR provider，例如：

- `internal_text_ocr`

然后让系统支持：

1. 两套 provider 同时注册
2. 调用方可显式指定 `provider`
3. 未显式指定时，由系统按场景自动路由

### 4.2 命名建议

为了避免混淆，建议不要继续让“layout OCR”和“text OCR”共用一个 provider 名称。

建议命名如下：

- `internal_ocr`
  保留现有含义，表示版面解析型 OCR

- `internal_text_ocr`
  新增 provider，表示纯文本 OCR

这样做的好处是：

- 对已有调用兼容
- 语义清楚
- 便于配置和路由

### 4.3 不建议的方案

不建议直接把当前 `internal_ocr` 改造成“有时返回 markdown、有时返回纯文本”的单 provider 混合模式。

原因：

- provider 语义会变得不稳定
- 调试时难以判断当前到底走了哪种 OCR
- 测试和回归成本高
- 后续 tracing 和评测也不清晰

---

## 5. 两套 OCR 的职责定位

### 5.1 layout OCR

`internal_ocr`

职责：

- 保留版面结构
- 更适合复杂文档、标题层级、区块信息、layout parsing
- 更适合结构化解析或对版式敏感的场景

典型输出：

- markdown 文本
- layout block 组合结果

### 5.2 text OCR

`internal_text_ocr`

职责：

- 输出连续纯文本
- 更适合直接进入 chunking / embedding / RAG
- 更适合“只关心文本内容、不关心排版结构”的场景

典型输出：

- plain text
- 轻量 pages 列表

---

## 6. 建议接入方式

### 6.1 新增 adapter

建议新增：

- `app/integrations/ocr_providers/internal_text_ocr_adapter.py`

职责：

- 按新服务协议组装请求
- 调用新的纯文本 OCR 接口
- 将返回值转换成统一的 `OCRProviderResponse`

### 6.2 请求映射

建议新 adapter 的请求仍沿用统一 `OCRToolRequest`：

- `source_type`
- `source_value`
- `file_type`
- `language_hints`
- `metadata`

这意味着：

- 上层不需要知道新 provider 的协议细节
- 新服务只是多一个 adapter，不是多一套新工具

### 6.3 响应映射

虽然新服务直接返回纯文本，但仍建议统一映射为：

- `provider`
- `model`
- `text`
- `pages`
- `usage`
- `raw_response`

如果新服务返回：

- `ocrResults[]`

则建议适配为：

- 每个 `ocrResults[i]` 映射成一个 `OCRPage`
- `rec_texts` 拼接成该页文本
- 最终所有页再拼成总 `text`

如果服务并不可靠返回页级结构，也至少要保证：

- `text` 完整
- `pages` 尽力映射

---

## 7. 配置设计

建议在现有 OCR 配置基础上新增一组 text OCR 配置：

```env
# OCR runtime
OCR_DEFAULT_PROVIDER=internal_text_ocr
OCR_DEFAULT_LAYOUT_PROVIDER=internal_ocr
OCR_DEFAULT_TEXT_PROVIDER=internal_text_ocr

# Internal layout OCR
INTERNAL_OCR_BASE_URL=
INTERNAL_OCR_API_KEY=

# Internal text OCR
INTERNAL_TEXT_OCR_BASE_URL=
INTERNAL_TEXT_OCR_API_KEY=
INTERNAL_TEXT_OCR_MODEL=paddleocr_v5
```

### 7.1 配置含义

- `OCR_DEFAULT_PROVIDER`
  全局兜底 provider

- `OCR_DEFAULT_LAYOUT_PROVIDER`
  结构化或 layout 场景默认 provider

- `OCR_DEFAULT_TEXT_PROVIDER`
  纯文本场景默认 provider

### 7.2 兼容原则

为了兼容已有代码：

- 旧配置 `OCR_DEFAULT_PROVIDER` 继续保留
- 新的 `TEXT/LAYOUT` 专属默认 provider 作为增强配置引入

---

## 8. 路由策略设计

### 8.1 显式指定优先

最优先规则：

- 如果请求里显式传了 `provider`
- 则直接按调用方指定执行

这条规则适用于：

- 调试
- A/B 对比
- 回归验证
- 特定业务强制选 provider

### 8.2 默认自动路由

如果调用方没有显式指定 `provider`，建议按以下规则自动路由：

1. `enable_layout=true`
   -> 走 `OCR_DEFAULT_LAYOUT_PROVIDER`

2. `parse_mode=structured`
   -> 走 `OCR_DEFAULT_LAYOUT_PROVIDER`

3. `parse_mode=text`
   -> 走 `OCR_DEFAULT_TEXT_PROVIDER`

4. `parse_mode=preview`
   -> 默认走 `OCR_DEFAULT_TEXT_PROVIDER`

5. 都未命中
   -> 走 `OCR_DEFAULT_PROVIDER`

### 8.3 路由落点

建议把路由逻辑放在：

- `app/modules/document_center/services/ocr_execution_service.py`

而不是写在 adapter 里。

原因：

- adapter 应只负责协议转换
- provider 选择属于 service 层职责
- 这样便于后续继续接第三个 OCR provider

---

## 9. 与当前 PDF 分批 OCR 的关系

当前仓库已经实现：

- PDF 分批 OCR
- batch JSON checkpoint
- 断点续传

这套能力现在已经上移到了 service 层，因此对新 provider 非常友好。

结论是：

- 新的 `internal_text_ocr` 不需要支持 `page_range`
- 因为 service 层已经会把 PDF 切成批次 PDF 资产
- OCR provider 只需要处理“当前这一批次 PDF”

这意味着两套 OCR provider 都可以复用同一套：

- `PDFOCRBatchingService`
- `PDFBatchAssetService`
- `PDFOCRCheckpointRepository`

不需要分别再做一套 batch / resume 逻辑。

---

## 10. 推荐落地方案

### 10.1 第一阶段

先把 provider 并存接起来，不做复杂策略：

1. 新增 `internal_text_ocr_adapter.py`
2. 在 `build_default_ocr_adapters()` 注册：
   - `internal_ocr`
   - `internal_text_ocr`
3. 新增配置：
   - `INTERNAL_TEXT_OCR_BASE_URL`
   - `INTERNAL_TEXT_OCR_API_KEY`
4. 先支持调用方手动指定 `provider`

### 10.2 第二阶段

再加默认自动路由：

1. `enable_layout / parse_mode` 驱动 provider 选择
2. 让 `DocumentParseService` 默认在 text 场景走纯文本 OCR
3. 让 structured 场景继续走 layout OCR

### 10.3 第三阶段

再做效果评测与观测：

1. LangSmith 里记录 `provider`
2. 记录 `ocr_profile=text/layout`
3. 对两套 provider 做 A/B 对比
4. 评估：
   - 文本质量
   - chunk 质量
   - RAG 命中效果
   - 耗时与成本

---

## 11. 代码改动建议

建议改动以下文件：

- `app/core/config.py`
  - 新增 text OCR provider 配置

- `app/integrations/ocr_providers/internal_text_ocr_adapter.py`
  - 新增纯文本 OCR adapter

- `app/runtime/tools/ocr_tool.py`
  - 在 `build_default_ocr_adapters()` 注册新 provider

- `app/modules/document_center/services/ocr_execution_service.py`
  - 增加 provider 自动路由逻辑

- `app/modules/document_center/services/document_parse_service.py`
  - 不需要大改，只透传 provider / parse_mode / enable_layout

- `tests/unit/integrations/ocr_providers/`
  - 新增 adapter 单测

- `tests/unit/modules/document_center/`
  - 新增 provider 路由单测

---

## 12. 验收标准

### 12.1 Provider 并存

- 系统能同时注册：
  - `internal_ocr`
  - `internal_text_ocr`

### 12.2 显式选择

- 调用方传 `provider=internal_ocr` 时，稳定返回 layout OCR 结果
- 调用方传 `provider=internal_text_ocr` 时，稳定返回纯文本 OCR 结果

### 12.3 自动路由

- `parse_mode=text` 默认走 text OCR
- `parse_mode=structured` 默认走 layout OCR
- `enable_layout=true` 时优先走 layout OCR

### 12.4 批处理兼容

- 大 PDF 在 `internal_text_ocr` 下也能正常走批次 OCR
- 断点续传逻辑不因 provider 切换而失效

### 12.5 向后兼容

- 现有依赖 `internal_ocr` 的调用不被破坏
- 未改配置时系统行为仍可控

---

## 13. 风险与注意事项

### 13.1 两套 OCR 结果风格不同

这是预期，不是 bug。

风险在于：

- markdown OCR 和 plain text OCR 的 chunk 结果可能明显不同
- RAG 召回效果也可能不同

因此需要用评测去验证，而不是只看“能不能跑通”。

### 13.2 路由规则不能过度隐式

如果自动路由太复杂，会造成：

- 调试困难
- 用户不知道当前到底走了哪个 provider

因此必须保证：

- 显式 `provider` 优先
- trace 和日志里能看到最终 provider

### 13.3 不要把 provider 选择写死在 parser

`PDFDocumentParser` 不应写成：

- 固定只走 layout OCR
- 固定只走 text OCR

否则后面扩展第三个 OCR provider 会再次重构。

provider 选择应该收敛在 service 层。

---

## 14. 本文结论

当前仓库已经具备让两套 OCR provider 并存的基础架构。

最合理的方案是：

- 保留现有 `internal_ocr` 作为 layout OCR
- 新增 `internal_text_ocr` 作为纯文本 OCR
- 上层继续走同一套 `OCRTool / DocumentParseService / OCRExecutionService`
- provider 选择通过“显式指定优先 + service 层自动路由”完成
- PDF 分批 OCR、checkpoint、断点续传继续复用现有公共能力

这样做的结果是：

- 两套 OCR 可以同时服务不同场景
- 不需要推翻现有架构
- 后续也方便继续做评测、灰度和切换
