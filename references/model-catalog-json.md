# model_catalog_json 阅读指南

给要读、改、或排查 `<profile>-models.json` 的人。目录从哪来、要不要上网，见 [catalog-source.md](catalog-source.md)。窗口公式见 [context-window-guide.md](context-window-guide.md)。

## 先记住三件事

1. TOML 里的 `model_catalog_json` 只是**绝对路径**，指向一份本地 JSON。不是供应商接口，也不会去拉 OpenAI。
2. 配了它之后，这份 JSON **整份替换**当前进程的内置模型菜单。缺字段的短文件、或只含一条自定义模型，都会出问题。
3. 自定义模型能不能调工具，主要看这一条的 `tool_mode` / `include_*_instructions` / `apply_patch_tool_type`，不是看 `base_url`。

不配 `model_catalog_json` 时，未知 slug 仍能跑：窗口走 fallback（约 `272000 × 95%`），工具走客户端默认（直连）。这就是「注释掉 catalog 后 Grok 反而能调工具」的原因。

## 和哪些文件不是一回事

| 名字 | 角色 | 要不要手改 |
|---|---|---|
| `~/.codex/<profile>-models.json` | 本 skill 维护的菜单，给 `model_catalog_json` 用 | 用脚本改 |
| TOML 的 `model_catalog_json` | 告诉 Codex 启动时读哪份菜单 | 只写在设置了 `model = "<slug>"` 的那份 profile |
| `~/.codex/models.json` | Codex 内部文件，schema 更严 | **不要**拿来当 catalog |
| `codex debug models --bundled` | 本机安装包里的出厂菜单 | 只作导出源 |
| `models_cache.json` | 用过的模型缓存，slug 常带 `x-ai/` 前缀 | 只作克隆骨架 |

## 文件长什么样

顶层永远是 `{ "models": [ ... ] }`。前面是完整 bundled 列表，最后追加自定义模型：

```json
{
  "models": [
    { "slug": "gpt-6-astra", "shell_type": "unified_exec", "tool_mode": "code_mode_only" },
    { "slug": "gpt-5.5", "shell_type": "unified_exec", "include_skills_usage_instructions": true },
    {
      "slug": "grok-4.6",
      "display_name": "grok-4.6",
      "shell_type": "unified_exec",
      "apply_patch_tool_type": "freeform",
      "include_skills_usage_instructions": true,
      "context_window": 300000
    }
  ]
}
```

`slug` 必须和 profile 里 `model = "..."` **完全相等**。`x-ai/grok-4.6` 对不上 `grok-4.6`。

## 主要字段（每条新模型必须逐项明确）

bundled 一条大约 35–40 个键。下面这些决定窗口、档位、工具能否用，每条新模型都要定，CLI 覆盖见行内参数（完整命令见 [usage.md](usage.md)）。

