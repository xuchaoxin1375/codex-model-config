# Codex 沙箱与审批权限

本 skill 经常要写 `~/.codex/`、跑 `codex debug models`、以及 `git` 整理仓库。这些动作受 **沙箱** 和 **审批策略** 两套开关约束，和模型 profile 不是同一件事。

权威说明见官方文档：[Sandbox](https://developers.openai.com/codex/concepts/sandboxing)、[Config basics](https://developers.openai.com/codex/config-basic)、[Configuration reference](https://developers.openai.com/codex/config-reference)。

## 先改哪

| 目的 | 改哪里 |
|---|---|
| 以后每次默认都这样 | 用户级 `~/.codex/config.toml`（CLI / IDE / 桌面端共用） |
| 只这个仓库默认 | 项目 `.codex/config.toml`（仅受信任项目会加载；不能覆盖提供方/认证类键） |
| 只开这一次 | CLI：`--sandbox`、`--ask-for-approval`，或 `codex --yolo` |

优先级（高 → 低）：CLI / `-c` → 项目 `.codex/config.toml` → `--profile` 的 profile 文件 → `~/.codex/config.toml` → 内置默认。组织可能用 `requirements.toml` 禁止 `never` 或 `danger-full-access`。

不要把 `sandbox_mode` / `approval_policy` 写进本 skill 生成的 `~/.codex/<provider>.config.toml`，那是模型提供方 profile，不是权限配置。

## 两个开关

沙箱决定命令**实际能碰什么**；审批决定越界时**要不要停下来问你**。

常见沙箱：

- `read-only`：能看文件；改文件或跑命令要批准。
- `workspace-write`：可读写当前工作区，适合日常改代码。默认仍**保护**工作区内的 `.git/`、`.codex/`，也默认**没有外网**。
- `danger-full-access`：去掉文件系统和网络边界。只在明确需要（改 git index、装全局工具）时用。

常见审批：

- `untrusted`：不在可信集合里的命令都先问。
- `on-request`：沙箱内自己干，越界再问。日常推荐。
- `never`：不问。越界命令会直接失败（例如 `git` 写不了 `.git/index.lock`），agent 也无法申请升级。

交互审批时还有 `approvals_reviewer`：`user`（默认，弹给你）或 `auto_review`（符合条件的请求交给审查 agent）。审查**不扩大**沙箱边界。

## 推荐组合

日常本机自动化（低风险）：

```toml
sandbox_mode = "workspace-write"
approval_policy = "on-request"

[sandbox_workspace_write]
network_access = true
```

等价 CLI：

```powershell
codex --sandbox workspace-write --ask-for-approval on-request
```

需要 agent 直接改 git 历史 / index、或安装依赖拉外网且不能停顿时：

```powershell
codex --sandbox danger-full-access --ask-for-approval never
# 或
codex --yolo
```

对应 TOML：

```toml
sandbox_mode = "danger-full-access"
approval_policy = "never"
```

Windows 原生沙箱另有一层（与上面的 `sandbox_mode` 不同）：

```toml
[windows]
sandbox = "elevated"   # 推荐；没有管理员权限再改 unelevated
```

## 本 skill 会踩到的边界

这些在 `workspace-write` + `approval_policy = "never"` 下会失败或半成品：

- `git add` / `git rm --cached` / `git commit` / `git amend`：写 `.git/index` 或 `index.lock` 被拒（`Permission denied`）。
- 改仓库里的 `.codex/` 配置（若该目录受保护）。
- 访问 `~/.codex/` 之外的密钥文件，或需要外网的 `pip` / 文档抓取（未开 `network_access` 时）。

处理办法：

1. 用户本机自己跑 git / 写 `~/.codex`（最稳）。
2. 这次会话用 `--sandbox danger-full-access`，或把审批改成 `on-request` 让你点一次批准。
3. 不要为了一次 git 清理把全局默认改成 full access。

脚本把 `models.json` 写进 `--codex-home`（默认 `~/.codex`）。若报该目录不可写，换可写的 `--codex-home`，或提高本次沙箱，而不是改模型 TOML。

## 和「模型配置」的分工

| 文件 | 管什么 |
|---|---|
| `~/.codex/config.toml` | 默认模型、沙箱、审批、MCP |
| `~/.codex/<provider>.config.toml` | 本 skill 生成的提供方、slug、窗口 |
| `~/.codex/models.json` | 选择器目录 |
| 项目 `.codex/config.toml` | 该仓库的沙箱/审批覆盖（受信任时） |

改窗口、slug、提供方：按 [workflow.md](workflow.md)。权限太紧导致命令失败：先看本文，再看 [常见陷阱.md](常见陷阱.md) 里的编码 / PATH / 文件写错问题。
