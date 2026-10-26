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
- 目录里 `use_responses_lite` 为 `true` 时该工具不进请求：顶层 `tools` 为空，`input[].additional_tools` 里也没有它，配置看着生效实则没有；判定与修法见 [model-catalog-json.md](model-catalog-json.md) 的 use_responses_lite 小节。
- `web_search_tool_type` 只决定该工具形态：`text` vs `text_and_image`（图片搜索内容形态），默认 `text`。
- 搜索由提供方后端执行，与沙箱命令网络**相互独立**：命令网络关了也可用。用 `web_search`、`tools.web_search.allowed_domains`、托管 `allowed_web_search_modes` 配置；客户端调用 Responses API 的连接仍需可达，直接用 shell 发请求时仍按 `network-access` 选路。
- 所有搜索结果一律当不可信输入。

### 2. Standalone `web.run`（自定义提供方）

同一搜索能力、另一条传输：Codex 调 `POST <base_url>/alpha/search`。

- 需要 TOML `web_search = "live"`、提供方段 `supports_standalone_web_search = true`（默认 `false`），以及模型与运行时支持；还需检查当前客户端的 `standalone_web_search` 功能开关，该功能仍在开发且默认关闭。
- `/alpha/search` 只属于独立搜索传输，未实现它不代表 Responses 托管 `web_search` 不可用。只有确认端点兼容后才声明支持；参数校验类 400 不能单独证明兼容或不兼容，不用猜参数连试，也不盲开此开关。
- 本 skill 的 `init_profile.py` 暂不写该键（默认 `false` 最稳）；确认上游实现后再手加，见 [workflow.md](workflow.md) 的 TOML 形状。

### 3. 模型自己 `curl` / fetch 指定 URL

走 shell（`exec_command`），与上面两个搜索字段**无关**，依赖：`shell_type`（须有 shell 工具）+ 沙箱 `network_access` + 审批放行。走的是命令网络（代理、限制、超时按提供方调优走），适合“访问这个指定 URL 取内容”，不适合“全网搜答案”。

## 依赖总表

| 能力 | 目录字段 | TOML / CLI | 提供方 / 运行时 |
|---|---|---|---|
| 改文件 patch | `apply_patch_tool_type`、`tool_mode` | —（`--apply-patch-type` 写目录） | 模型实测是否会打 patch 格式 |
| shell / curl 取 URL | `shell_type` | 沙箱 `network_access`、审批策略 | 本机网络 / 代理 |
| 托管搜索 | `web_search_tool_type`（只定形态）、`use_responses_lite=false` | `web_search` 模式、`tools.web_search.allowed_domains` | 提供方在 `/responses` 支持并执行 `type: web_search` |
| standalone 搜索 | — | `web_search = "live"`、客户端功能开关 | `supports_standalone_web_search = true` + 兼容 `/alpha/search` + 模型/运行时支持 |
| 延迟工具发现 | `supports_search_tool`（注意：**不是** web search 开关，管 MCP / app 扩展工具的 `tool_search` 发现面） | Feature `ToolSearch` | — |

## 第三方网关：启用与排查顺序

按顺序过，前一步不成立时后一步改了也白改：