| 字段 | 作用 | 第三方怎么定 | 填错会怎样 |
|---|---|---|---|
| `slug` | 和 TOML `model` 对齐的主键 | 必须与 `model = "..."` 全等（含 `x-ai/` 这类前缀） | 窗口、档位、工具全不生效 |
| `shell_type` | Codex 据此决定暴露哪套 shell 工具 | 现网 bundled 用 `unified_exec`；缺了脚本会补 | 缺失可能直接拒启动；`default` 走旧 shell |
| `context_window` | 目录声明的基础窗口 | 按官方或 skill 默认 `258400`（`--context-window`） | 与目标不一致则窗口不对 |
| `max_context_window` | TOML `model_context_window` 能达到的上限 | 与目标值相同（精确命中） | 小于目标则窗口被钳回去 |
| `effective_context_window_percent` | 可用比例：`context_window × 该百分比` | 精确命中用 `100`（`--effective-percent`） | 沿用 95 会再打 95 折 |
| `supported_reasoning_levels` | 选择器里能选哪些思考档 | `--reasoning-levels` 写入 | UI 档位缺几个 |
| `default_reasoning_level` | 没手选时的目录默认档 | 一般 `medium`（`--default-reasoning-level`） | 默认档不符合预期 |
| `input_modalities` | 模型可收哪些输入；无 `image` 则不按视觉处理 | 默认 `text,image`；`--input-modalities` 覆盖，只允许 `text,image,audio`（上游 omni 的 `video` 不要照抄，本版 Codex 整份拒读） | 能贴图也不会按视觉模型处理 |
| `tool_mode` | 工具暴露方式 | 省略或 `direct`；`code_mode_only` 会把 shell / apply_patch / MCP 收到嵌套工具里，脚本默认去掉它，显式 `--clone-from gpt-6-astra` 才保留 | 第三方常表现为很多工具调不了 |
| `apply_patch_tool_type` | 有无 `apply_patch`；`null` 时模型只能整文件重写，且无改文件摘要 | 默认 `freeform`；实测全失败则该条改回 `null`（`--apply-patch-type null`，判定见 2a） | 选错则改文件走弯路、浪费 token |
| `include_skills_usage_instructions` | 是否注入 skills 用法说明 | 脚本默认打开三套（`true`） | 缺省=`false`，模型不会用 skills |
| `include_plugin_usage_instructions` | 是否注入插件说明 | 同上 | 同上 |
| `include_apps_usage_instructions` | 是否注入 apps 说明 | 同上（缺省反而是 `true`，脚本显式打开） | 同上 |
| `supports_search_tool` | 是否暴露延迟工具发现（MCP / app 扩展工具的 `tool_search` 面；**不是** web search 开关，详见 [tool-calling.md](tool-calling.md)） | 有扩展工具生态 `true`；无搜索模型用 `--no-supports-search-tool` | 关掉后模型看不到延迟发现的扩展工具 |
| `web_search_tool_type` | 搜索工具形态 | 缺省脚本补 `text`；仅供应商文档化图片搜索才用 `text_and_image`（`--web-search-type`）；Grok 保持 `text` | 误抄别家形态可能不稳 |
| `visibility` / `supported_in_api` | 选择器可见、API 可用 | `list` / `true` | `hide` 则选择器里看不到 |

本 skill 合成第三方条目时：克隆一条**直连工具**骨架（优先 `gpt-5.5` 这类），去掉 `code_mode_only`，并把三套 `include_*` 打开。显式 `--clone-from gpt-6-astra` 才会保留 code mode。

### apply_patch 擅长与否：判定与适配

目录只能**打开**工具，不能让模型学会 patch 格式。是否给某条 `freeform`，按实测定，不要按供应商宣传定：

1. 默认先给 `freeform`（脚本缺省行为），开新会话做一次真实改文件任务。
2. 若 rollout 里反复出现 `The first line of the patch must be '*** Begin Patch'`、随后回退到 Python/`exec_command` 写文件，且成功率明显低于直写，该条改回 `null`（`--apply-patch-type null`）。`null` 时少绕失败轮次，反而更省 token。
3. `null` 只是该条的决定：`shell_type` 仍保持 `unified_exec`，不要整份目录回滚；接线修好后再开 `freeform`。
4. 已知实例：Grok 4.6 当前属此类（见 [常见陷阱.md](常见陷阱.md)）；GPT / DeepSeek 保持 `freeform`。
5. 网关直接拒收（确定性）：若真实请求返回 `tool type 'custom' is not supported`（本版 Codex 以 `custom` 类型发出 `apply_patch`，Xiaomi 等网关不认），不用试错，直接给 `null`。定位方法：本地回显代理抓请求体看 `tools[]` 的 `type`，见 [case-xiaomi-mimo.md](case-xiaomi-mimo.md)。

脚本行为：`--apply-patch-type null` 会为目标条保留显式 `null`，且全表回填时不覆盖其他条已有的显式 `null`；不传该参数时空值仍补 `freeform`（旧缓存的 `null` 不要照抄）。

## 次要字段（跟克隆源走，不手写）

下面这些不决定窗口和工具能否用，克隆时跟着骨架走即可；手改人设或产品文案反而易带偏行为。窗口公式见 [context-window-guide.md](context-window-guide.md)。

