# Codex 上下文窗口字段指南

本文只讲窗口如何被目录钳制。顺序见 [workflow.md](workflow.md)，命令见 [usage.md](usage.md)。

## 有效窗口

```text
effective = min(model_context_window, max_context_window) * effective_context_window_percent
```

精确命中目标：`context_window` 与 `max_context_window` 都设目标值，`effective_context_window_percent=100`。压缩阈值常用有效窗口的 90%。

## 各字段位置

| 字段 | 文件 | 含义 |
|---|---|---|
| `model_context_window` | profile TOML | 请求窗口 |
| `model_auto_compact_token_limit` | profile TOML | 压缩阈值 |
| `model_catalog_json` | profile TOML | 目录绝对路径（`<profile>-models.json`，禁用保留名） |
| `context_window` / `max_context_window` | 目录条目 | 基础窗口 / 可覆盖上限 |
| `effective_context_window_percent` | 目录条目 | 可用百分比 |
| `auto_compact_token_limit` | 目录条目 | 留 `null`，由 TOML 定 |
| `comp_hash` | 目录条目 | 窗口变时更新 |

未知 slug 走 fallback（约 `272000*95%≈258400`）。`slug` 必须与 `model=` 全等。工具字段与校验命令分别见 [model-catalog-json.md](model-catalog-json.md) 与 [usage.md](usage.md)，此处不重复。
