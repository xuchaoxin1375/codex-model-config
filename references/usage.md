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
python3 scripts/adjust_context_window.py --model deepseek-v4-flash-vision-exp --context-window 400000 --compact-percent 90 --yes
```

```powershell
python scripts\adjust_context_window.py --model deepseek-v4-flash-vision-exp --context-window 400000 --compact-percent 90 --yes
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
  --apply-patch-type freeform
# Grok 实测 patch 全失败时：--apply-patch-type null
# 关延迟工具发现（非 web search 开关）：--no-supports-search-tool
# 音频输入模型加 audio；不要写 video（本版 Codex 整份拒读）
```

```powershell
python scripts\adjust_context_window.py --model <slug> --profile <id> --bootstrap-bundled --from-cache --yes `
  --input-modalities "text,image" `
  --web-search-type text `
  --apply-patch-type freeform
```

`--dry-run` 只打印方案；`--force` 仅在 `model=` 对不上时放行；脚本默认去掉 `code_mode_only` 并打开 skills/plugin/apps 说明。

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

`--catalog-only` 只增改目录条目、不碰 TOML（窗口差距大才各建 profile）。预览输出（不写文件）：

```bash
python3 scripts/init_profile.py --model <slug> --provider <id> --base-url <url> --dev
python3 scripts/adjust_context_window.py --model <slug> --profile <id> --context-window <n> --dev
```

## 3. 校验（读文件，不管道 heredoc）

```bash
codex --strict-config doctor
codex -c model_catalog_json='"/home/<user>/.codex/<profile>-models.json"' debug models > /tmp/codex-models-debug.json
python3 -c 'import json; from pathlib import Path; data=json.loads(Path("/tmp/codex-models-debug.json").read_text()); m=next(x for x in data["models"] if x["slug"]=="<slug>"); print({k:m.get(k) for k in ["slug","context_window","max_context_window","effective_context_window_percent","input_modalities","apply_patch_tool_type","shell_type","web_search_tool_type","tool_mode"]})'
codex --profile <name>
```

PowerShell 用脚本打印的 `codex -c '...'` 行，把 stdout 交给 Python 写文件，不要 `>`。`doctor` 不接受 `--profile`。

`debug models` 只证明目录可读。配完必须再打一次真实请求（网关可能拒收某些工具类型，目录校验看不出来）：

```bash
codex --profile <name> exec --skip-git-repo-check -s read-only -c approval_policy="never" "Reply with exactly: OK"
```

```powershell
codex --profile <name> exec --skip-git-repo-check -s read-only -c approval_policy="never" "Reply with exactly: OK"
```

切模型验证加 `-m <slug>`。返回 `unsupported_feature` / `tool type '...' is not supported` 即按 [tool-calling.md](tool-calling.md) 排障（通常是 `apply_patch` / `web_search` 被拒收）。

收尾：重载 VS Code / 桌面端并开新对话；旧会话保留启动时的目录和窗口。
