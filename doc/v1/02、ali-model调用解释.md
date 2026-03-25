# 阿里模型调用解释

## 1. 当前配置

当前 `.env` 中与阿里模型相关的配置如下：

```env
# Direct exception models
PRIVATE_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
PRIVATE_LLM_API_KEY=<redacted>
PRIVATE_LLM_MODEL=qwen3.5-122b-a10b
PRIVATE_LLM_LOGICAL_MODEL=private_sensitive_backup
```

这组配置在当前实现里表示：

- `PRIVATE_LLM_LOGICAL_MODEL=private_sensitive_backup`
  这是系统内部暴露给业务使用的“逻辑模型名”。
- `PRIVATE_LLM_MODEL=qwen3.5-122b-a10b`
  这是实际发给阿里 DashScope 的模型名。
- `PRIVATE_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1`
  这是实际调用的 OpenAI 兼容接口地址。

结论是：

- 这个模型不是通过 LiteLLM Proxy 访问的。
- 它在当前架构里被注册成一个 `direct` 通道的“例外直连模型”。
- 它既可以被显式指定调用，也可以作为默认公有链路失败后的兜底 fallback。

---

## 2. 它在系统里的角色

当前模型层分为三层：

- `app/modules/model_center/`
  负责模型目录、路由策略、fallback 策略。
- `app/runtime/llm/`
  负责运行时解析、调用编排、fallback 执行、响应标准化。
- `app/integrations/model_providers/`
  负责真正对接 LiteLLM Proxy 或外部模型接口。

阿里这个模型落在“外部模型直连”这条分支上。

在 `InMemoryModelConfigRepository.from_settings()` 中，只要同时配置了：

- `PRIVATE_LLM_MODEL`
- `PRIVATE_LLM_BASE_URL`

系统就会自动注册一个模型目录项：

- `logical_model = private_sensitive_backup`
- `channel = direct`
- `direct_model_name = qwen3.5-122b-a10b`
- `base_url = https://dashscope.aliyuncs.com/compatible-mode/v1`

对应代码位置：

- `app/modules/model_center/repositories/in_memory.py`

其核心逻辑等价于：

```python
ModelCatalogEntry(
    logical_model=settings.private_llm_logical_model,
    provider="private_llm",
    channel="direct",
    direct_model_name=settings.private_llm_model,
    base_url=settings.private_llm_base_url,
    api_key=settings.private_llm_api_key,
)
```

这意味着它不是“默认公有模型”，而是“直连模型目录项”。

---

## 3. 第一条链路：显式指定这个逻辑模型时

如果上层请求显式传入：

```python
logical_model="private_sensitive_backup"
```

那么这次请求不会先走 LiteLLM Proxy，而是直接走阿里 DashScope。

完整链路如下：

```text
上层业务请求
-> GatewayService.invoke_chat()
-> ModelResolver.resolve_logical_model("private_sensitive_backup")
-> 读取模型目录项，得到 channel=direct
-> 选择 PrivateLLMAdapter
-> 用 OpenAI 兼容客户端直连 DashScope
-> POST /chat.completions
-> model=qwen3.5-122b-a10b
```

对应的运行时职责如下：

### 3.1 GatewayService

`GatewayService.invoke_chat()` 是统一入口。

它会：

1. 生成 `trace_id`
2. 调用 `ModelResolver` 解析本次请求应该走哪个模型、哪个通道
3. 根据 `channel` 选择 adapter
4. 执行调用
5. 做错误归一、响应标准化和调用记录

### 3.2 ModelResolver

`ModelResolver.resolve_logical_model()` 会把逻辑模型解析成一个可执行计划 `ResolvedInvocationPlan`。

对这个阿里模型来说，解析结果大致是：

```text
logical_model = private_sensitive_backup
channel = direct
provider = private_llm
target_model_name = qwen3.5-122b-a10b
base_url = https://dashscope.aliyuncs.com/compatible-mode/v1
```

### 3.3 PrivateLLMAdapter

`PrivateLLMAdapter` 会真正发请求：

```python
client = OpenAI(base_url=base_url, api_key=api_key)
client.chat.completions.create(
    model=plan.target_model_name,
    messages=request.messages,
    ...
)
```

这里的 `OpenAI(...)` 不是在调 OpenAI 官方模型，而是在使用 OpenAI 兼容 SDK 去请求 DashScope 的兼容接口。

所以最终实际访问的是：

- Base URL: `https://dashscope.aliyuncs.com/compatible-mode/v1`
- API: `POST /chat/completions`
- Model: `qwen3.5-122b-a10b`

---

