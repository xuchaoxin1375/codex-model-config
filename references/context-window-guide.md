# Codex 上下文窗口字段指南

本文讲本地窗口预算、目录上限和压缩阈值。顺序见 [workflow.md](workflow.md)，参数以脚本 `--help` 为准，命令见 [usage.md](usage.md)。本地配置不会增加提供方实际支持的上下文容量；skill 默认值只供缺元数据时初始化，不能作为上游能力证明。

## 有效窗口

1. 顶层 `model_context_window` 已设置时，原始窗口取该值；目录有 `max_context_window` 时再取两者较小值。
2. 未设置顶层覆盖时，取目录 `context_window`，缺失时才退到 `max_context_window`；未知 slug 则使用客户端 fallback。
3. 有效窗口 `effective = floor(raw_window × effective_context_window_percent / 100)`。百分比字段写 `95` 代表 95%，不是直接乘以 95。

当目标指 UI 显示的有效预算时，脚本可将 TOML `model_context_window`、目录 `context_window` 与 `max_context_window` 都设为目标值，再显式设有效比例为 100。目标指上游总容量时，可保留比例为系统提示、工具定义和输出留余量；不要为了凑 UI 数字擅自去掉余量。

已知 slug 且目标原始窗口未超过 bundled 的 `max_context_window` 时，可直接用生效 TOML 的顶层覆盖，无需仅为抬高窗口替换整份目录。需要改变上限、有效比例或补未知 slug 时才维护自定义目录。保留 95% 有效比例时，有效预算目标 `T` 所需的原始窗口至少为 `ceil(T × 100 / 95)`，再核对目录上限与上游容量。

脚本按有效窗口的比例生成压缩阈值：原始窗口 400,000、有效比例 80%、压缩比例 90%，得到有效窗口 320,000、配置压缩阈值 288,000。显式阈值不得大于有效窗口。当前 Codex 在默认 `total` 计数范围还会以原始窗口的 90% 为上限：未配置时按 `raw_window × 9 / 10` 派生，配置了则取 `min(配置值, raw_window × 9 / 10)`；设置更高值不保证推迟压缩。`model_auto_compact_token_limit_scope = "body_after_prefix"` 只计前缀之后的增长，阈值含义不同，不能与总上下文 token 直接比较；脚本保留原设置不覆盖。

## 各字段位置

| 字段 | 文件 | 含义 |
|---|---|---|
| `model_context_window` | 生效的默认配置或 profile TOML | 本地原始窗口覆盖值，不是提高上游容量的 API 参数 |
| `model_auto_compact_token_limit` | profile TOML | 压缩阈值 |
| `model_catalog_json` | profile TOML | 目录绝对路径（`<profile>-models.json`，禁用保留名） |
| `context_window` / `max_context_window` | 目录条目 | 基础窗口 / 可覆盖上限 |
| `effective_context_window_percent` | 目录条目 | 可用百分比 |
| `auto_compact_token_limit` | 目录条目 | 留 `null`，由 TOML 定 |
| `comp_hash` | 目录条目 | 已有字段随窗口值更新，不能证明窗口生效 |

未知 slug 走 fallback（约 `272000*95%≈258400`）。`slug` 必须与 `model=` 全等。工具字段与校验命令分别见 [model-catalog-json.md](model-catalog-json.md) 与 [usage.md](usage.md)，此处不重复。

## 调整与验证

- 先确认实际启动的配置文件、模型 slug 和 `CODEX_HOME`，修改真正生效的 TOML 及其专用目录。已有模型只调窗口时保留推理档位、工具偏好和其他模型；需要重置为 skill 默认值才显式选择重置。
- 脚本的预览和未确认执行均不得写入配置或目录。正式写入前备份已有文件；只改目录时，TOML 必须已经引用该目录，否则“目录写成功”不会改变会话。
- 同一 profile 的顶层窗口覆盖和压缩阈值会影响选择器内切换的其他模型；目录条目不能覆盖顶层 TOML。窗口或压缩预算不同的模型优先分 profile。
- `debug models` 仅证明本机客户端能读取目录，短请求成功也不能证明大窗口可用。重载并开新会话后核对实际模型和 token 统计中的 `model_context_window`；要声称上游支持目标容量，还需权威规格或受控的大上下文请求。报告分别说明配置写入、客户端加载和上游容量的验证范围。
