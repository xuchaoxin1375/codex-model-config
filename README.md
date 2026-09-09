# Codex 模型配置 Skill

把自定义或第三方模型接到 Codex：提供方、目录元数据、上下文窗口。CLI、ChatGPT 桌面端和 VS Code Codex 插件共用同一份用户配置。

Python 脚本跨平台。跑完后会按当前 OS 打印后续命令：Unix shell 用 bash 写法，Windows 用 PowerShell 写法。给 Codex 的硬规则以 `SKILL.md` 为准。

## 目录

| 路径 | 作用 |
|---|---|
| `SKILL.md` | skill 入口：何时用、硬约束、工作流 |
| `agents/openai.yaml` | Codex UI 展示名与默认提示 |
| `scripts/init_profile.py` | 从模板新建 `~/.codex/<provider>.config.toml` |
| `scripts/adjust_context_window.py` | 改窗口、目录条目、`model_catalog_json` |
| `scripts/shell_hints.py` | 按 OS 打印后续命令 |
| `references/template.config.toml` | profile 模板（含 Unix / PowerShell `auth.command`） |
| `references/workflow.md` | 完整接入顺序 |
| `references/catalog-source.md` | `models.json` 从哪来（本机 bundled，不是下载 OpenAI） |
| `references/model-catalog-json.md` | `model_catalog_json` 怎么读：字段主次、工具坑、升级兼容 |
| `references/context-window-guide.md` | 窗口如何被目录钳制 |
| `references/常见陷阱.md` | 改错文件 / slug / 安装器 |
| `references/codex-sandbox-permissions.md` | Codex 沙箱 / 审批：CLI 与 config.toml |
| `references/400k-context-setup配置指南.md` | DeepSeek 400K 已验证示例，不是唯一目标 |

## Shell 差异

两边都需要 **Python 3.11+**（脚本用 `tomllib`）。`~` 在 Python 里会扩成用户主目录；写进 TOML 的 `model_catalog_json` 必须是**绝对路径**，推荐正斜杠，例如 `/home/<user>/.codex/yjwd-grok-models.json` 或 `C:/Users/<user>/.codex/yjwd-grok-models.json`。不要指向 Codex 保留的 `~/.codex/models.json`。

### Unix shell

- 解释器一般是 `python3`。
- 用户配置：`~/.codex/`；密钥：`~/.config/models.env`。
- 续行用 `\`。重定向 `>` 通常是 UTF-8，可用来写 JSON。
- 临时文件常用 `/tmp/...`。
- 新建 `models.env` 时脚本会 `chmod 600`。

```bash
python3 scripts/init_profile.py --model grok-4.6 --base-url https://example.invalid/v1 --yes
set -a && . ~/.config/models.env && set +a
export HTTPS_PROXY=http://127.0.0.1:7897
codex debug models --bundled > ~/.codex/yjwd-grok-models.json
```

### PowerShell

- 解释器一般是 `python`，不要写 `python3`。
- 用户配置：`$env:USERPROFILE\.codex`；密钥：`$env:USERPROFILE\.config\models.env`。
- 续行用反引号 `` ` ``。
- **不要用 `>` 重定向 JSON / TOML**：Windows PowerShell 5.x 会写成 UTF-16，Codex 读不了。改用 Python 写文件，或 `[IO.File]::WriteAllText`。
- 临时文件用 `$env:TEMP`。
- `chmod 600` 不能映射成 NTFS ACL，脚本会忽略失败。

```powershell
python scripts\init_profile.py --model grok-4.6 --base-url https://example.invalid/v1 --yes
$env:HTTPS_PROXY = "http://127.0.0.1:7897"
```

加载当前会话的 `models.env`：

```powershell
$envFile = Join-Path $env:USERPROFILE ".config\models.env"
Get-Content -LiteralPath $envFile | ForEach-Object {
  if ($_ -match '^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
    Set-Item -Path "Env:$($Matches[1])" -Value $Matches[2].Trim().Trim('"').Trim("'")
  }
}
```

导出 bundled 目录（避免 `>`）：

```powershell
python scripts\adjust_context_window.py --model grok-4.6 --profile yjwd-grok --bootstrap-bundled --from-cache --yes
```

不要用 `subprocess.run(..., text=True)` 接 `codex debug models --bundled`：中文 Windows 会按 GBK 解码 UTF-8 JSON，随后 `stdout` 变成 `None`。也不要用 `>` 重定向。