## 4. 第二条链路：作为默认公有链路失败后的 fallback

当前 `.env` 里还配置了：

```env
MODEL_GATEWAY_ENABLE_PUBLIC_PROXY=true
MODEL_GATEWAY_ENABLE_DIRECT_FALLBACK=true
MODEL_GATEWAY_DEFAULT_LOGICAL_MODEL=chat_default
MODEL_GATEWAY_DEFAULT_PUBLIC_MODEL=public-chat-default
```

因此系统的默认 chat 链路并不是先走阿里模型，而是：

```text
chat_default
-> litellm_proxy
-> public-chat-default
```

只有在主链路失败并满足 fallback 条件时，才会切到阿里模型。

在 `InMemoryModelConfigRepository.from_settings()` 中，只要：

- 开启 `MODEL_GATEWAY_ENABLE_DIRECT_FALLBACK=true`
- 同时配置了 `PRIVATE_LLM_MODEL`

系统就会自动创建 fallback 策略：

```text
source_logical_model = chat_default
channel_fallback_target = private_sensitive_backup
max_fallback_count = 1
```

这条链路可以理解为：

```text
普通 chat 请求
-> 先走 LiteLLM Proxy 公有模型
-> 若公有链路整体失败
-> fallback 到 private_sensitive_backup
-> 直连 DashScope 的 qwen3.5-122b-a10b
```

也就是：

```text
chat_default
  -> litellm_proxy / public-chat-default
  -> direct / private_sensitive_backup
  -> DashScope / qwen3.5-122b-a10b
```

---

## 5. 什么错误会触发 fallback

当前 `GatewayService` 只会在以下错误码下尝试 fallback：

- `timeout_error`
- `rate_limit_error`
- `provider_unavailable`
- `bad_response_error`
- `unknown_error`

如果是以下类型，一般不会 fallback：

- 配置错误
- 权限错误
- 参数校验错误

这是为了避免“本来就不该成功的请求”被盲目切到另一个通道重复执行。

另外还有两个明确约束：

- 必须开启 `MODEL_GATEWAY_ENABLE_DIRECT_FALLBACK`
- fallback 目标通道不能和主通道相同

当前设计要求：

- 公有模型内部的 provider 路由和 fallback 由 LiteLLM Proxy 处理
- 应用侧只做“通道级 fallback”
- 不允许应用和 LiteLLM Proxy 同时做同级公有模型 fallback

所以阿里这个模型在当前实现中的定位是：

- 不是公有模型主路由的一部分
- 而是公有链路失败后的“直连兜底模型”

---

## 6. 最终分两种情况理解

### 情况 A：显式调用 `private_sensitive_backup`

这时链路是：

```text
请求
-> logical_model=private_sensitive_backup
-> channel=direct
-> PrivateLLMAdapter
-> DashScope
-> qwen3.5-122b-a10b
```

特点：

- 不经过 LiteLLM Proxy
- 直接走阿里 DashScope
- 最终返回结果里的 `final_channel` 应为 `direct`
- `final_provider` 应为 `private_llm`
- `final_model` 应为 `qwen3.5-122b-a10b`

### 情况 B：普通 chat 请求，没有显式指定逻辑模型

这时链路是：

```text
请求
-> route 到 chat_default
-> 先走 litellm_proxy / public-chat-default
-> 只有失败时才 fallback
-> direct / private_sensitive_backup
-> DashScope / qwen3.5-122b-a10b
```

特点：

- 阿里模型不是首选
- 它是兜底链路
- 只有满足 fallback 条件时才会被调用

---

## 7. 关键代码位置

与这条阿里模型调用链最相关的代码如下：

- `app/core/config.py`
  负责从环境变量读取 `PRIVATE_LLM_*` 配置。
- `app/modules/model_center/repositories/in_memory.py`
  负责把这组配置注册成 `direct` 模型目录项，并为默认 chat 链路挂上 fallback。
- `app/runtime/llm/model_resolver.py`
  负责把逻辑模型解析成 `ResolvedInvocationPlan`。
- `app/runtime/llm/gateway_service.py`
  负责统一入口、通道分发、fallback 执行。
- `app/integrations/model_providers/private_llm_adapter.py`
  负责用 OpenAI 兼容方式直连 DashScope。

---

## 8. 一句话结论

当前配置下，`qwen3.5-122b-a10b` 走的是“私有/例外模型直连链路”：

- 显式指定 `private_sensitive_backup` 时，直接调用 DashScope。
- 普通 chat 请求时，它不是主链路，而是 `chat_default` 在公有链路失败后的 fallback 兜底模型。
