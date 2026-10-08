# Skill 开发规范

改本 skill 代码或文档时遵守。规范本身只定规则，命令与字段语义不复述（见 [usage.md](usage.md) / [model-catalog-json.md](model-catalog-json.md)）。

## 同步写测试（强制）

- 新增 CLI 参数、新增函数、修 bug，必须同步加回归测试，不留 TODO。
- 纯函数（解析、渲染、打分）加单测；落盘行为加 CLI 测试（`subprocess` 端到端或 `mod.main()` + `mock.argv`，仓内两种模式都有）。
- 错误路径也要测：非法值、互斥参数、应拒绝的写入，断言非零退出。
- 跑全量：`python -m pytest tests/ -q`，通过才能提交。

## 兼容底线

- `requires-python >= 3.10`；禁止直接依赖 3.11+ 标准库（`tomllib` 必须带 `tomli` 回退，见三个脚本头的 `try/except`）。
- 新语法先确认 3.10 可跑；注解有 `from __future__ import annotations` 兜底，不要在运行时求值注解。
- 3.10 回退路径要能验证：挡掉标准库 `tomllib`、确认切到 `tomli` 后全量测试仍过。

## 文档去重

- 真源矩阵在 [AGENTS.md](../AGENTS.md)：每种内容只有一份真源文件，其他文档只给链接，不抄。
- 文档间引用统一用 `[path](path)` 语义链接（如 `[usage.md](usage.md)`），不用裸路径或行内标记；外部 URL 保持原样。
- 修脚本行为时，同步修其真源文档（如改默认搜索形态 → 改 [model-catalog-json.md](model-catalog-json.md) 对应行）。

## 文档一致性检查（每次改动后执行）

单源存放还不够，改完必须全仓 grep 核对，防止两处说法打架：

- 枚举值对代码：文档里的 `wire_api`、思考档、输入模态、`shell` / `apply_patch` / `web_search` 合法值，与 `scripts/model_meta.py` 常量逐项对照。
- 默认值对代码：文档所写 `258400` / 五档 / `text` 等默认，与模板 `skill.codex-model-config` 注释块、`--help` 输出对照。
- 路径与保留名：`models.json` / `models_cache.json` 禁用、`<profile>-models.json` 专用、skills 目录位置，全仓确认无矛盾写法。
- 命令只活在一处：改命令前先 grep，[usage.md](usage.md) 之外不留第二份可执行示例。
- 版本要求三处一致：`README` 要点、`pyproject` `requires-python`、本节兼容底线。
- 语义纠正要改全：如某字段含义被证伪（如 `supports_search_tool`），当次把全仓同类表述一次改完，不留旧说法。

冲突时以代码实际行为为准修文档；修文档时疑似重复的表述一律 grep 到底。提交前看 `git diff` 确认每行都是本轮意图，避免把他人并发改动带进来或冲掉。

## 提交前

- `git status` / `diff` / `log --oneline -10` 先看；只暂存本轮意图文件，不碰无关 untracked（如本地 `.python-version`、`main.py`）。
- 扫描密钥与占位符：只允许 `example.invalid` / `<key>` 类占位，不许真实密钥。
- 提交信息沿用仓风格短句（`imp:` / `fix:` / `add:` 开头）。
- 只提交不推送；推送、PR 等明确要求再做。
