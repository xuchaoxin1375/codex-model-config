# Codex 模型接入流程

流程形状对齐 [DeepSeek 的 Codex 接入文档](https://api-docs.deepseek.com/zh-cn/quick_start/agent_integrations/codex/)，但保持供应商无关。不要把 DeepSeek 示例原样当成唯一正确配置。

## 何时读本文

用户要「接入 / 切换 / 配好」某个 Codex 模型时读本文。若任务只是把已接通模型的窗口从 258400 抬上去，改读 [context-window-guide.md](context-window-guide.md)。还不清楚 `models.json` 从哪来、要不要访问 OpenAI 时，先读 [catalog-source.md](catalog-source.md)。

## 收集输入

动手前先对齐这些值；缺一项就停，不要猜提供方 URL 或模型名。

| 项 | 写到哪里 | 注意 |
|---|---|---|
| 模型 slug | TOML `model` 与目录 `slug` | 必须全等，含大小写和 `/` |
| 提供方 id | `model_provider` 与 `[model_providers.<id>]` | 未指定则用模型系列名（`gpt` / `grok` / `deepseek` 等）。不要用 `openai` / `ollama` / `lmstudio` |
| `base_url` | 提供方段 | 按供应商文档，不要擅自加或删 `/v1` |
| `wire_api` | 提供方段 | Codex 常用 `responses`；供应商若只给 Chat Completions 才用 `chat` |
| 密钥 | `~/.config/models.env` 的 `KEY=value`，TOML 只写 `env_key` 名 | 用户给了 key 就写入该文件：没有则创建，有则追加；不要写进 TOML，不要回显 |
| 目标窗口 | TOML + 目录 | 先查官方文档；不确定就问用户，不要猜 |
| 思考档位 | 见下方「档位写到哪」 | 查不到用模板默认五档；官方更少档位再用 `--reasoning-levels` 覆盖 |
| 配置文件 | 默认 `config.toml` 或 `~/.codex/<profile>.config.toml` | 新模型默认新建 profile；看哪份文件真正设置了 `model=` |
| 是否改默认模型 | 用户明确要求才改默认 `config.toml` 的 `model=` | 多 profile 用户通常应新建或编辑 profile |

未要求时不要覆盖用户正在用的默认模型。本机若默认是另一家提供方，第三方模型应放进 profile。

## 查询权威元数据

coding agent 配指定模型时，**先联网查官方文档，再写配置**。这与「不要为写 catalog 去下载 OpenAI 目录」不冲突：查的是模型规格，catalog JSON 仍从本机 bundled / 现有文件 / `models_cache.json` 克隆。

### 查什么

- 接口使用的精确 slug（是否带 `x-ai/` 这类前缀；TOML `model` 与目录 `slug` 仍必须全等）
- `base_url`、`wire_api`（`responses` 或 `chat`）
- 上下文窗口（token）
- 思考/推理档位：官方接受哪些 effort，默认档，有没有 `max`

### 来源优先级

1. 用户已经明确给出的值
2. 供应商官方 API 文档 / 模型页（搜索时优先官网、官方 docs，不要用来源不明的博客数字）
3. 本机 `~/.codex/models_cache.json`：只当克隆模板（显示名、`input_modalities`、其余字段），**不当**窗口和档位的证明

官方与缓存冲突 → 用官方，克隆后覆盖窗口/档位字段。官方与用户冲突 → 停下来问。

### 不确定时

`base_url` 和精确 slug 仍不能猜，缺了就请用户核对官方文档。

窗口和思考档位查不到时，**不要编造更大的数**。改用模板里本 skill 识读的默认块 `skill.codex-model-config`：

- `context_window = 258400`（主流模型至少这个量级）
- `reasoning_levels = ["low", "medium", "high", "xhigh", "max"]`（部分档位上游可不可用）
- `reasoning_effort = "medium"`

简便写法：`--defaults`（或不传窗口/档位参数，脚本自己读模板）。

官方明确更大窗口或更少档位时再覆盖：

```bash
python3 scripts/init_profile.py --model <slug> --base-url <url> --defaults --yes
python3 scripts/adjust_context_window.py --model <slug> --profile <id> --bootstrap-bundled --from-cache --defaults --yes
```

```bash
python3 scripts/adjust_context_window.py --model <slug> --profile <id> --bootstrap-bundled --from-cache --context-window <n> --reasoning-levels low,high,max --yes
```

Windows 把 `python3` 换成 `python`。

## 标准顺序

DeepSeek 安装器的有效部分是这四步。本 skill 手动做同样的事，但默认写 profile、用环境变量、保留完整目录。

1. **确定 profile**。新模型默认新建 `~/.codex/<provider-id>.config.toml`，不要改正在用的默认 `config.toml`。未指定 `provider-id` 时，用模型系列名（见下方）。
2. **备份**将要改的 TOML 和已有 `models.json`。时间戳副本写在原文件旁边即可。
3. **从模板生成或更新 profile**。没有现成文件时，用 `scripts/init_profile.py` 全量替换 [template.config.toml](template.config.toml) 里的 `provider-id` 和 `model-id`。已有文件则只改必要字段，保留 MCP、`[projects.*]`、沙箱和审批。
4. **写模型目录** `~/.codex/models.json`（或用户指定的绝对路径）：向 Codex 声明 slug、窗口、推理档位、`input_modalities` 等。文件从本机 bundled / 现有 JSON / 缓存来，不是访问 OpenAI；见 [catalog-source.md](catalog-source.md)。
5. **写入前校验** TOML 与 JSON 语法。失败则中止，不覆盖原文件。

不要运行：

```bash
bash <(curl -fsSL https://cdn.deepseek.com/api-docs/codex-deepseek-setup.sh)
```

除非用户明确要求执行某家供应商的安装器。

## 从模板新建 profile

添加模型时，对应新增一份用户级 profile(创建或修改`profile-name.config.toml`)，而不是把新 `model=model-name` 写进默认 `config.toml`。

模板：[template.config.toml](template.config.toml)

占位符必须**全量替换**（文件名、`model_provider`、`[model_providers.<id>]`、`name` 用同一个 id）：

| 占位符 | 替换为 |
|---|---|
| `provider-id` | 用户指定的提供方 id；未指定则用模型系列名 |
| `model-id` | TOML 里的 `model` slug，必须和目录 `slug` 一致 |
| `base_url = ""` | 供应商文档中的接口地址，不能留空 |
| `env_key = "API_KEY"` | 默认 `<PROVIDER_ID>_API_KEY`（`-` 变 `_` 再大写）。密钥本体写入 `~/.config/models.env` |

系列名取模型 slug 最后一段的前缀（忽略 `x-ai/` 这类供应商前缀）：

| 模型例子 | 系列 / provider-id |
|---|---|
| `gpt-5.6-sol`、`o3-mini` | `gpt` |
| `grok-4.6`、`x-ai/grok-4.6` | `grok` |
| `deepseek-v4-flash` | `deepseek` |
| `claude-opus-4-6` | `claude` |
| 未识别 | 最后一段里第一个 `-` / `_` / `.` 之前的 token |

不要用保留 id：`openai`、`ollama`、`lmstudio`。例如,OpenAI 兼容的 GPT 模型用 `gpt`，不要用 `openai`。

优先用脚本，避免漏替换：

```bash
python3 scripts/init_profile.py --model grok-4.6 --base-url https://example.invalid/v1 --yes
```

写出 `~/.codex/grok.config.toml`，启动：`codex --profile grok`。

已有中转站名时显式传入：

```bash
python3 scripts/init_profile.py --model grok-4.6 --provider yjwd-grok --base-url https://yujianwudi.net/v1 --env-key YUJIANWUDI_GROK_API_KEY --yes
```

目标文件已存在则拒绝覆盖，除非 `--force`。脚本不写 `model_catalog_json`，窗口和目录仍按后文补。

手工复制模板时，不要只改第一处 `provider-id`。`base_url` 留空会在启动时报 builder error。

## 保存 API Key

用户给出 API Key 时，默认写入 `~/.config/models.env`：

- 文件不存在：创建，权限 `600`，写入 `ENV_KEY=value`
- 文件已存在：在末尾追加一行
- 同名键已存在：更新该行，避免重复定义
- 格式与现有文件一致：`KEY=value`，不要 `export`，不要把密钥写进 TOML 或对话回复

```bash
python3 scripts/init_profile.py --model grok-4.6 --base-url https://example.invalid/v1 --api-key '<user-key>' --yes
```

```powershell
python scripts\init_profile.py --model grok-4.6 --base-url https://example.invalid/v1 --api-key '<user-key>' --yes
```

脚本日志只打印「写入了哪个变量名和路径」，不打印密钥。Codex 从进程环境读取 `env_key`，因此启动前需要加载该文件，例如：

```bash
set -a && . ~/.config/models.env && set +a
```

```powershell
$envFile = Join-Path $env:USERPROFILE ".config\models.env"
Get-Content -LiteralPath $envFile | ForEach-Object {
  if ($_ -match '^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
    Set-Item -Path "Env:$($Matches[1])" -Value $Matches[2].Trim().Trim('"').Trim("'")
  }
}
```

不要擅自改 shell rc。未给密钥时不要动 `models.env`。


## 推荐 TOML 形状


```toml
model = "<slug>"
model_provider = "<id>"
preferred_auth_method = "apikey"
model_reasoning_effort = "medium"
model_catalog_json = "/absolute/path/to/models.json"

[model_providers.<id>]
name = "<id>"
base_url = "https://example.invalid/v1"
wire_api = "responses"
env_key = "<ENV_VAR>"
```

按需补充：

- `forced_login_method = "api"`：跳过 ChatGPT 登录提示时可用。
- `model_context_window` 与 `model_auto_compact_token_limit`：要自定义窗口时再写；字段含义见 [context-window-guide.md](context-window-guide.md)。
- `[model_providers.<id>.auth]`：`command` + `args` 从环境或本机命令取密钥，适合不想用 `env_key` 的情况。

DeepSeek 文档的差异（对照用，不是默认）：

- `experimental_bearer_token` 把密钥写进文件。本 skill 默认改成 `env_key`。
- `model_catalog_json = "~/.codex/models.json"` 对部分客户端不稳定。改成绝对路径。
- 其示例 `base_url = "https://api.deepseek.com/"`、`wire_api = "responses"` 对 DeepSeek 官方接口有效；其他中转站以该站文档为准。
- 官方 flash 目录示例曾用 `context_window: 1048576` 且 `effective_context_window_percent: 95`。那是名义窗口再打折；若要精确命中用户目标，把 `context_window` 和 `max_context_window` 都设成目标，并把百分比设为 `100`。

## 目录元数据

初学者先读 [catalog-source.md](catalog-source.md)：`model_catalog_json` 只是本地文件的绝对路径；内容从 Codex 自带的 bundled 目录导出，再追加自定义模型，**不会**去下载 OpenAI 目录，也不需要代理。

自定义目录必须是：

```json
{
  "models": [
    { "slug": "my-model", "display_name": "My Model" }
  ]
}
```

没有 `models.json` 时，从**本机**内置目录导出（不访问外网）：

```bash
codex debug models --bundled > ~/.codex/models.json
```

然后追加自定义对象，不要用只含一个模型的文件替换。`model_catalog_json` 会替换该进程的整份内置目录。

克隆来源优先级：

1. 现有 `models.json` 里的同 slug 条目
2. `--clone-from` 指定的条目
3. `~/.codex/models_cache.json` 里精确匹配，或唯一的 `*/slug` 后缀匹配
4. 克隆后把 `slug` 改成 TOML 里的 `model` 值

不要手写一份完整 DeepSeek/OpenAI 目录。保留克隆来的其余字段，只改当前任务需要的键。

常改字段：

| 字段 | 作用 |
|---|---|
| `slug` | 必须等于 TOML `model` |
| `display_name` | 选择器显示名 |
| `context_window` | 目录声明的基础窗口 |
| `max_context_window` | `model_context_window` 能达到的上限 |
| `effective_context_window_percent` | 钳制后真正可用的百分比 |
| `auto_compact_token_limit` | 模型自己的压缩上限；通常留 `null`，改由 TOML 决定 |
| `supported_reasoning_levels` | UI 能选的思考档；由 `--reasoning-levels` 写入，例如 `low,high,xhigh` |
| `default_reasoning_level` | 未手动选择时的目录默认档；由 `--default-reasoning-level` 写入 |
| `input_modalities` | 含 `image` 时 Codex 才认为该模型能收图 |

视觉模型：目录里没有 `image` 时，即使用户能贴图，Codex 也不会按视觉模型处理。

## 该改哪份文件

| 场景 | 文件 |
|---|---|
| 新增模型，用户没说改全局默认 | 从模板新建 `~/.codex/<provider-id>.config.toml` |
| 用户要把该模型设成全局默认 | `~/.codex/config.toml` |
| 用户已有或希望用 `codex --profile <name>` | `~/.codex/<name>.config.toml` |
| 只改窗口，且 `model=` 已在某 profile | 只改那份 profile，外加 `models.json` |

`model_providers` 只能写在用户级配置。项目目录里的 `.codex/config.toml` 不能承载提供方定义。

CLI、ChatGPT 桌面端、VS Code Codex 插件读同一份用户配置，不用配三份。改完后三个客户端都要重载或新开进程。

## 校验

写入前：

```bash
python3 -c 'import tomllib, pathlib, sys; tomllib.loads(pathlib.Path(sys.argv[1]).read_text())' /path/to/config.toml
python3 -c 'import json, pathlib, sys; json.loads(pathlib.Path(sys.argv[1]).read_text())' /path/to/models.json
```

默认配置语法：

```bash
codex --strict-config doctor
```

应看到 `config.toml parse ok`。`codex --profile` 不能搭配 `doctor`。

目录是否加载、slug 是否命中：

```bash
codex -c model_catalog_json='"/home/<user>/.codex/models.json"' debug models > /tmp/codex-models-debug.json
```

把 JSON 重定向到文件再查。不要把 `codex debug models` 管道进 Python heredoc，heredoc 会吃掉 stdin。

```bash
python3 -c 'import json; from pathlib import Path; data=json.loads(Path("/tmp/codex-models-debug.json").read_text()); m=next(x for x in data["models"] if x["slug"]=="<slug>"); print({k:m.get(k) for k in ["slug","display_name","context_window","max_context_window","effective_context_window_percent","input_modalities"]})'
```

实际会话：

```bash
codex --profile <name>
```

启动信息里的 `model:` 应等于配置的 slug。

VS Code / 桌面端：`Ctrl+Shift+P` → `Developer: Reload Window`（或完全退出桌面端），然后开新对话。旧会话和已在跑的 app-server 仍用启动时的目录。

## 客户端与历史会话

配置一次，三种客户端共用。桌面端模型选择器可能显示「自定义」，这通常表示正在用你配置的第三方模型，不一定会显示供应商品牌名。

Codex 按认证方式分组存放会话。从 ChatGPT 登录切到 API Key（或在两家提供方之间切换）后，界面只显示与当前认证匹配的那一组。另一组没有被删除；改回原来的认证/提供方并重启客户端就会再出现。

## 窗口子任务

提供方已经接通、只需抬窗口时，优先：

```bash
python3 scripts/adjust_context_window.py \
  --model <slug> \
  --context-window <n> \
  --profile <name> \
  --bootstrap-bundled \
  --from-cache \
  --yes
```

该脚本改窗口相关键，以及思考档位（见「档位写到哪」）。它不会创建 `[model_providers.<id>]`，也不会设置 `env_key`。窗口和档位：有官方值就覆盖，没有就用模板默认。

## 档位写到哪

`--reasoning-levels low,high,xhigh` 这类改动**不会**写进 TOML 的列表字段（TOML 没有档位列表）。落实位置：

| CLI | 写入文件 | 字段 | 作用 |
|---|---|---|---|
| `--reasoning-levels` | `~/.codex/models.json`（或 `--catalog`） | `supported_reasoning_levels` | 选择器里能选哪些档 |
| `--default-reasoning-level` | 同上 | `default_reasoning_level` | 未手动选时的目录默认档；若不在 `--reasoning-levels` 里，改成列表第一项 |
| `--reasoning-effort` | `~/.codex/<profile>.config.toml` | `model_reasoning_effort` | **这次请求实际用哪一档** |
| `init_profile.py --reasoning-effort` | 新建的 profile TOML | `model_reasoning_effort` | 同上；`init_profile.py` 不写档位列表 |
| 模板 `skill.codex-model-config` 注释块 | `references/template.config.toml`（复制进 profile 仍是注释） | `reasoning_levels` 等 | 只给本 skill / 脚本读默认值；Codex 不解析；CLI 覆盖不会改模板本身 |

校验选择器档位：看 `debug models` 里该 slug 的 `supported_reasoning_levels`。校验当前请求档位：看 profile 里的 `model_reasoning_effort`。