| 字段 | 说明 |
|---|---|
| `display_name` / `description` | 选择器显示名与描述；抄骨架或按 slug 填，不影响行为 |
| `priority` | 排序权重；跟克隆源走 |
| `upgrade` | OpenAI 的升级文案；不要改成别家的升级提示 |
| `availability_nux` | 新模型引导标记；跟走 |
| `service_tiers` / `additional_speed_tiers` | 计费与速率层；跟走 |
| `auto_compact_token_limit` | 模型自己的压缩线；脚本写成 `null`，改由 TOML `model_auto_compact_token_limit` 管 |
| `comp_hash` | 可选缓存键；上下文值变化时脚本更新 |
| `truncation_policy` | 超长内容怎么截；跟克隆源走 |
| `base_instructions` / `model_messages` | Codex 给该模型的系统提示；从 `gpt-5.5` 克隆带 GPT-5 工具用法，从 `gpt-6-astra` 克隆带偏 code mode 的 GPT-6 提示——这就是骨架不能随便用 bundled 第一行的原因；不手写 |
| `support_verbosity` / `default_verbosity` | 只决定发不发 `text.verbosity`；仅上游官方文档化才开，不跨供应商抄 |
| `default_reasoning_summary` | 推理摘要默认档；跟走 |
| `supports_image_detail_original` | 原图细节；跟走 |
| `use_responses_lite` | 精简 Responses 形态；跟走 |
| `node_repl_*` | Node REPL 相关开关；跟走 |
| `model_specialty` | 模型专长标注；跟走 |
| `experimental_supported_tools` | 新模型才有的实验工具（如 `clock`）；不认识的客户端会忽略，不盲目照抄 `gpt-6-astra` |
| 未来未知键 | 新版本 bundled 可能再多键；**保留**，不要删（脚本从最富 donor 自动补） |

## Codex 升级后字段会变吗

会。bundled 第一行往往是最新旗舰（例如2026.09.17时,主模型是 `gpt-6-astra`），新键也最先出现在那里。

本 skill 的兼容策略：

1. **行为骨架**按「能不能当普通 coding agent」打分：直连工具 + skills/plugin 说明优先，而不是 bundled 顺序。
2. **未知新键**从字段最多、且排在 bundled 最前的那一行补上（不覆盖 `tool_mode`、人设、窗口、slug）。
3. 合成后再强制：去掉 `code_mode_only`，打开 skills/plugin/apps 说明，空 `apply_patch` 补 `freeform`（用户显式 `--apply-patch-type null` 的条除外）。

因此：新模型进 bundled 后，一般不用改脚本就能带上新键；同时又不会把第三方模型再次收进 code mode。若官方明确某个第三方模型就该用 code mode，才传 `--clone-from <slug>`。

脚本**不会**猜新键的含义，也不会为写 catalog 去访问 OpenAI。

## 怎么验证

```bash
codex -c model_catalog_json='"/home/<user>/.codex/<profile>-models.json"' debug models > /tmp/codex-models-debug.json
```

在输出里找到你的 `slug`，确认：

- `slug` 与 TOML `model=` 全等，`shell_type` 存在（`unified_exec`）
- `tool_mode` 不是 `code_mode_only`（除非有意）；`include_skills/plugin/apps_usage_instructions` 为 `true`
- `apply_patch_tool_type` 是有意的值（`freeform` 或经实测的 `null`），`web_search_tool_type`/`supports_search_tool` 符合该模型
- `context_window`/`max_context_window`/`effective_context_window_percent` 与目标一致
- `supported_reasoning_levels`/`default_reasoning_level`、`input_modalities`、`visibility=list`、`supported_in_api=true` 与预期一致

改完后必须**新开会话**。已有线程不会重载 catalog。不要把路径写进默认 `config.toml`，除非你就是要把所有会话的内置菜单换掉。

## 快速对照：出问题先看哪

| 现象 | 先查 |
|---|---|
| 启动失败 / builder error | 路径不是绝对路径、指向了 `models.json`、或缺 `shell_type` |
| 窗口没生效 | `slug` 和 `model=` 不一致，或只改了 TOML 没改 catalog |
| 思考档缺几个 | 改 `supported_reasoning_levels`，不是只改 `model_reasoning_effort` |
| 很多工具调不了，注释 catalog 又好了 | 这条是 `code_mode_only` 或短条目缺工具字段 |
| 选择器里 OpenAI 模型消失 | catalog 不是「完整 bundled + 一条自定义」，只剩几条 |