| 事项 | Unix shell | PowerShell |
|---|---|---|
| Python | `python3` | `python` |
| Codex 主目录 | `~/.codex` | `$env:USERPROFILE\.codex` |
| 续行 | `\` | `` ` `` |
| 写 JSON | `> file.json` | 不要用 `>`；用 Python 写文件 |
| 临时目录 | `/tmp` | `$env:TEMP` |
| 环境变量 | `export NAME=value` | `$env:NAME = "value"` |
| 加载 `models.env` | `set -a && . ~/.config/models.env && set +a` | 见上方 `Get-Content` |
| CSV 参数 | `--reasoning-levels low,high,xhigh` | 必须加引号：`--reasoning-levels "low,high,xhigh"`（未加引号时逗号会变成数组） |
| 调用 `codex` | PATH 上的 `codex` 可执行文件 | PowerShell 的 `codex` 常是 `.ps1`，Python `subprocess` 找不到。脚本会改找 `codex.cmd` / `codex.exe` |
| bundled JSON | `codex debug models --bundled > file` 可用 | 不要 `text=True`，不要 `>`（UTF-16）。用 `--bootstrap-bundled` |
| 供应商安装器 | 不要 `curl \| bash` | 不要 `irm \| iex` |

## 安装

把本目录放到 Codex skills 下（目录名即 skill 名）：

```bash
cp -R . "${CODEX_HOME:-$HOME/.codex}/skills/codex-model-config"
```

```powershell
Copy-Item -Recurse -Force . "$env:USERPROFILE\.codex\skills\codex-model-config"
```

已在 `~/.codex/skills/codex-model-config` 则可直接用。新开一轮对话后，相关请求会匹配 `$codex-model-config`。

## 关键约束

- 先备份，再只改必要字段。MCP、`[projects.*]`、沙箱和审批策略一律保留。
- 新模型默认新建 `~/.codex/<provider-id>.config.toml`，不要改正在用的默认 `config.toml`。未指定 provider-id 时用模型系列名（`gpt` / `grok` / `deepseek` 等）。
- 改真正设置了 `model = "..."` 的那份 TOML。把 `model_catalog_json` 写进默认配置会替换每一个会话的内置目录。
- 目录 `slug` 必须和 TOML 的 `model` 完全一致。`x-ai/grok-4.6` 不会作用于 `model = "grok-4.6"`。
- 自定义目录会整份替换该进程的内置目录。先导出 bundled 完整菜单再追加，不要写成只有一条模型。
- 创建 catalog **不访问 OpenAI**，也不需要代理。内容来自本机 bundled / 现有 `models.json` / `models_cache.json`。
- 密钥用 `env_key`，本体写入 `~/.config/models.env`，不要写进 TOML，不要回显。
- 保留提供方 id 不要占用：`openai`、`ollama`、`lmstudio`。`model_providers` 不能写在项目级 `.codex/config.toml`。
- 本地窗口数值不会改变上游真实上限。未知 slug 会回退到大约 `272000 * 95% ≈ 258400`。
- `codex --profile` 对 `doctor` 无效。改完后重载客户端并开**新**对话。

## 查询权威元数据

coding agent 配指定模型时：先查供应商官方文档，再调用脚本。不要用博客或 `models_cache.json` 里的数字冒充上游上限。

要确认：精确 slug、`base_url`、`wire_api`。窗口和思考档位查到官方值就覆盖；查不到则用模板里 `skill.codex-model-config` 默认值（258400 上下文 + `low,medium,high,xhigh,max`，默认档 `medium`，部分档位可不可用）。`base_url` / slug 仍不能猜。

简便配置（读模板默认值）：

```bash
python3 scripts/init_profile.py --model grok-4.6 --base-url <url> --defaults --yes
python3 scripts/adjust_context_window.py --model grok-4.6 --profile grok --bootstrap-bundled --from-cache --defaults --yes
```

```powershell
python scripts\init_profile.py --model grok-4.6 --base-url <url> --defaults --yes
python scripts\adjust_context_window.py --model grok-4.6 --profile grok --bootstrap-bundled --from-cache --defaults --yes
```

官方更大窗口或更少档位时再传 `--context-window` / `--reasoning-levels` / `--reasoning-effort`。写 catalog 仍用本机 bundled / 缓存。

