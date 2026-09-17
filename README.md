# Codex 模型配置 Skill

把自定义或第三方模型接到 Codex：提供方、目录元数据、上下文窗口。CLI、ChatGPT 桌面端和 VS Code Codex 插件共用同一份用户配置。

规范以 `SKILL.md` 为准。本文只做索引，不重复约束和命令。

## 文档索引

| 路径 | 作用 |
|---|---|
| `SKILL.md` | 唯一规范：何时用、硬约束、工作流 |
| `references/usage.md` | 唯一命令出处：推荐用法、Unix/PowerShell 示例、校验 |
| `agents/openai.yaml` | Codex UI 展示名与默认提示 |
| `scripts/init_profile.py` | 从模板新建 `~/.codex/<provider>.config.toml`（含提供方调优参数） |
| `scripts/adjust_context_window.py` | 改窗口、目录条目、`model_catalog_json`（含工具/模态覆盖） |
| `scripts/model_meta.py` | 共享枚举与解析：`responses`、`low..max`、`text,image,audio,video` |
| `scripts/shell_hints.py` | 按 OS 打印后续命令 |
| `references/template.config.toml` | profile 模板 |
| `references/workflow.md` | 接入顺序与字段分工（无命令块） |
| `references/model-catalog-json.md` | 字段主次唯一说明 |
| `references/catalog-source.md` | 目录来源 |
| `references/model-info-sources.md` | 模型信息源（查规格用） |
| `references/context-window-guide.md` | 窗口公式 |
| `references/常见陷阱.md` | 陷阱清单 |
| `references/codex-sandbox-permissions.md` | 沙箱/审批 |
| `references/400k-context-setup配置指南.md` | DeepSeek 400K 历史示例（已标注过期点） |

约束、步骤、命令分别见 `SKILL.md` 与 `references/usage.md`，此处不复述。

## 安装

```bash
mkdir -pv ~/.agents/skills/
skill_repo='https://github.com/xuchaoxin1375/codex-model-config.git'
# 国内用户可以使用github加速镜像(定义2个备用)
github_mirror1='https://ghproxy.net' github_mirror2='https://gh-proxy.com'
# skill_repo="$github_mirror1/$skill_repo" && echo "url=$skill_repo" # 可选改写镜像1,2
# 开始拉取skill
git clone "$skill_repo" ~/.agents/skills/codex-model-config
cp -R . "${CODEX_HOME:-$HOME/.codex}/skills/codex-model-config"
```



```powershell
Copy-Item -Recurse -Force . "$env:USERPROFILE\.codex\skills\codex-model-config"
```

要点：Python 3.11+（`tomllib`）；`model_catalog_json` 用绝对路径正斜杠；密钥走 `~/.config/models.env`；`wire_api` 只有 `responses`。细节见 `SKILL.md`，命令见 `references/usage.md`。
