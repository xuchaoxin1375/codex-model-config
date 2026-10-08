# Codex 模型接入流程

流程形状对齐 DeepSeek 的 Codex 接入文档，但保持供应商无关。命令见 [usage.md](usage.md)，字段语义见 [model-catalog-json.md](model-catalog-json.md)。本文只保留顺序与分工。

## 何时读本文

要「接入 / 切换 / 配好」某个模型时读。若只是抬窗口，重点看 [context-window-guide.md](context-window-guide.md)；不清楚目录来源先看 [catalog-source.md](catalog-source.md)。

## 收集输入

缺一项就停，不要猜 URL 或模型名。

| 项 | 写到哪里 | 注意 |
|---|---|---|
| 模型 slug | TOML `model` 与目录 `slug` | 必须全等 |
| 提供方 id | `model_provider` 与 `[model_providers.<id>]` | 未指定用模型系列名；禁用 `openai`/`ollama`/`lmstudio` |
| `base_url` | 提供方段 | 按供应商文档，不擅自加减 `/v1` |
| `wire_api` | 提供方段 | 只有 `responses` |
| 密钥 | `~/.config/models.env`，TOML 只写 `env_key` | 不进 TOML，不回显 |
| 目标窗口/档位 | TOML + 目录 | 先查官方；查不到用 `--defaults` |
| 配置文件 | 默认或 `<profile>.config.toml` | 新模型默认新建 profile |
| 是否改默认 | 用户明确要求才动默认 `config.toml` | 否则只动 profile |

## 查询权威元数据

查：精确 slug、`base_url`、窗口、思考档位（含 `max`）、`text.verbosity` 是否文档化、输入模态 / `tool_call`。信息源与字段映射见 [model-info-sources.md](model-info-sources.md)。优先级：用户 > 官方 > 第三方初筛 > `models_cache.json`（仅骨架）。官方与用户冲突停下问。

窗口/档位查不到用模板 `skill.codex-model-config` 默认值；`base_url`/slug 不可猜。写 catalog 仍只用本机数据。

## 标准顺序

1. 定 profile：新模型默认新建 `~/.codex/<provider-id>.config.toml`。
2. 备份 TOML 与已有 `<profile>-models.json`。
3. `init_profile.py` 生成/更新 profile（全量替换 `provider-id`/`model-id`，`base_url` 不可空）。
4. `adjust_context_window.py` 写目录（完整 bundled + 自定义条目）。
5. 写入前校验 TOML/JSON 语法。

不要跑供应商安装器，除非用户明确要求。

## 从模板新建 profile

占位符必须全量替换：`provider-id`、`model-id`、`base_url`、`env_key`（默认 `<PROVIDER>_API_KEY`）。系列名取 slug 最后一段前缀（`grok-4.6`→`grok` 等）。命令见 [usage.md](usage.md)。

## 保存 API Key

`~/.config/models.env`：无则创建（`600`）、有则追加、同名更新该行。日志只打印变量名与路径。启动前加载该文件（片段见 [usage.md](usage.md)）。

## 推荐 TOML 形状

```toml
model = "<slug>"
model_provider = "<id>"
preferred_auth_method = "apikey"
model_reasoning_effort = "medium"
model_catalog_json = "/absolute/path/to/<profile>-models.json"

[model_providers.<id>]
name = "<id>"
base_url = "https://example.invalid/v1"
wire_api = "responses"
env_key = "<ENV_VAR>"
```

按需：`forced_login_method="api"`、`model_context_window`/`model_auto_compact_token_limit`、`query_params`/headers/重试/超时（`init_profile.py` 参数）、`auth.command`。供应商差异对照见 git 历史，不在此展开。

## 目录元数据

唯一说明在 [model-catalog-json.md](model-catalog-json.md)。此处只记分工：骨架克隆直连工具行（去 `code_mode_only`、开三套 `include_*`），`slug` 改成 TOML 值，工具/模态覆盖经 CLI 显式传参，不跨供应商抄 `verbosity`/`web_search`。

## 该改哪份文件

| 场景 | 文件 |
|---|---|
| 新增模型 | `~/.codex/<provider-id>.config.toml` |
| 设全局默认（`--as-default`） | `~/.codex/config.toml` |
| 用 `--profile` | `~/.codex/<name>.config.toml` |
| 只改窗口 | 该 profile + `models.json` |

`model_providers` 不可写项目 `.codex/config.toml`。三客户端共用用户配置，改完重载并开新会话。

## 同供应商多模型（选择器内可切换）

一家供应商多个可用模型（如 `mimo-v2.5` + `mimo-v2.5-pro`）时，推荐做法：**一个 profile，一份目录放多条**，选择器内直接切换。TOML 里 `model` 只是默认项，目录里每条独立 carrying 各自的窗口、档位、工具偏好。

做法：第一个模型正常跑完 `init_profile.py` + `adjust_context_window.py`；之后每个模型只跑 `adjust_context_window.py --catalog-only`（只增改目录条目，不碰 TOML，`model=` 对不上也不会报错）。命令见 [usage.md](usage.md)。

例外：两个模型窗口差距大、且你希望各用各的压缩阈值时，才各建一个 profile（各持一份目录）。不要用 `--force` 把第二个模型塞进第一个 profile——窗口键会被写到错的模型上。

## 校验

命令见 [usage.md](usage.md)：`doctor` 查默认配置，`debug models` 查目录，`--profile` 开会话。不要管道 heredoc，不要 `--profile doctor`。

## 档位写到哪

| CLI | 写入文件 | 字段 |
|---|---|---|
| `--reasoning-levels` | 目录 JSON | `supported_reasoning_levels` |
| `--default-reasoning-level` | 目录 JSON | `default_reasoning_level` |
| `--reasoning-effort` | profile TOML | `model_reasoning_effort` |
| 模板注释块 | 仅 skill 读默认 | Codex 不解析 |
