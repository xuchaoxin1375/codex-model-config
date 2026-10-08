# 工具调用：文件编辑与联网搜索

目录只能**打开**工具，不能让模型学会用法。字段语义见 [model-catalog-json.md](model-catalog-json.md)，命令见 [usage.md](usage.md)。本文讲清三件事：改文件走哪条路、联网搜索是哪种服务、各自依赖什么。

## 文件编辑：两条路

- `apply_patch`（`freeform`）：Codex 把 patch 工具发给模型，模型按 `*** Begin Patch` 格式出补丁，Codex 落地。CLI / IDE 的改文件摘要来自 `apply_patch` 结果，有这个工具才有 GPT 那种每轮文件总结。
- 整文件重写（`null` / 缺省）：Codex 不发该工具，模型改用 Python / shell（heredoc、`cat`）一次写完整文件；内容截断就像写丢文件，且没有改文件摘要。

`shell_type` 决定 shell 工具形态：`unified_exec`（`exec_command` / `write_stdin`，与 GPT 目录一致）、旧 `default` / `shell_command` / `local` / `disabled`。缺失 Codex 可能直接拒读目录。

判定某模型走哪条路必须实测（流程见 [model-catalog-json.md](model-catalog-json.md) 的 apply_patch 小节），不要按供应商宣传定。

## 联网搜索：三种服务，不是 curl

回答“运行 curl 访问指定资源，还是搜索引擎式服务”：Codex 的第一方搜索是**搜索引擎式托管服务**，curl 是另一条独立的路。

### 1. 托管 `web_search`（默认方式）

Responses 请求里的 `type: web_search` 工具，由提供方后端执行搜索并返回结果，模型只发查询、读结果。

- 模式：`cached`（默认，用 OpenAI 维护的索引）、`live`（`config.toml` 写 `web_search = "live"`，或单次 `codex --search`）、`indexed`、`disabled`。
- `web_search_tool_type` 只决定该工具形态：`text` vs `text_and_image`（图片搜索内容形态），默认 `text`。
- 它是托管工具，与沙箱命令网络**相互独立**：不走 permission 的网络代理和域名白名单，命令网络关了也可用。用 `web_search`、`tools.web_search.allowed_domains`、托管 `allowed_web_search_modes` 配置。
- 所有搜索结果一律当不可信输入。

### 2. Standalone `web.run`（自定义提供方）

同一搜索能力、另一条传输：Codex 调 `POST <base_url>/alpha/search`。

- 三个条件缺一不可：TOML `web_search = "live"`、提供方段 `supports_standalone_web_search = true`（默认 `false`）、模型与运行时支持。
- 第三方 / 中转站若没实现 `/alpha/search`，开了开关也不会有搜索；此时用第 3 条或 MCP 搜索工具代替。
- 本 skill 的 `init_profile.py` 暂不写该键（默认 `false` 最稳）；确认上游实现后再手加，见 [workflow.md](workflow.md) 的 TOML 形状。

### 3. 模型自己 `curl` / fetch 指定 URL

走 shell（`exec_command`），与上面两个搜索字段**无关**，依赖：`shell_type`（须有 shell 工具）+ 沙箱 `network_access` + 审批放行。走的是命令网络（代理、限制、超时按提供方调优走），适合“访问这个指定 URL 取内容”，不适合“全网搜答案”。

## 依赖总表

| 能力 | 目录字段 | TOML / CLI | 提供方 / 运行时 |
|---|---|---|---|
| 改文件 patch | `apply_patch_tool_type`、`tool_mode` | —（`--apply-patch-type` 写目录） | 模型实测是否会打 patch 格式 |
| shell / curl 取 URL | `shell_type` | 沙箱 `network_access`、审批策略 | 本机网络 / 代理 |
| 托管搜索 | `web_search_tool_type`（只定形态） | `web_search` 模式、`tools.web_search.allowed_domains` | OpenAI 后端；自定义站需 `/alpha/search` 端点 |
| standalone 搜索 | — | `web_search = "live"` | `supports_standalone_web_search = true` + 模型/运行时支持 |
| 延迟工具发现 | `supports_search_tool`（注意：**不是** web search 开关，管 MCP / app 扩展工具的 `tool_search` 发现面） | Feature `ToolSearch` | — |

## 排障

- 要搜索但模型没调：先查 `web_search` 模式和提供方 standalone 能力，再查目录；只改目录救不了没实现 `/alpha/search` 的上游。
- `supports_search_tool = false`：只关延迟工具发现，不关托管搜索，两者别混淆。
- 沙箱里 `curl` 不通：看 `sandbox_mode` / `network_access` / 审批（见 [codex-sandbox-permissions.md](codex-sandbox-permissions.md)），不是目录问题。

## 第三方模型拒收 `web_search`（mimo-v2.5 实例）

现象：连上就能复现——会话一起就 400，如 `tool type 'web_search' is not supported` / `web search tool found in the request body, but webSearchEnabled is false`。根因不在目录：默认 `cached` 模式也会随请求带 `web_search` 工具，而 MiMo 这类上游（或没开搜索插件的账户、没实现该工具的中转网关）直接拒收。

修法（只动该模型自己的 profile，不动全局默认）：在 `~/.codex/<profile>.config.toml` **顶层**加：

```toml
web_search = "disabled"
```

注意 TOML 位置：必须在任何 `[table]` 之前（文件顶部与其他顶层键一起），写进 `[model_providers.<id>]` 里会被当成提供方字段而忽略。这是 TOML 段落语义，不是 Codex bug。

## 禁用 `web_search` 会挡住 `curl` 吗

不会。这是两套独立开关：`web_search = "disabled"` 只拿掉托管搜索工具；`curl` 走 shell 工具，看沙箱 `network_access` + 审批策略。官方文档原话：搜索是托管工具，与沙箱命令网络相互独立，命令网络关了搜索仍可用——反过来同样成立，搜索关了 `curl` 照常用。mimo profile 里关搜索后，需要取 URL 内容仍可让模型用 `curl`（沙箱放行即可）。