1. **目录是否真的被加载**：`debug models` 的模型集合与字段应等于你的文件；与 `--bundled` 一致说明读的是内置目录（判定见 [usage.md](usage.md) 校验一节）。
2. **工具是否下发**：目录条目 `use_responses_lite` 必须为 `false`，否则托管 `web_search` 不进请求（见 [model-catalog-json.md](model-catalog-json.md) 的 use_responses_lite 小节）；脚本修复用 `--responses-lite false`。
3. **模式是否打开**：profile 顶层（任何 `[table]` 之前）写 `web_search = "live"`；`cached` 只走索引，`disabled` 直接移除工具。
4. **网关是否支持**：托管工具走 `/v1/responses` 的顶层 `tools`，要求网关原样透传；`supports_standalone_web_search` 是另一条路（`POST /v1/alpha/search`），网关没实现就别开。
5. **行为是否真的发生**：会话内看 `exec --json` 是否出现 `"type":"web_search"` 的 item 事件；要判定提供方后端本身是否支持，见[搜索可用性的验证边界](#搜索可用性的验证边界)的直接 `/responses` 验证。只有 shell `curl` 抓页面，说明仍没走托管搜索。

最小配置三处，缺一不可：

| 位置 | 键 | 值 |
|---|---|---|
| profile TOML 顶层 | `web_search` | `"live"` |
| 目录条目 | `use_responses_lite` | `false` |
| 目录条目 | `web_search_tool_type` | `"text"`（图片搜索才 `text_and_image`） |

可选：`[tools.web_search]` 的 `context_size`、`allowed_domains`。`supports_search_tool` 管的是延迟工具发现，与托管搜索无关，不要为搜索去动它。

体检入口：先跑 `check_profile.py`（见 [usage.md](usage.md) §4），它会校验顶层 `web_search` 取值；目录条目 `use_responses_lite=true` 时给 `W_RESPONSES_LITE`，`false` 时打印 `I_WEB_SEARCH_SUMMARY`。要一屏看生效值、目录字段与 profile 覆盖，用 `inspect_web_search.py`（见 [usage.md](usage.md) §5）。两者都只覆盖配置层，通过后再按上面的顺序做真实请求。

## 排障

- 要搜索但模型没调：按上一节「第三方网关：启用与排查顺序」逐项过（先核对生效的 profile、模型、提供方和 `web_search` 模式），再按[搜索可用性的验证边界](#搜索可用性的验证边界)取证；目录字段只决定工具形态，不能代替后端执行证据。
- `supports_search_tool = false`：只关延迟工具发现，不关托管搜索，两者别混淆。
- 沙箱里 `curl` 不通：看 `sandbox_mode` / `network_access` / 审批（见 [codex-sandbox-permissions.md](codex-sandbox-permissions.md)），不是目录问题。

### 搜索可用性的验证边界

**本地工具列表不覆盖托管工具**：`ALL_TOOLS` 或 MCP 列表里没有 `web_search`，只能说明该列表没有本地可调用入口，不能据此判定提供方搜索不可用。`web_search = "live"` 也只证明配置意图；访问搜索网站返回 HTTP 200 只证明该请求取回了页面，仍可能是提示页或挑战页。

需要验证后端时，使用当前提供方、模型和凭据向 `/responses` 发最小请求：

1. `tools` 含 `{"type":"web_search"}`；仅保留此工具并设 `tool_choice: "required"`，要求查找一个可核验的官方页面。
2. 验证实时模式时显式设工具的 `external_web_access: true`；可加 `include: ["web_search_call.action.sources"]` 取得来源。记录请求的模式，避免把普通搜索或缓存结果写成已验证实时搜索。
3. 检查响应或 SSE 最终事件：出现 `type: "web_search_call"`、`status: "completed"`，并返回查询及可核验的来源或引用，才记录为该提供方的托管搜索通过。只有 HTTP 200、助手说“我会搜索”或正文给出链接均不足以证明执行过搜索。凭据从现有环境或安全存储读取，不回显，不落入诊断产物。

**直接 API 验证通过不代表当前会话原生入口已恢复**。交付时分别说明后端验证结果、当前会话能否实际调用，以及是否修改配置。后端已通过且配置正确时先保留配置；客户端配置或目录确有修改时重载并开新会话，再观察原生搜索事件。未经复验，不承诺重开会话就能解决，也不把直接 API 调用写成原生入口修复成功。

### 验证成本与顺序

搜索与模型请求按次计费。配置检查默认只做第 1 步，`debug models` 通过就结束；第 2、3 步和抓包只在用户明确要求时做。托管搜索的最短路径是三处齐备：顶层 `web_search = "live"`、目录 `use_responses_lite = false`、目录 `web_search_tool_type = "text"`。

1. 静态：`debug models` 核对目录字段（`use_responses_lite`、`web_search_tool_type`）与生效的 profile / model；不抓包、不转发、不发真实请求。
2. 端点级（需用户同意）：用最小请求直接打该传输的端点（托管走 `/responses` 的 `tools`，standalone 走 `/alpha/search`），只看状态与事件类型；一次失败即换路，不重试同一请求。
3. 会话级（需用户同意）：先问不搜——让模型只报告可用的搜索工具名（如“列出你能调用的搜索工具，不要执行搜索”）也要算一次模型请求；真实搜索按用户授权做，提示词限定“一次搜索、一句话结论”。
4. 复用已有证据：同一配置的会话级验证至多一次，配置再改才重测。

例：`debug models` 已显示目录条目 `use_responses_lite=false`、`web_search_tool_type=text`，且同一配置已有真实请求证据时，直接改配置；不再开第二个会话或补抓包。

自检：

- [ ] 是否按实际传输判断依赖，没有把 `/alpha/search` 当作托管搜索的前提？
- [ ] 是否保留已完成的搜索调用与来源证据，并分别报告后端、实时模式和会话入口的验证范围？
- [ ] 是否按静态 → 端点 → 会话的成本顺序取证，且没有为同一结论重复发起计费会话？

## 第三方模型拒收 `web_search`（mimo-v2.5 实例）

现象：连上就能复现——会话一起就 400，如 `tool type 'web_search' is not supported` / `web search tool found in the request body, but webSearchEnabled is false`。根因不在目录：默认 `cached` 模式也会随请求带 `web_search` 工具，而 MiMo 这类上游（或没开搜索插件的账户、没实现该工具的中转网关）直接拒收。

修法（只动该模型自己的 profile，不动全局默认）：在 `~/.codex/<profile>.config.toml` **顶层**加：

```toml
web_search = "disabled"
```

注意 TOML 位置：必须在任何 `[table]` 之前（文件顶部与其他顶层键一起），写进 `[model_providers.<id>]` 里会被当成提供方字段而忽略。这是 TOML 段落语义，不是 Codex bug。

## 禁用 `web_search` 会挡住 `curl` 吗

不会。这是两套独立开关：`web_search = "disabled"` 只拿掉托管搜索工具；`curl` 走 shell 工具，看沙箱 `network_access` + 审批策略。官方文档原话：搜索是托管工具，与沙箱命令网络相互独立，命令网络关了搜索仍可用——反过来同样成立，搜索关了 `curl` 照常用。mimo profile 里关搜索后，需要取 URL 内容仍可让模型用 `curl`（沙箱放行即可）。
