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

供应商文档（例如 DeepSeek）给出的是完整接入形状，本 skill 保持同样流程，但不绑定单一供应商。

## 关键约束

- 先备份，再只改必要字段。MCP、`[projects.*]`、沙箱和审批策略一律保留。
- 新增模型时从 `references/template.config.toml` 生成 `~/.codex/<provider-id>.config.toml`。未指定 provider-id 则用模型系列名（`gpt` / `grok` / `deepseek` 等），全量替换占位符，不要只改第一处。
- 改真正设置 `model=model-name` 的那份 TOML。常见是 `~/.codex/<profile>.config.toml`，如果没有现成的`.toml`,则创建一份,而不是用 `config.toml`。如果把 `model_catalog_json` 写进默认配置，会替换每一个会话的内置目录(model_catalog),这可能不是用户想要的,影响面太大。
- 目录 `slug` 必须和 TOML 的 `model` 完全一致。例如`x-ai/grok-4.6` 不会作用于 `model = "grok-4.6"`。
- 一般第三方/自定义条目不要把 `apply_patch_tool_type` 留成 `null`，也不要把 `shell_type` 留成 `default`。`null` 时 Codex 不发 `apply_patch`，模型会改用 Python/shell 整文件重写，容易写丢，界面也没有 GPT 那种改文件摘要。追加或修复时设 `apply_patch_tool_type = "freeform"`；`shell_type` 为空或 `default` 时设 `"unified_exec"`。这只打开工具，不保证模型能用好 patch 格式。见 [references/workflow.md](references/workflow.md) 和 [references/常见陷阱.md](references/常见陷阱.md)。
- Grok 例外：本机实测 `apply_patch_tool_type = "freeform"` 时 Grok 会调用该工具，但 Codex 校验常报 `The first line of the patch must be '*** Begin Patch'`（rollout 里 `input` 第一行已经是该标记），然后退回 Python。此时 freeform 是负效率，Grok 条目保持 `null`，不要整份目录回滚。`shell_type` 仍用 `"unified_exec"`。`web_search_tool_type` 保持 `"text"`，不要抄 GPT 的 `"text_and_image"`。接线修好后再开 freeform。见 [references/常见陷阱.md](references/常见陷阱.md)。
- `support_verbosity` / `default_verbosity` 只表示 Codex 会不会发 `text.verbosity`，不等于上游真会控篇幅。这是 GPT-5 家族 Responses API 的能力。Grok 官方未文档化 `verbosity`，保持 `false` / `null`。DeepSeek 官方写该字段可传入但不生效，安装器目录里的 `true`/`low` 不要抄给 Grok。见 [references/常见陷阱.md](references/常见陷阱.md)。
- `model_catalog_json` 必须是绝对路径，指向 `~/.codex/<profile>-models.json` 这类专用文件。不要用 `~/.codex/models.json`（Codex 保留名，缺 `shell_type` 等字段会无法启动）。
- 自定义目录会替换该进程的内置目录。先用 `codex debug models --bundled` 引导完整目录再追加，不要写成只有一条模型。
- 追加第三方模型时不要原样克隆 bundled 第一行（现在常是 `gpt-6-astra`，`tool_mode=code_mode_only` 且 `include_skills_usage_instructions=false`）。那会让 shell/apply_patch/MCP/skills 从初始工具列表消失。脚本会改克隆直连工具骨架，去掉 `code_mode_only`，并把 bundled 新模型上多出来的未知键补到自定义条目（不覆盖工具行为）。字段怎么读见 [references/model-catalog-json.md](references/model-catalog-json.md)。
- 创建或修改 `model_catalog_json` 时，内容来自本机 bundled / 现有 `models.json` / `models_cache.json`，不是访问 OpenAI。不要为写 catalog 拉外网或探测本地代理。初学者说明见 [references/catalog-source.md](references/catalog-source.md)。
- 密钥用 `env_key`，不要写进 TOML。用户给出 API Key 时，写入 `~/.config/models.env`：文件不存在则创建（权限 `600`），已存在则追加 `KEY=value`；同名键更新该行。不要在回复里回显密钥。供应商文档里的 `experimental_bearer_token` 只作对照，不是默认。
- 不要运行供应商的 `curl | bash` / `irm | iex` 安装器，除非用户明确要求。那些脚本常改默认 `config.toml`，并可能用单供应商目录盖掉内置模型。
- 保留的提供方 id 不要占用：`openai`、`ollama`、`lmstudio`。`model_providers` 不能写在项目级 `.codex/config.toml`。
- 本地窗口数值不会改变上游真实上限。未知 slug 会回退到大约 `272000 * 95% ≈ 258400`。
- 配置指定模型时，先查供应商**官方**文档再写窗口和思考档位。查不到时用模板里 `skill.codex-model-config` 默认值（258400 上下文 + `low,medium,high,xhigh,max`，默认档 `medium`，部分档位上游可不可用）。不要编造比默认更大的窗口。本机 `models_cache.json` 只作目录克隆骨架。
- `codex --profile` 对 `doctor` 无效。校验目录用 `-c model_catalog_json=... debug models`，把 JSON 重定向到文件，不要管道进 Python heredoc。Windows PowerShell 不要用 `>`（会写成 UTF-16）。
- 配置按进程启动时加载。改完后重载客户端并开新对话。会话按认证方式分组，切换提供方后另一组历史会被隐藏，不是删除。

