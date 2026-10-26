# 推荐用法与命令行（唯一 canonical）

本文件是所有命令示例的唯一出处。[SKILL.md](../SKILL.md) 只给约束和步骤，[README.md](../README.md) 只给索引，其他 `references/` 不再重复贴命令，统一链到这里。

约定：`skill` 根目录即本仓库目录。下文 `<profile>` 指 `~/.codex/<profile>.config.toml` 的 stem。

## Shell 差异（只写一次）

| 事项               | Unix shell                                     | PowerShell                                                                        |
| ------------------ | ---------------------------------------------- | --------------------------------------------------------------------------------- |
| Python             | `python3`                                    | `python`（不要 `python3`）                                                    |
| 续行               | `\`                                          | `` ` ``                                                                           |
| CSV 参数           | `--reasoning-levels low,high`                | 必须加引号：`--reasoning-levels "low,high"`                                     |
| 写 JSON            | `> file.json` 可用（UTF-8）                  | 不要用`>`（UTF-16）；用 `--bootstrap-bundled` 让脚本写文件                    |
| 调`codex`        | PATH 上的`codex`                             | 脚本只找`codex.cmd`/`codex.exe`，不认 `codex.ps1`                           |
| 解码               | 无特殊                                         | 不要`subprocess text=True` 接 bundled JSON（GBK 会炸）；脚本已按字节 UTF-8 解码 |
| 加载`models.env` | `set -a && . ~/.config/models.env && set +a` | 见下文 PowerShell 片段                                                            |

PowerShell 加载 `models.env`：

```powershell
$envFile = Join-Path $env:USERPROFILE ".config\models.env"
Get-Content -LiteralPath $envFile | ForEach-Object {
  if ($_ -match '^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
    Set-Item -Path "Env:$($Matches[1])" -Value $Matches[2].Trim().Trim('"').Trim("'")
  }
}
```

## 1. 新建配置 profile（`init_profile.py`）

```Shell
python3 scripts/init_profile.py --model grok-4.6 --base-url https://example.invalid/v1 --yes
python3 scripts/init_profile.py --model grok-4.6 --provider yjwd-grok --base-url https://yujianwudi.net/v1 --env-key YUJIANWUDI_GROK_API_KEY --yes
python3 scripts/init_profile.py --model grok-4.6 --base-url https://example.invalid/v1 --api-key '<key>' --yes
```

提供方调优（按需，不猜值；含义见 [workflow.md](workflow.md)）：

```bash
python3 scripts/init_profile.py --model <slug> --provider <id> --base-url <url> \
  --query-params "api-version=2025-04-01-preview" \
  --request-max-retries 4 --stream-max-retries 10 --stream-idle-timeout-ms 300000 \
  --yes
```

```powershell
python scripts\init_profile.py --model <slug> --provider <id> --base-url <url> `
  --query-params "api-version=2025-04-01-preview" `
  --request-max-retries 4 --stream-max-retries 10 --stream-idle-timeout-ms 300000 `
  --yes
```

规则：未传 `--provider` 则用模型系列名；目标已存在需 `--force`；`--as-default` 才碰默认 `config.toml`；`wire_api` 只有 `responses`。

## 2. 仅调整:窗口 + 目录（`adjust_context_window.py`）

模型已在默认配置里，只改窗口：

```bash
python3 scripts/adjust_context_window.py --model deepseek-v4-flash-vision-exp --bootstrap-bundled --context-window 400000 --effective-percent 100 --compact-percent 90 --yes
```

```powershell
python scripts\adjust_context_window.py --model deepseek-v4-flash-vision-exp --bootstrap-bundled --context-window 400000 --effective-percent 100 --compact-percent 90 --yes
```

模型在 profile 里、目录缺条目（查不到官方窗口/档位用 `--defaults`）：

```shell
python3 scripts/adjust_context_window.py --model grok-4.6 --profile yjwd-grok --bootstrap-bundled --from-cache --defaults --yes
# 可以一并指定窗口长度和推理档位
python3 scripts/adjust_context_window.py --model grok-4.6 --profile yjwd-grok --bootstrap-bundled --from-cache --context-window <n> --reasoning-levels low,medium,high,xhigh --yes
```

工具偏好 / 输入模态覆盖（默认值见 [model-catalog-json.md](model-catalog-json.md)，不要跨供应商抄）：

```bash
python3 scripts/adjust_context_window.py --model <slug> --profile <id> --bootstrap-bundled --from-cache --yes \
  --input-modalities text,image \
  --web-search-type text \
  --responses-lite false \
  --apply-patch-type freeform
