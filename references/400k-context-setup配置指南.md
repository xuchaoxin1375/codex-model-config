# Codex 400K 上下文配置参考

本文说明如何让 Codex CLI 和 VSCode Codex 扩展都使用 400K 上下文窗口。适用场景：第三方/自定义模型供应商，例如 DeepSeek，并通过 `model_provider` 接入 Codex。

> 这是 DeepSeek 400K 的一份已验证示例，不是唯一目标。完整接入（提供方、目录、profile、校验）见 [workflow.md](workflow.md)。任意窗口、以及 profile / slug / 缺 catalog 的处理，见 [常见陷阱.md](常见陷阱.md) 和 [context-window-guide.md](context-window-guide.md)。`models.json` 从哪来、为何不是下载 OpenAI 目录，见 [catalog-source.md](catalog-source.md)。


验证版本：

- Codex CLI：`0.149.0`
- VSCode 扩展内置 Codex：`0.149.0-alpha.4`
- 扩展版本：`26.818.31338`

## 为什么直接配置 `model_context_window` 不够

Codex 对模型使用两层上下文限制：

1. 模型目录中的 `max_context_window` 是配置覆盖上限。
2. 模型目录中的 `effective_context_window_percent` 会进一步减少可用输入上下文。

若自定义模型不在内置模型目录中，Codex 会使用 fallback 元数据：

- `context_window = 272000`
- `max_context_window = 272000`
- `effective_context_window_percent = 95`

因此即使写了：

```toml
model_context_window = 400000
```

运行时仍会被钳制为：

```text
272000 × 95% ≈ 258400
```

正确做法是提供一个自定义 `models.json`，把该模型的上限和有效比例调高。

## 最小有效配置

### 1. `~/.codex/config.toml`

把路径替换成你自己的用户目录：

```toml
model_provider = "deepseek"
model = "deepseek-v4-flash-vision-exp"
model_reasoning_effort = "max"

model_context_window = 400000
model_auto_compact_token_limit = 360000
model_catalog_json = "/home/<你的用户名>/.codex/models.json"

[model_providers.deepseek]
name = "deepseek"
base_url = "https://api.deepseek.com"
wire_api = "responses"
requires_openai_auth = true
```

说明：

- `model_context_window = 400000`：目标上下文窗口。
- `model_auto_compact_token_limit = 360000`：达到 90% 后开始自动压缩。
- `model_catalog_json`：必须是绝对路径；该配置只在 Codex 启动时加载。
- API 密钥需放在 `~/.codex/auth.json`，或改用供应商支持的 `env_key` 方式。

### 2. `~/.codex/models.json`

这是一个经过当前版本验证的最小文件：

```json
{
  "models": [
    {
      "slug": "deepseek-v4-flash-vision-exp",
      "display_name": "DeepSeek V4 Flash Vision Exp (400K)",
      "description": "DeepSeek 400K context metadata for Codex.",
      "default_reasoning_level": "max",
      "supported_reasoning_levels": [
        { "effort": "low", "description": "低强度思考" },
        { "effort": "medium", "description": "中强度思考（DeepSeek 映射为 high）" },
        { "effort": "high", "description": "高强度思考" },
        { "effort": "xhigh", "description": "极高强度思考（DeepSeek 映射为 high）" },
        { "effort": "max", "description": "最大强度思考" }
      ],
      "shell_type": "default",
      "visibility": "list",
      "supported_in_api": true,
      "priority": 99,
      "availability_nux": null,
      "upgrade": null,
      "model_messages": {
        "instructions_template": "You are Codex, an agent based on DeepSeek V4 Flash Vision Exp. You and the user share one workspace and collaborate until their goal is handled.",
        "instructions_variables": null,
        "approvals": null
      },
      "include_skills_usage_instructions": false,
      "include_plugin_usage_instructions": false,
      "include_apps_usage_instructions": false,
      "supports_reasoning_summaries": false,
      "default_reasoning_summary": "none",
      "support_verbosity": false,
      "default_verbosity": null,
      "apply_patch_tool_type": null,
      "web_search_tool_type": "text",
      "truncation_policy": { "mode": "bytes", "limit": 10000 },
      "supports_image_detail_original": true,
      "context_window": 400000,
      "max_context_window": 400000,
      "auto_compact_token_limit": null,
      "comp_hash": "deepseek-v4-flash-vision-exp-400k",
      "effective_context_window_percent": 100,
      "experimental_supported_tools": [],
      "input_modalities": ["text", "image"],
      "supports_search_tool": false,
      "use_responses_lite": false,
      "node_repl_auto_review_required": false,
      "node_repl_disabled": false,
      "auto_review_model_override": null,
      "model_specialty": null,
      "tool_mode": null,
      "multi_agent_version": null
    }
  ]
}
```

