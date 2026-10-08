# 案例：Xiaomi MiMo 双模型（`mimo-v2.5` + `mimo-v2.5-pro`）

一次配好、同目录双条目、选择器内切换的完整记录。通用流程见 [workflow.md](workflow.md)，命令模板见 [usage.md](usage.md)。

## 官方规格（2026-09 查）

| 模型 | 上下文 | 输入模态 | 思考 | 备注 |
|---|---|---|---|---|
| `mimo-v2.5` | 1M | text, image, audio（上游 omni 另有 video，本版 Codex 目录写不进） | `thinking.type` 开/关，默认开 | 原生多模态，日常 coding 性能够用且便宜一半 |
| `mimo-v2.5-pro` | 1M，最大输出 128K | text | 同上 | 纯文本旗舰，复杂工程任务用它 |

MiMo 推理只有开/关两档，没有 `low..max` 五档；Codex 侧保留五档选择器（默认 `medium`），上游映射未知。

## 架构

- `mimo.config.toml`：只定默认选择——`model=mimo-v2.5`、`model_reasoning_effort=medium`、`web_search="disabled"`（MiMo 拒收搜索工具，不禁即 400；禁了不挡 `curl`），外加窗口键（1M 生效必需）与提供方段。
- `mimo-models.json`：模型列表——完整 bundled + 两条 mimo（13 条），选择器内切换。
- 密钥：复用系统环境变量 `MIMO_API_KEY`，`env_key` 只写变量名，`models.env` 未动。

## 命令（PowerShell，实跑过）

```powershell
python scripts\init_profile.py --model mimo-v2.5 --provider mimo --base-url https://api.xiaomimimo.com/v1 --env-key MIMO_API_KEY --yes
python scripts\adjust_context_window.py --model mimo-v2.5 --profile mimo --bootstrap-bundled --from-cache --context-window 1000000 --input-modalities "text,image,audio" --apply-patch-type null --yes
python scripts\adjust_context_window.py --model mimo-v2.5-pro --profile mimo --bootstrap-bundled --from-cache --context-window 1000000 --input-modalities "text" --apply-patch-type null --catalog-only --yes
```

两条的 `apply_patch` 都是 `null`：本版 Codex 以 `custom` 类型发出该工具，Xiaomi 网关直接 400（`tool type 'custom' is not supported`），见下文验证。改文件走 shell/Python 整文件重写。

```toml
# mimo.config.toml 顶层手工加一行（须在任何 [table] 之前）：
web_search = "disabled"
```

bash 把 `python` 换 `python3`、续行换 `\`、CSV 去引号即可，见 [usage.md](usage.md)。

## 验证

两层，缺一不可：

1. `debug models` 确认两条：`context_window=1000000`、`effective=100%`、`apply_patch=null`、`shell=unified_exec`、无 `code_mode_only`。注意输出 500KB+，不要管道进 `python -c`（会被截断），用 Python 落盘再读。
2. 真实请求（`debug` 看不出的网关拒收只能这层发现）：`codex --profile mimo exec --skip-git-repo-check -s read-only -c approval_policy="never" "Reply with exactly: OK"`，切 pro 加 `-m mimo-v2.5-pro`。本案两条都已跑通。

定位方法（`custom` 从哪来）：临时 profile 指本地回显代理（`base_url=http://127.0.0.1:PORT/v1`），`exec` 一次，抓请求体看 `tools[]` 的 `type`/`name`。本案抓到 `custom | apply_patch`，其他均为 `function`/`namespace`/`web_search`，故两条改 `null` 后复抓确认 `custom` 消失，再打真实上游。

## 本案踩过的坑

- `input_modalities` 写 `video` → 整份 catalog 拒读（`unknown variant 'video'`）。本版 Codex 只认 `text/image/audio`，见 [常见陷阱.md](常见陷阱.md)。
- `--dev` 预览打印含特殊字符的条目时在 GBK 控制台崩溃 → 已修（`model_meta.print_preview_body`，有回归测试）。
- `codex` 在 PowerShell 是 `.ps1` 垫片，Python 调不起；脚本只找 `codex.cmd`/`codex.exe`。
- 初版曾一模型一 profile，后合并为共享目录；`mimo-pro.*` 已删，只留备份。