# 第三方网关必须 --responses-lite false（否则托管 web_search 不进顶层 tools）；OpenAI 官方模型保持默认
# Grok 实测 patch 全失败时：--apply-patch-type null
# 关延迟工具发现（非 web search 开关）：--no-supports-search-tool
# 音频输入模型加 audio；不要写 video（本版 Codex 整份拒读）
```

```powershell
python scripts\adjust_context_window.py --model <slug> --profile <id> --bootstrap-bundled --from-cache --yes `
  --input-modalities "text,image" `
  --web-search-type text `
  --responses-lite false `
  --apply-patch-type freeform
```

`--dry-run` 只打印方案，`--dev` 展示差异，二者均不写文件；`--force` 仅在 `model=` 对不上时放行。新条目采用 skill 的工具默认值；已有条目只调窗口时保留推理与工具偏好，其他条目不回填。省略窗口或有效比例时保留已有值，缺失或显式 `--defaults` 时才使用 skill 默认值；精确命中有效预算时显式给有效比例，计算与限制见 [窗口指南](context-window-guide.md)。

同供应商多模型（一份目录多条，选择器内切换，如 Xiaomi 的 `mimo-v2.5` + `mimo-v2.5-pro`）：

```bash
python3 scripts/init_profile.py --model mimo-v2.5 --provider mimo --base-url <url> --yes
python3 scripts/adjust_context_window.py --model mimo-v2.5 --profile mimo --bootstrap-bundled --from-cache --context-window 1000000 --yes
python3 scripts/adjust_context_window.py --model mimo-v2.5-pro --profile mimo --bootstrap-bundled --from-cache --context-window 1000000 --catalog-only --yes
```

```powershell
python scripts\init_profile.py --model mimo-v2.5 --provider mimo --base-url <url> --yes
python scripts\adjust_context_window.py --model mimo-v2.5 --profile mimo --bootstrap-bundled --from-cache --context-window 1000000 --yes
python scripts\adjust_context_window.py --model mimo-v2.5-pro --profile mimo --bootstrap-bundled --from-cache --context-window 1000000 --catalog-only --yes
```

`--catalog-only` 只增改 TOML 已引用的目录、不碰 TOML（窗口或压缩预算不同优先分 profile）。预览输出（不写文件）：

```bash
python3 scripts/init_profile.py --model <slug> --provider <id> --base-url <url> --dev
python3 scripts/adjust_context_window.py --model <slug> --profile <id> --context-window <n> --dev
```

## 3. 校验（读文件，不管道 heredoc）

```bash
codex --strict-config doctor
codex -c model_catalog_json='"/home/<user>/.codex/<profile>-models.json"' debug models > /tmp/codex-models-debug.json
python3 -c 'import json; from pathlib import Path; data=json.loads(Path("/tmp/codex-models-debug.json").read_text()); m=next(x for x in data["models"] if x["slug"]=="<slug>"); print({k:m.get(k) for k in ["slug","context_window","max_context_window","effective_context_window_percent","input_modalities","apply_patch_tool_type","shell_type","web_search_tool_type","use_responses_lite","tool_mode"]})'
codex --profile <name>
```

PowerShell 用脚本打印的 `codex -c '...'` 行，把 stdout 交给 Python 写文件，不要 `>`。`doctor` 和 `debug models` 不接受 `--profile`；查专用目录按上例显式传 `-c model_catalog_json=...`，启动会话才用 `--profile`。

目录是否真的被加载，看两件事，不要只看命令有没有报错：

- `debug models` 与 `debug models --bundled` 的模型集合一致 → 读的是内置目录，自定义文件没生效。
- 改目录里的显眼字段（`display_name` / `context_window` / `use_responses_lite`）后重跑，输出跟着变才算读到。

常见假生效：键写在 profile 文件但启动没带 `--profile`；路径用了 `~` 或相对路径；改完没重启进程；TOML `model` 与目录 `slug` 不匹配（走 fallback 元数据，看着像没生效）。`debug models` 同样不接受 `--profile`，验证 profile 里的目录要把该路径用 `-c` 传进去。

`debug models` 只证明目录可读。配完必须再打一次真实请求（网关可能拒收某些工具类型，目录校验看不出来）：

```bash
codex --profile <name> exec --skip-git-repo-check -s read-only -c approval_policy="never" "Reply with exactly: OK"
```

```powershell
codex --profile <name> exec --skip-git-repo-check -s read-only -c approval_policy="never" "Reply with exactly: OK"
```

切模型验证加 `-m <slug>`。返回 `unsupported_feature` / `tool type '...' is not supported` 即按 [tool-calling.md](tool-calling.md) 排障（通常是 `apply_patch` / `web_search` 被拒收）。

会话内验证搜索加 `--json`（PowerShell 同文）：

```bash
codex --profile <name> exec --json --skip-git-repo-check -s read-only -c approval_policy="never" "不使用任何 skill，直接做一次简单的一次性搜索：<可核验主题>"
```

输出是 JSONL：`item.completed` 且 `action.type=search`、带 `query` / `queries` 才算执行过搜索，`item.started` 的 `action.type=other` 不算。判定边界见 [tool-calling.md](tool-calling.md#搜索可用性的验证边界)。

收尾：重载 VS Code / 桌面端并开新对话；旧会话保留启动时的目录和窗口。

改完让配置生效，按宿主分层，退出 TUI 不等于重启后台服务：

| 宿主 | 何时读配置 | 怎么做 |
|---|---|---|
| `codex` TUI / `codex exec` | 进程启动 | 退出重开；要完全隔离用 `codex --no-daemon` |
| 共享 app-server daemon | daemon 启动 | `codex app-server daemon restart`；`stop` 也行，下次自动拉起 |
| VSCode 扩展 | 扩展自己的 app-server 启动 | `Developer: Reload Window`，或直接关窗口 |
| Desktop App | 应用内 app-server 启动 | 完全退出（含托盘）再启动 |

判定当前有没有 daemon：`codex app-server daemon version`。报连接失败就是没有，退出 TUI 重开即可；有输出说明它还活着，只重开 TUI 仍用旧配置。残留 socket 让该命令报错时先 `daemon restart`；仍不行再按 PID 结束那一个进程（Linux：`pgrep -fl codex` 看清后 `kill <pid>`），不要用 `pkill codex` 这类批量杀——它会连带结束正在跑的 TUI 和其他会话。改前改后各跑一次，看运行版本或启动时间变化即可确认换新。

`daemon version` 同时给出 `cliVersion` 与 `appServerVersion`。两者不一致说明 daemon 仍旧二进制，只重启换不掉版本：npm/brew 安装的 CLI 升级不会自动迁移 managed app-server。`codex app-server daemon update` 会去拉 `https://chatgpt.com/codex/install.sh`，国内常超时，且可能中断正在运行的会话；`--from-cli` 能把当前 CLI 复制给 daemon（可用但锁版本）。要持续跟版，用官方独立安装后再 `app-server daemon bootstrap`；不然就接受手动管理版本。

