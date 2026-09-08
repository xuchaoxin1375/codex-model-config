---
name: codex-model-config
description: >
  为 Codex 端到端配置自定义或第三方模型：提供方端点、API Key 环境变量、
  models.json 目录、上下文窗口，以及哪份 profile TOML 持有 model=model-name。

  适用于：新增或切换 model_providers、写入目录元数据、设置 model_catalog_json，
  或让指定上下文窗口真正生效，包括模型写在 Codex profile 里、或 models.json 中缺失的情况。

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
- `model_catalog_json` 必须是绝对路径。`~/.codex/models.json` 这种写法在部分客户端不可靠。
- 自定义目录会替换该进程的内置目录。先用 `codex debug models --bundled` 引导完整目录再追加，不要写成只有一条模型。
- 创建或修改 `model_catalog_json` 时，内容来自本机 bundled / 现有 `models.json` / `models_cache.json`，不是访问 OpenAI。不要为写 catalog 拉外网或探测本地代理。初学者说明见 [references/catalog-source.md](references/catalog-source.md)。
- 密钥用 `env_key`，不要写进 TOML。用户给出 API Key 时，写入 `~/.config/models.env`：文件不存在则创建（权限 `600`），已存在则追加 `KEY=value`；同名键更新该行。不要在回复里回显密钥。供应商文档里的 `experimental_bearer_token` 只作对照，不是默认。
- 不要运行供应商的 `curl | bash` / `irm | iex` 安装器，除非用户明确要求。那些脚本常改默认 `config.toml`，并可能用单供应商目录盖掉内置模型。
- 保留的提供方 id 不要占用：`openai`、`ollama`、`lmstudio`。`model_providers` 不能写在项目级 `.codex/config.toml`。
- 本地窗口数值不会改变上游真实上限。未知 slug 会回退到大约 `272000 * 95% ≈ 258400`。
- `codex --profile` 对 `doctor` 无效。校验目录用 `-c model_catalog_json=... debug models`，把 JSON 重定向到文件，不要管道进 Python heredoc。
- 配置按进程启动时加载。改完后重载客户端并开新对话。会话按认证方式分组，切换提供方后另一组历史会被隐藏，不是删除。

## 工作流

1. 收集：模型 slug、`base_url`、`wire_api`、环境变量名、目标窗口（若有）。未指定提供方 id 时，用模型系列名（`gpt` / `grok` / `deepseek` 等）作为 `provider-id`。若用户给了 API Key，写入 `~/.config/models.env`，不要写进 TOML。
2. 确认上游确实提供该模型和窗口；未要求时不要改正在使用的默认模型。
3. 没有现成 profile 时，从 [references/template.config.toml](references/template.config.toml) 新建 `~/.codex/<provider-id>.config.toml`，不要改默认 `config.toml`。已有文件则备份后再改。
4. 写入或追加目录元数据（完整 bundled 目录 + 自定义条目）。
5. 只改必要的顶层键和对应的 `[model_providers.<id>]`。
6. 写入前用 TOML/JSON 语法校验；失败则中止。
7. 用 `debug models` 确认 slug 与窗口；需要上下文时再跑窗口脚本。
8. 用正确的 profile 开新会话，并重载 VS Code / 桌面端。

新建 profile 时优先跑 `scripts/init_profile.py`（全量替换模板里的 `provider-id` / `model-id`）。完整步骤见 [references/workflow.md](references/workflow.md)。

窗口公式、目录引导和 compact 阈值见 [references/context-window-guide.md](references/context-window-guide.md)。

catalog 文件从哪来（bundled、缓存、为何不是 OpenAI 下载）见 [references/catalog-source.md](references/catalog-source.md)。

profile / slug / 安装器类错误见 [references/常见陷阱.md](references/常见陷阱.md)。

[references/400k-context-setup配置指南.md](references/400k-context-setup配置指南.md) 只是 DeepSeek 400K 的一份已验证示例，不是唯一目标。

## 新建 profile

未指定 `--provider` 时，用模型系列作为 id 和文件名：

```bash
python3 scripts/init_profile.py --model grok-4.6 --base-url https://example.invalid/v1 --yes
```

显式指定提供方（例如已有中转站名）：

```bash
python3 scripts/init_profile.py --model grok-4.6 --provider yjwd-grok --base-url https://yujianwudi.net/v1 --env-key YUJIANWUDI_GROK_API_KEY --yes
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

模型在 profile 里，且目录还没有这条时：

```bash
python3 scripts/adjust_context_window.py \
  --model grok-4.6 \
  --context-window 500000 \
  --profile yjwd-grok \
  --bootstrap-bundled \
  --from-cache \
  --yes
```

除非传入 `--force`，否则 `model=` 对不上时，脚本会拒绝写入默认 `config.toml`。提供方段落仍需按 [workflow.md](references/workflow.md) 手工核对，脚本只改窗口相关键。
