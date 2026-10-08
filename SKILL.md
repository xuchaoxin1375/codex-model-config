---
name: codex-model-config
description: >
  为 Codex 端到端配置自定义或第三方模型：提供方端点、API Key 环境变量、
  models.json 目录、上下文窗口，以及哪份 profile TOML 持有 model=model-name。

  适用于：新增或切换 model_providers、写入目录元数据、设置 model_catalog_json，
  或让指定上下文窗口真正生效，包括模型写在 Codex profile 里、或 models.json 中缺失的情况。
  也适用于第三方模型不走 apply_patch、改用 Python 写文件、缺少改文件摘要、把 GPT/DeepSeek 的 support_verbosity 抄给 Grok、或 Grok 打开 apply_patch freeform 后反复失败、效率更差的情况。

  不适用于：只改 MCP、沙箱或审批策略、通用 OpenAI SDK 客户端，
  以及不涉及提供方、目录或配置文件的纯推理强度调整。
---
# Codex 模型配置

把自定义或第三方模型接到 Codex：提供方、目录元数据、上下文窗口。CLI、ChatGPT 桌面端和 VS Code Codex 插件共用同一份用户配置。

命令示例唯一出处：[references/usage.md](references/usage.md)。本文只给约束和顺序，不重复贴命令。

## 关键约束

- 先备份，再只改必要字段。MCP、`[projects.*]`、沙箱和审批策略一律保留。
- 新模型默认新建 `~/.codex/<provider-id>.config.toml`，不要改正在用的默认 `config.toml`。未指定 id 用模型系列名（`gpt`/`grok`/`deepseek` 等），全量替换占位符。保留 id（`openai`/`ollama`/`lmstudio`）不可占。`model_providers` 只能在用户级配置。
- 改真正设置 `model=model-name` 的那份 TOML。`model_catalog_json` 写进默认配置会替换所有会话的内置目录。
- 目录 `slug` 必须和 TOML 的 `model` 全等（含前缀如 `x-ai/`）。
- `wire_api` 只有 `responses`（2026-02 起 `chat` 已移除，残留即启动失败）。
- 自定义目录整份替换该进程内置目录：先 `--bootstrap-bundled` 导出完整目录再追加。`model_catalog_json` 必须是绝对路径的专用文件（`<profile>-models.json`），禁用 `models.json`/`models_cache.json`。
- 工具字段语义见 [references/model-catalog-json.md](references/model-catalog-json.md)：默认去 `code_mode_only`、开 skills/plugin/apps 说明；空 `apply_patch`/`default` shell 补 `freeform`/`unified_exec`；`web_search` 缺省 `text`。Grok 例外：`apply_patch` 实测全失败则该条保持 `null`，`shell_type` 仍 `unified_exec`，`web_search` 仍 `text`。
- `support_verbosity` 仅上游官方文档化才开；不要跨供应商抄 `verbosity`。
- 密钥只用 `env_key`，本体进 `~/.config/models.env`（`600`），不进 TOML，不回显。
- 不要跑供应商 `curl|bash` / `irm|iex` 安装器，除非用户明确要求。
- 本地窗口不改变上游上限；未知 slug 回退约 `272000*95%≈258400`。

## 查询权威元数据

先查供应商官方，再写配置。

> 查：精确 slug、`base_url`、上下文窗口、思考档位（含 `max`）、`text.verbosity` 是否文档化、输入模态 / `tool_call` 能力。信息源与字段映射见 [references/model-info-sources.md](references/model-info-sources.md)。

优先级：用户给定 > 供应商官方 > 第三方目录初筛 > 本机 `models_cache.json`（仅克隆骨架）。官方与用户冲突时停下问。

查不到窗口/档位：用模板 `skill.codex-model-config` 默认值（`258400` + `low,medium,high,xhigh,max`，默认 `medium`）。`base_url`/slug 不可猜。写 catalog 仍只用本机 bundled/现有文件/cache，不拉外网（见 [references/catalog-source.md](references/catalog-source.md)）。

## 工作流

