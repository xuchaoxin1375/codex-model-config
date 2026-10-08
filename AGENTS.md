# AGENTS.md

> 给在本仓库工作的 coding agent（Codex 会自动加载本文件）。
> 分工：[SKILL.md](SKILL.md) 教**用户**用 skill；本文件教 **agent** 改本仓库。改前先读真源矩阵。

## 这是什么

`codex-model-config` skill 仓库：`scripts/`（建 profile、写目录）+ `references/template.config.toml` + 文档，把第三方/自定义模型接到 Codex。

## 真源矩阵（改任何东西先查表，只改真源，别处只加链接）

| 主题 | 真源文件 |
|---|---|
| 规范、硬约束、工作流 | [SKILL.md](SKILL.md) |
| 命令示例（唯一可执行出处） | [references/usage.md](references/usage.md) |
| 目录字段语义 | [references/model-catalog-json.md](references/model-catalog-json.md) |
| 工具调用（改文件/搜索/依赖） | [references/tool-calling.md](references/tool-calling.md) |
| 接入顺序与分工 | [references/workflow.md](references/workflow.md) |
| 目录来源 | [references/catalog-source.md](references/catalog-source.md) |
| 模型信息源 | [references/model-info-sources.md](references/model-info-sources.md) |
| 窗口公式 | [references/context-window-guide.md](references/context-window-guide.md) |
| 陷阱清单 | [references/常见陷阱.md](references/常见陷阱.md) |
| 沙箱/审批 | [references/codex-sandbox-permissions.md](references/codex-sandbox-permissions.md) |
| 安装与仓库索引 | [README.md](README.md) |
| 开发规范（测试/兼容/一致性/提交） | [references/dev-guide.md](references/dev-guide.md) |
| 本矩阵（项目级文档管理设计） | [AGENTS.md](AGENTS.md)（本文件） |
| 历史示例（已标注过期点，不跟进） | [references/400k-context-setup配置指南.md](references/400k-context-setup配置指南.md) |
| 配置案例（含实跑命令） | [references/case-xiaomi-mimo.md](references/case-xiaomi-mimo.md) |

## 改动协议

1. 先读对应真源，再改真源；别处只加链接，不抄第二份。
2. 改脚本行为 → 同步改真源文档 → 同步加回归测试（见 [dev-guide.md](dev-guide.md)）。
3. 改完全仓 grep 做一致性检查（枚举、默认值、路径、版本号），冲突以代码行为为准。
4. `python -m pytest tests/ -q` 全过；`git diff` 确认每行都是本轮意图；只暂存意图文件，不碰无关 untracked。

## 红线

- 真实密钥不进仓库；占位只用 `example.invalid` / `<key>` 类。
- 不改用户正在用的默认 `config.toml` 语义；`wire_api` 只有 `responses`。
- 只提交不推送；推送、PR 等明确要求再做。