## 4. 手写第三方配置静态检查（`check_profile.py`）

只读不写。抓手写配置最常见的遗漏：空 `base_url`（回退 OpenAI）、模板占位符未替换、`wire_api` 非 `responses`、密钥进 TOML、目录 slug 对不上等。`debug models` 之前先跑它：

```bash
python3 scripts/check_profile.py --profile <id>
python3 scripts/check_profile.py --file ~/.codex/<id>.config.toml --env-file ~/.config/models.env --strict
```

```powershell
python scripts\check_profile.py --profile <id>
python scripts\check_profile.py --file $env:USERPROFILE\.codex\<id>.config.toml --strict
```

退出码：0 无 ERROR（警告放行），1 有 ERROR（`--strict` 下警告也算），2 用法/文件错误；`--json` 出机器可读。字段语义与判定依据见 [model-catalog-json.md](model-catalog-json.md)，陷阱清单见 [常见陷阱.md](常见陷阱.md)。

搜索体检：它同时校验顶层 `web_search` 取值，并在目录条目 `use_responses_lite=true` 时给 `W_RESPONSES_LITE`（托管搜索不会进顶层 `tools`）；修复用 §2 的 `--responses-lite false`。

## 5. 搜索配置一屏视图（`inspect_web_search.py`）

目录 JSON 太长、不想翻文件时用它。只读、离线：不发请求、不抓包、不改文件。

