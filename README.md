# Codex 模型配置 Skill

把自定义或第三方模型接到 Codex：提供方、目录元数据、上下文窗口。CLI、ChatGPT 桌面端和 VS Code Codex 插件共用同一份用户配置。

规范以 [SKILL.md](SKILL.md) 为准。本文只做索引，不重复约束和命令。

## 文档索引

| 路径 | 作用 |
|---|---|
| [AGENTS.md](AGENTS.md) | 仓库级说明：真源矩阵与改动协议（给 coding agent） |
| [SKILL.md](SKILL.md) | 唯一规范：何时用、硬约束、工作流 |
| [references/usage.md](references/usage.md) | 唯一命令出处：推荐用法、Unix/PowerShell 示例、校验 |
| `agents/openai.yaml` | Codex UI 展示名与默认提示 |
| `scripts/init_profile.py` | 从模板新建 `~/.codex/<provider>.config.toml`（含提供方调优参数） |
| `scripts/adjust_context_window.py` | 改窗口、目录条目、`model_catalog_json`（含工具/模态覆盖） |
| `scripts/model_meta.py` | 共享枚举与解析：`responses`、`low..max`、`text,image,audio` |
| `scripts/shell_hints.py` | 按 OS 打印后续命令 |
| `references/template.config.toml` | profile 模板 |
| [references/workflow.md](references/workflow.md) | 接入顺序与字段分工（无命令块） |
| [references/model-catalog-json.md](references/model-catalog-json.md) | 字段主次唯一说明 |
| [references/tool-calling.md](references/tool-calling.md) | 工具调用：改文件/搜索三条路/依赖 |
| [references/catalog-source.md](references/catalog-source.md) | 目录来源 |
| [references/model-info-sources.md](references/model-info-sources.md) | 模型信息源（查规格用） |
| [references/context-window-guide.md](references/context-window-guide.md) | 窗口公式 |
| [references/常见陷阱.md](references/常见陷阱.md) | 陷阱清单 |
| [references/codex-sandbox-permissions.md](references/codex-sandbox-permissions.md) | 沙箱/审批 |
| [references/dev-guide.md](references/dev-guide.md) | 本 skill 开发规范（测试/兼容/提交） |
| [references/400k-context-setup配置指南.md](references/400k-context-setup配置指南.md) | DeepSeek 400K 历史示例（已标注过期点） |
| [references/case-xiaomi-mimo.md](references/case-xiaomi-mimo.md) | Xiaomi 双模型配置案例（含实跑命令） |

约束、步骤、命令分别见 [SKILL.md](SKILL.md) 与 [references/usage.md](references/usage.md)，此处不复述。

## 安装

unix shell:

```bash
mkdir -pv ~/.agents/skills/
skill_repo='https://github.com/xuchaoxin1375/codex-model-config.git'
# 国内用户可改用加速镜像（二选一，去掉行首 #）
# skill_repo="https://ghproxy.net/https://github.com/xuchaoxin1375/codex-model-config.git"
# skill_repo="https://gh-proxy.com/https://github.com/xuchaoxin1375/codex-model-config.git"
# 已克隆则更新，否则拉取（可重复执行）
if [ -d ~/.agents/skills/codex-model-config ]; then git -C ~/.agents/skills/codex-model-config pull; else git clone "$skill_repo" ~/.agents/skills/codex-model-config; fi
# 先清目标再复制，避免重复执行时嵌套
rm -rf "${CODEX_HOME:-$HOME/.codex}/skills/codex-model-config"
cp -R ~/.agents/skills/codex-model-config "${CODEX_HOME:-$HOME/.codex}/skills/codex-model-config"
```

powershell(pwsh):

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.agents\skills" | Out-Null
$skillRepo = 'https://github.com/xuchaoxin1375/codex-model-config.git'
# 国内用户可改用加速镜像（二选一，去掉行首 #）
# $skillRepo = "https://ghproxy.net/https://github.com/xuchaoxin1375/codex-model-config.git"
# $skillRepo = "https://gh-proxy.com/https://github.com/xuchaoxin1375/codex-model-config.git"
$skillDir = "$env:USERPROFILE\.agents\skills\codex-model-config"
if (Test-Path $skillDir) { git -C $skillDir pull } else { git clone $skillRepo $skillDir }
$codexSkills = if ($env:CODEX_HOME) { "$env:CODEX_HOME\skills\codex-model-config" } else { "$env:USERPROFILE\.codex\skills\codex-model-config" }
Remove-Item -Recurse -Force $codexSkills -ErrorAction SilentlyContinue
Copy-Item -Recurse -Force $skillDir $codexSkills
```

要点：Python 3.10+（3.10 需先 `pip install tomli`，3.11+ 自带 `tomllib`）；

- `model_catalog_json` 用绝对路径正斜杠；
- 密钥走 `~/.config/models.env`；
- `wire_api` 只有 `responses`。
- 细节见 [SKILL.md](SKILL.md)，命令见 [references/usage.md](references/usage.md)。