## 查询权威元数据

配置指定模型时联网查官方资料，再尝试写入。不要用二手博客或缓存数字冒充上游上限。

查这些：精确 slug、`base_url`、`wire_api`、上下文窗口、思考/推理档位（含是否支持 `max`）、官方是否文档化 `text.verbosity`。

来源优先级：用户已给的值 → 供应商官方 API / 模型文档 → 本机 `models_cache.json`（只克隆骨架，不证明窗口）。官方文档与缓存冲突时以官方为准；官方与用户冲突时停下来问。

查不到窗口或档位：用模板 `skill.codex-model-config` 默认值（`context_window=258400`，五档思考，`reasoning_effort=medium`），并告诉用户部分档位可能被上游忽略。官方明确更大窗口或更少档位时用 CLI 覆盖。`base_url` / slug 仍不能猜；缺这些才请用户核对。

写专用 catalog 仍只用本机 bundled / 现有文件 / cache，不要为写 catalog 去下载 OpenAI 或探测代理。细节见 [references/workflow.md](references/workflow.md)。

## 工作流

1. 收集用户已有的：模型 slug、`base_url`、环境变量名；窗口和档位若已给就用。未指定提供方 id 时，用模型系列名（`gpt` / `grok` / `deepseek` 等）作为 `provider-id`。若用户给了 API Key，写入 `~/.config/models.env`，不要写进 TOML。
2. 按「查询权威元数据」补全 `wire_api`、窗口、思考档位。不要猜 URL。窗口/档位无官方值时用 `--defaults`（或省略这些参数，脚本读取模板默认值）。未要求时不要改正在使用的默认模型。
3. 没有现成 profile 时，优先跑 `scripts/init_profile.py`。`adjust_context_window.py --profile <id>` 若发现 TOML 不存在，也会从模板新建（建议同时传 `--base-url`）。不要改默认 `config.toml`。已有文件则备份后再改。
4. 写目录：完整 bundled + 自定义条目。简便写法：`adjust_context_window.py --defaults --bootstrap-bundled --from-cache --profile <id> --model <slug> --yes`。官方值用 `--context-window` / `--reasoning-levels` 覆盖。脚本会把空的 `apply_patch_tool_type` / `default` shell 补成 `freeform` / `unified_exec`，不要沿用缓存空值。
5. 只改必要的顶层键和对应的 `[model_providers.<id>]`。
6. 写入前用 TOML/JSON 语法校验；失败则中止。
7. 用 `debug models` 确认 slug、窗口、`supported_reasoning_levels`、`apply_patch_tool_type`、`shell_type`。
8. 用正确的 profile 开新会话，并重载 VS Code / 桌面端。

`--reasoning-levels` 只写入 `models.json` 的 `supported_reasoning_levels`（选择器能选哪些档）。当前用哪一档是 profile TOML 的 `model_reasoning_effort`（`--reasoning-effort` / `init_profile.py`）。目录默认档是 `default_reasoning_level`。模板里 `skill.codex-model-config` 注释块只给本 skill 读默认值，CLI 不会改模板本身。