```bash
python3 scripts/inspect_web_search.py                 # 默认 ~/.codex/config.toml
python3 scripts/inspect_web_search.py -p mimo         # 叠加 profile 层（等价 codex -p 的 layer 语义）
python3 scripts/inspect_web_search.py -a -b           # 所有 profile 覆盖 + 与内置目录比字段
python3 scripts/inspect_web_search.py --json          # 机器可读
```

```powershell
python scripts\inspect_web_search.py -a -b
```

输出分四块：

- 生效层：model、provider、base_url、`web_search`、目录路径与条目数。
- `checks`：搜索三处是否成立（`[ok]` / `[! ]` / `[!!]`），阻断项以 `E_` 开头。
- `catalog search fields`：每条只留 `use_responses_lite` 与 `web_search_tool_type`，`*` 标当前模型。
- `profiles`：各 profile 的顶层覆盖，`<inherit>` 表示继承 base；`-b` 会调本机 `codex debug models --bundled` 做字段差异，用来证明自定义目录真的被加载。

退出码：0 无阻断项，1 有阻断项，2 用法或文件错误。它只判配置层；网关是否透传、会话里是否真调用，按 [tool-calling.md](tool-calling.md#搜索可用性的验证边界) 另做。

## 6. 工具面一屏视图（`inspect_tools.py`）

回答"当前配置下模型手上有哪些工具"。只读、离线，来源是目录条目 + `config.toml`：

```bash
python3 scripts/inspect_tools.py
python3 scripts/inspect_tools.py -p mimo
python3 scripts/inspect_tools.py --json
```

```powershell
python scripts\inspect_tools.py -p mimo
```

每行一个工具面，标记含义：

| 标记 | 含义 |
|---|---|
| `[send]` | 配置上会进请求：托管 `web_search`、`tool_search`（延迟发现）、`apply_patch`、`shell`、`experimental_supported_tools` |
| `[off ]` | 已关闭（`web_search=disabled`、`shell_type=disabled`、`apply_patch_tool_type=null` 等） |
| `[!!  ]` | 被 `use_responses_lite=true` 或非法 `web_search_tool_type` 挡住 |
| `[nest]` | 被 `tool_mode=code_mode_only` 收进嵌套工具，仍可达但不是顶层工具 |
| `[?   ]` | 目录缺失、slug 对不上或字段缺失，先修目录再判断 |

另外列出 `[mcp_servers]` 与 skills/plugin/apps 说明开关。Codex 没有"列出当前会话全部可用工具"的命令：`debug models` 只给目录字段、`debug prompt-input` 只给消息、`mcp list` 只给 server。请求体里到底有什么，按 [tool-calling.md](tool-calling.md#搜索可用性的验证边界) 取证。