关键字段：

- `context_window = 400000`：模型目录声明的基础上下文。
- `max_context_window = 400000`：允许 `model_context_window` 覆盖的上限；没有它，400000 会被钳回 272000。
- `effective_context_window_percent = 100`：避免默认 95% 把 400000 再降为 380000。
- `auto_compact_token_limit = null`：实际压缩阈值由 `config.toml` 的 360000 控制，并会被限制为 400000 的 90%，最终正好是 360000。
- `supported_reasoning_levels`：Codex UI 中“思考深度”的可选项；`default_reasoning_level` 是未手动选择时使用的默认档位。

注意：`model_catalog_json` 会替换内置模型目录。若还需要 OpenAI 内置模型，请使用与当前 Codex 版本匹配的完整 `models.json`，再把上面的模型对象追加到 `models` 数组中，不要直接覆盖为只有 DeepSeek 的版本。

## 思考深度列表

参照 [DeepSeek 思考模式文档](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/)，`deepseek-v4-flash` 与 `deepseek-v4-pro` 接受以下档位：

| 请求传入 effort | DeepSeek 实际映射 |
|---|---|
| `low` | `low` |
| `medium` | `high` |
| `high` | `high` |
| `xhigh` | `high` |
| `max` | `max` |

因此 UI 中虽然会显示 `medium` 和 `xhigh`，但供应商侧并不会产生比 `high` 更强的推理。若要真正使用最高强度，请选 `max`。当前配置默认使用 `max`：

```toml
model_reasoning_effort = "max"
```

该配置读取的是整个模型目录中 `default_reasoning_level` 的初始值；修改它之后，需要按下面的步骤重启 Codex/重载 VSCode 窗口才能生效。

## 部署步骤

1. 修改 `~/.codex/config.toml`，添加 `model_catalog_json`。
2. 创建 `~/.codex/models.json`。
3. 验证配置解析（只检查默认配置；profile 请用 `codex -c model_catalog_json=... debug models`）：

```bash
codex --strict-config doctor
```

应看到：

```text
config.toml parse ok
```

4. 验证模型目录已加载：

```bash
codex debug models
```

应能看到 DeepSeek 条目，且相关值包含：

```text
context_window: 400000
max_context_window: 400000
effective_context_window_percent: 100
```

## VSCode 扩展使用说明

`model_catalog_json` 只在 app-server 启动时加载。已经运行的 VSCode 窗口不会自动重载，即使新建对话也没有效果。

在 VSCode 中执行：

```text
Ctrl+Shift+P
Developer: Reload Window
```

重新加载后：

- 给 Codex 插件新建一个对话。
- 模型选择器中应能看到 DeepSeek 条目。
- 新会话运行时 `model_context_window` 应为 `400000`。
- 旧会话不会更新，仍保留启动时的 258400；不要用旧会话验证。

## 常见错误

| 问题 | 表现 | 解决方法 |
|---|---|---|
| 没有 `models.json` | 运行仍是 258400 | 添加 `model_catalog_json` 和自定义模型条目 |
| `max_context_window` 小于 400000 | 配置被钳制 | 设成 400000 或更大 |
| 未设置 `effective_context_window_percent` | 变成 380000 | 设置为 100 |
| 只改配置不重载 VSCode | 新对话仍可能不变 | 执行 Developer: Reload Window |
| 使用相对路径 | 启动时找不到文件 | 使用绝对路径 |
| 修改后立即切换模型 | 扩展可能仍使用旧 app-server | 重载 VSCode 后重新选择模型 |
| 供应商实际不支持 400K | 服务端可能报上下文错误 | 先确认供应商模型支持量，不要只改本地值 |

## 参考

- [Codex 配置基础（CLI 与 IDE 共用配置）](https://learn.chatgpt.com/docs/config-file/config-basic)
- [Codex 配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)
- [Codex IDE 扩展](https://learn.chatgpt.com/docs/codex/ide)
- [DeepSeek 思考模式](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/)