`--reasoning-levels` 写入 `models.json` 的 `supported_reasoning_levels`（能选哪些档），不是 TOML。当前用哪一档是 profile 里的 `model_reasoning_effort`（`--reasoning-effort`）。模板注释块只提供默认值，不会被 CLI 改写。

## 快速上手

先收集：模型 slug、`base_url`、`wire_api`、环境变量名、目标窗口（若有）。缺一项不要猜。

### 新建 profile

未指定 `--provider` 时，用模型系列作为 id 和文件名（`grok-4.6` → `grok.config.toml`）：

```bash
python3 scripts/init_profile.py --model grok-4.6 --base-url https://example.invalid/v1 --yes
```

```powershell
python scripts\init_profile.py --model grok-4.6 --base-url https://example.invalid/v1 --yes
```

已有中转站名时显式传入；给了 API Key 就写入 `models.env`，不会写进 TOML：

```bash
python3 scripts/init_profile.py \
  --model grok-4.6 \
  --provider yjwd-grok \
  --base-url https://yujianwudi.net/v1 \
  --env-key YUJIANWUDI_GROK_API_KEY \
  --api-key '<your-key>' \
  --yes
```

```powershell
python scripts\init_profile.py `
  --model grok-4.6 `
  --provider yjwd-grok `
  --base-url https://yujianwudi.net/v1 `
  --env-key YUJIANWUDI_GROK_API_KEY `
  --api-key '<your-key>' `
  --yes
```

目标文件已存在则拒绝覆盖，除非 `--force`。脚本不写 `model_catalog_json`，窗口和目录用下一步补。然后按上面「Shell 差异」加载 `models.env`。

### 上下文窗口与目录

模型已在默认配置和 `models.json` 里：

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

模型在 profile 里，且目录还没有这条：

```bash
python3 scripts/adjust_context_window.py \
  --model grok-4.6 \
  --context-window 500000 \
  --profile yjwd-grok \
  --bootstrap-bundled \
  --from-cache \
  --yes
```

```powershell
python scripts\adjust_context_window.py `
  --model grok-4.6 `
  --context-window 500000 `
  --profile yjwd-grok `
  --bootstrap-bundled `
  --from-cache `
  --yes
```

`model=` 对不上时，除非 `--force`，脚本会拒绝写入默认 `config.toml`。提供方段落仍需按 `references/workflow.md` 核对；该脚本只改窗口相关键。

### 校验

默认配置：

```bash
codex --strict-config doctor
```

应看到 `config.toml parse ok`。不要把 `--profile` 传给 `doctor`。目录校验把 JSON 写到文件再查，不要把 `debug models` 管道进 Python stdin。

```bash
codex -c model_catalog_json='"/home/<user>/.codex/yjwd-grok-models.json"' debug models > /tmp/codex-models-debug.json
```

PowerShell 不要用 `>`。脚本结束时打印的 `codex -c ... debug models` 已按当前 OS 引好号；把 stdout 交给 Python 写文件即可。

开新会话：`codex --profile grok`。启动信息里的 `model:` 应等于配置的 slug。VS Code / 桌面端：`Ctrl+Shift+P` → `Developer: Reload Window`（或完全退出桌面端），然后开新对话。旧会话仍用启动时的目录和窗口。

## 有效窗口

```text
effective = min(model_context_window, max_context_window) * effective_context_window_percent
```

要精确命中目标：把目录里的 `context_window` 和 `max_context_window` 都设成该目标，并把 `effective_context_window_percent` 设为 `100`。压缩阈值常用有效窗口的 90%。

## 代理（仅实际上游请求失败时）

写 catalog **不要**设代理。只有调用 `base_url` 失败、且本机已有 Clash / V2Ray 一类客户端时，用环境变量，不要写进 TOML。常见本地 HTTP 端口：`7897`、`7890`、`10808`（有的软件此端口是 SOCKS5）。先确认端口真的在听，不要扫全端口。

## command auth（可选）

默认仍用 `env_key` + `models.env`。只有需要 `auth.command` 时才用，Unix 与 Windows 的 command/args 不同：

```toml
# Unix
[model_providers.<provider-id>.auth]
command = "sh"
args = ["-c", "echo $OPENROUTER_API_KEY"]

# Windows PowerShell
[model_providers.<provider-id>.auth]
command = "powershell"
args = ["-NoProfile", "-Command", "Write-Output $env:OPENROUTER_API_KEY"]
```

## 更多

完整步骤、字段表和排障见 `references/`。