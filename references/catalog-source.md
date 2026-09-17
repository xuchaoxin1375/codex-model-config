# 模型目录从哪来

`model_catalog_json` 只是本地 JSON 的绝对路径，不是下载 OpenAI 目录。字段语义见 [model-catalog-json.md](model-catalog-json.md)，命令见 [usage.md](usage.md)。

规则：

- 维护 `<profile>-models.json`，禁用 `~/.codex/models.json` / `models_cache.json`。
- 配了 catalog 即整份替换内置目录：先 `--bootstrap-bundled` 导出完整菜单再追加。
- 写 catalog 不上网、不设代理；查窗口/档位才联网查官方与第三方初筛（见 [model-info-sources.md](model-info-sources.md)），`models_cache.json` 仅克隆骨架。
- 克隆顺序：同 slug 条目 → `--clone-from` → cache 精确/唯一后缀 → bundled 直连骨架（不用 `gpt-6-astra` 首行）→ 合成。`slug` 改成 TOML 值。
- 代理只在实际上游失败且本机已有客户端时用环境变量，不进 TOML。