1. 收集：slug、`base_url`、env 名；窗口/档位有则用，无则 `--defaults`。同供应商多模型见 [references/workflow.md](references/workflow.md)（同窗口共享目录用 `--catalog-only`，窗口不同才分 profile）。
2. 官方值覆盖：`--context-window` / `--reasoning-levels`；`base_url`/slug 缺失则停下。
3. 建 profile：`init_profile.py`（模板全量替换）。提供方调优（`query_params`/headers/重试/超时/websockets）按需传参，见 [usage.md](usage.md)。
4. 写目录：`adjust_context_window.py --bootstrap-bundled --from-cache`。工具/模态覆盖（`--apply-patch-type`/`--web-search-type`/`--input-modalities`/`--supports-search-tool`）、同目录多模型（`--catalog-only`）、预览（`--dev`）见 [usage.md](usage.md)，语义见 [model-catalog-json.md](model-catalog-json.md)。
5. 只改必要顶层键和对应 `[model_providers.<id>]`。
6. 写入前 TOML/JSON 语法校验；失败中止。
7. 手写第三方配置先用 `check_profile.py` 扫必改项（空 `base_url` 回退 OpenAI 等），再 `debug models` 确认 slug、窗口、档位、工具字段（字段清单见 [model-catalog-json.md](model-catalog-json.md)），再用 `exec` 打一次真实请求确认网关不拒收（命令见 [usage.md](usage.md)）。
8. 重载客户端并开新对话。`--profile` 对 `doctor` 无效；切换提供方后另一组历史仅隐藏。

`--reasoning-levels` 写目录的 `supported_reasoning_levels`，当前档是 TOML 的 `model_reasoning_effort`。窗口公式见 [references/context-window-guide.md](references/context-window-guide.md)。

## 确认用户需求后执行配置

用户要求配置新模型、描述不全面时，先确认再执行；描述清晰可直接执行,否则正式执行前向用户展示配置方案。

建议用户参考的典型配置需求说明提示词(模板，可直接复制发给用户)：

> 请按下面补充配置新模型所需信息（必填 2 项，其余可空，不填用默认值）：

1. 模型 slug（必填，如 grok-4.6）：
2. base_url（必填，如 https://example.invalid/v1）：
3. provider id（可选，默认按模型系列推导，如 grok；勿用 openai/ollama/lmstudio）：
4. API Key（可选，给出则写入 ~/.config/models.env，不回显；TOML 只保留 env_key）：
5. env 变量名（可选，默认 `<PROVIDER>_API_KEY`）：
6. 上下文窗口/思考档（可选；有官方值填，无则按官方文档查，查不到用 258400 + low,medium,high,xhigh,max）：
7. 输入模态（可选，默认 text,image；按官方模态加 audio；本版 Codex 目录不支持 video）：
8. 工具偏好（可选，默认去 `code_mode_only`、`apply_patch=freeform`、`shell=unified_exec`、`web_search=text`；Grok 实测失败保持 null）：
9. 提供方调优（可选，如 "query_params/headers/重试/超时/websockets"，按需填）：
10. 生效范围（可选，默认新建 `~/.codex/<provider>.config.toml`；仅明确要求才 `--as-default` 覆盖默认 `config.toml`）：

收齐后我会先展示执行方案（含改哪份 TOML、目录 slug/窗口/档位/工具字段），你确认后再执行。

字段含义见 [references/model-info-sources.md](references/model-info-sources.md) 与 [references/model-catalog-json.md](references/model-catalog-json.md)；命令见 [references/usage.md](references/usage.md)。

## 参考索引

- 命令：[references/usage.md](references/usage.md)
- 顺序与字段分工：[references/workflow.md](references/workflow.md)
- 字段主次与兼容：[references/model-catalog-json.md](references/model-catalog-json.md)
- 工具调用（改文件/搜索三条路/依赖）：[references/tool-calling.md](references/tool-calling.md)
- 目录来源：[references/catalog-source.md](references/catalog-source.md)
- 模型信息源：[references/model-info-sources.md](references/model-info-sources.md)
- 窗口钳制：[references/context-window-guide.md](references/context-window-guide.md)
- 陷阱（含 Grok/verbosity/编码）：[references/常见陷阱.md](references/常见陷阱.md)
- 沙箱/审批：[references/codex-sandbox-permissions.md](references/codex-sandbox-permissions.md)
- 本 skill 开发规范：[references/dev-guide.md](references/dev-guide.md)
- 历史示例：[references/400k-context-setup配置指南.md](references/400k-context-setup配置指南.md)
- 配置案例：[references/case-xiaomi-mimo.md](references/case-xiaomi-mimo.md)