新建 profile 时优先跑 `scripts/init_profile.py`（全量替换模板里的 `provider-id` / `model-id`）。完整步骤见 [references/workflow.md](references/workflow.md)。 若要把该 profile 变成默认会话配置，加 `--as-default`：先备份 `~/.codex/config.toml`，再把 profile 复制为 `config.toml`。`adjust_context_window.py --profile <id> --as-default` 同样在改完窗口/目录后提升为默认。

窗口公式、目录引导和 compact 阈值见 [references/context-window-guide.md](references/context-window-guide.md)。

catalog 文件从哪来（bundled、缓存、为何不是 OpenAI 下载）见 [references/catalog-source.md](references/catalog-source.md)。字段主次见 [references/model-catalog-json.md](references/model-catalog-json.md)。

profile / slug / 安装器类错误见 [references/常见陷阱.md](references/常见陷阱.md)。

git / `.git` 写不进、命令要外网、或 `index.lock` Permission denied：见 [references/codex-sandbox-permissions.md](references/codex-sandbox-permissions.md)。那是沙箱和审批，不是模型 profile。

[references/400k-context-setup配置指南.md](references/400k-context-setup配置指南.md) 只是 DeepSeek 400K 的一份已验证示例，不是唯一目标。

## 新建 profile

Windows 用 `python`（不要 `python3`），续行用反引号；脚本会按当前 OS 打印后续命令。PowerShell 里 CSV 必须加引号：`--reasoning-levels "low,medium,high,xhigh"`。`--bootstrap-bundled` 依赖 PATH 上的 `codex.cmd`/`codex.exe`，不是 `codex.ps1`。完整 PowerShell 流程见 [README.md](README.md)。

未指定 `--provider` 时，用模型系列作为 id 和文件名：

```bash
python3 scripts/init_profile.py --model grok-4.6 --base-url https://example.invalid/v1 --wire-api responses --yes
```

```powershell
python scripts\init_profile.py --model grok-4.6 --base-url https://example.invalid/v1 --wire-api responses --yes
```

显式指定提供方（例如已有中转站名）：

```bash
python3 scripts/init_profile.py --model grok-4.6 --provider yjwd-grok --base-url https://yujianwudi.net/v1 --env-key YUJIANWUDI_GROK_API_KEY --yes
```

```powershell
python scripts\init_profile.py --model grok-4.6 --provider yjwd-grok --base-url https://yujianwudi.net/v1 --env-key YUJIANWUDI_GROK_API_KEY --yes
```

这会写入 `~/.codex/<provider-id>.config.toml`。已存在则拒绝覆盖，除非 `--force`。窗口和目录仍用下面的脚本补。

## 上下文窗口脚本

模型已在默认配置和 `models.json` 里时：

```bash
python3 scripts/adjust_context_window.py \
  --model deepseek-v4-flash-vision-exp \
  --context-window 400000 \
  --compact-percent 90 \
  --yes
```

```powershell
python scripts\adjust_context_window.py `
  --model deepseek-v4-flash-vision-exp `
  --context-window 400000 `
  --compact-percent 90 `
  --yes
```

模型在 profile 里，且目录还没有这条时。查不到官方窗口/档位就用 `--defaults`（258400 + 五档）：

```bash
python3 scripts/adjust_context_window.py --model grok-4.6 --profile yjwd-grok --bootstrap-bundled --from-cache --defaults --yes
```

```powershell
python scripts/adjust_context_window.py --model grok-4.6 --profile yjwd-grok --bootstrap-bundled --from-cache --defaults --yes
```

官方值覆盖默认：

```bash
python3 scripts/adjust_context_window.py --model grok-4.6 --profile yjwd-grok --bootstrap-bundled --from-cache --context-window <n> --reasoning-levels low,medium,high,xhigh --yes
```

除非传入 `--force`，否则 `model=` 对不上时，脚本会拒绝写入默认 `config.toml`。提供方段落仍需按 [workflow.md](references/workflow.md) 手工核对。脚本改窗口、思考档和目录路径；若目标条目的 `apply_patch_tool_type` 为空或 `shell_type` 为 `default`，同时改成 `freeform` / `unified_exec`。
