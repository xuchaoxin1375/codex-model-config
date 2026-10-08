# 模型信息源（查规格用，不代替写 catalog）

查模型规格时的唯一信息源说明。写 `model_catalog_json` 仍只用本机 bundled / 现有文件 / `models_cache.json`（见 [catalog-source.md](catalog-source.md)），不下载目录。

## 优先级

用户给定 > 供应商官方 > 第三方目录初筛 > 本机 `models_cache.json`（仅克隆骨架）。官方与用户冲突停下问；第三方数字只做线索，不当上游上限。

## 1. 供应商官方（定稿用）

确认：精确 slug、`base_url`、窗口、思考档位（含 `max`）、`text.verbosity` 是否文档化、输入模态 / `tool_call`。

- OpenAI / Anthropic / Google / xAI / DeepSeek 官方 API 文档与模型页。
- `wire_api` 只有 `responses`；`base_url` / slug 不可猜，缺失请用户核对。

## 2. models.dev（初筛最对口）

- 地址：[`https://models.dev/`](https://models.dev/)；机器接口 `api.json`（按提供方）、`models.json`（按模型本体）、`catalog.json`（合并）；开源 TOML 在 GitHub。
- 可取字段映射：

| 第三方字段 | 写到目录/配置 |
|---|---|
| `limit.context/input/output` | `context_window` / `max_context_window`（再经官方复核） |
| `modalities.input/output`（第三方源可含 `video`/`pdf`，写目录只取 `text,image,audio` 子集） | `--input-modalities` |
| `reasoning` / `tool_call` / `structured_output` | 是否配思考档、是否期待工具调用（`tool_call=true` 不等于 `apply_patch freeform` 可用） |
| `release_date/last_updated/status/deprecated` | 判断模型是否下架、别名是否漂移 |
| `pricing` | 仅做量级参考，不进目录 |

- 注意 `base_model` 继承 + 提供方覆盖：同模型不同站窗口/模态可能不同，配谁用谁的值。

## 3. OpenRouter（服务现实最准）

- 地址：`https://openrouter.ai/models`；接口 `GET /api/v1/models`，支持 `?supported_parameters=tools&input_modalities=text,image&context=128000&sort=newest|context-high-to-low`。
- 可取字段映射：`context_length`、`architecture.input/output_modalities`、`supported_parameters`（`tools/reasoning/structured_outputs/...`）、`reasoning.supported_efforts/default`、`pricing/created/expiration_date/top_provider.context_length`。
- 适合判：是否真支持 `tools`、模态、推理档、是否下架。`tool_success_rate` 仅辅助，不证明 Codex 的 `apply_patch` 可用。

## 4. Artificial Analysis（交叉验证）

- 地址：`https://artificialanalysis.ai/models`，周级更新，数百模型实测。
- 可用：`Context Window`、`Input/Output modality`、`Reasoning`、`Release/Knowledge cutoff`、intelligence/速度/价格。验窗口量级和推理有无，不做机器源。

## 使用顺序

`models.dev` / OpenRouter 初筛窗口 + 模态 + `tool_call` + 档位 → 供应商官方定稿 → 本机 bundled 写目录。工具字段语义见 [model-catalog-json.md](model-catalog-json.md)，命令见 [usage.md](usage.md)。
