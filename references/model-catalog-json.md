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

## 字段：按该不该管来读

bundled 一条大约 35–40 个键。第三方模型只需看下面几层；其余多半是 OpenAI 产品元数据，克隆时跟着走即可。

### 1. 必看（不对就等于没配上）

| 字段 | 作用 | 第三方模型怎么填 |
|---|---|---|
| `slug` | 和 TOML `model` 对齐的主键 | 必须全等 |
| `shell_type` | 缺了 Codex 可能直接拒读目录 | 现网 bundled 用 `unified_exec`；缺了脚本会补 |
| `context_window` / `max_context_window` | 目录声明的窗口；TOML 的 `model_context_window` 不能超过 `max` | 按官方或 skill 默认 `258400` |
| `supported_reasoning_levels` | 选择器里能选哪些思考档 | `--reasoning-levels` 写入 |
| `default_reasoning_level` | 没手选时的目录默认档 | 一般 `medium` |

### 2. 工具能不能调（第三方最容易踩坑）

| 字段 | 高 | 低 / 危险 | 说明 |
|---|---|---|---|
| `tool_mode` | 省略或 `direct` | `code_mode_only` | 省略时走客户端 feature flag（通常是直连工具）。`code_mode_only` 把 shell / apply_patch / MCP 收到 code mode 嵌套工具里；Grok 等第三方模型往往不会用，表现为「很多工具调不了」。 |
| `apply_patch_tool_type` | `freeform` | 缺省 | 没有则可能不提供 apply_patch。 |
| `include_skills_usage_instructions` | `true` | 缺省=`false` | 控制是否注入 skills 用法说明。 |
| `include_plugin_usage_instructions` | `true` | 缺省=`false` | 插件说明。 |
| `include_apps_usage_instructions` | `true` | `false` | 缺省反而是 `true`。 |
| `supports_search_tool` | `true` | 缺省 | 是否暴露 web search。 |
| `web_search_tool_type` | `text` / `text_and_image` | 缺省 | 搜索工具形态。 |
| `experimental_supported_tools` | 按需 | 盲目照抄 `gpt-6-astra` | 例如 `clock`、`send_user_message_async`。新模型才有的实验工具，不认识的客户端会忽略。 |

本 skill 合成第三方条目时：克隆一条**直连工具**骨架（优先 `gpt-5.5` 这类），去掉 `code_mode_only`，并把三套 `include_*` 打开。显式 `--clone-from gpt-6-astra` 才会保留 code mode。

### 3. 窗口与压缩（要改窗口才看）

| 字段 | 作用 |
|---|---|
| `effective_context_window_percent` | 真正可用窗口 = `context_window × 该百分比` |
| `auto_compact_token_limit` | 模型自己的压缩线；脚本写成 `null`，改由 TOML `model_auto_compact_token_limit` 管 |
| `truncation_policy` | 超长内容怎么截；跟克隆源走即可 |

细节和公式见 [context-window-guide.md](context-window-guide.md)。

### 4. 选择器 / 产品层（一般别手改）

`display_name`、`description`、`visibility`（`list` / `hide`）、`priority`、`supported_in_api`、`upgrade`、`availability_nux`、`service_tiers`、`additional_speed_tiers`。

第三方模型：`visibility=list`、`supported_in_api=true` 即可。不要把 OpenAI 的 `upgrade` 文案改成「请升级到 gpt-x」。

### 5. 人设长文本（克隆会带上，通常不手写）

`base_instructions`、`model_messages` 是 Codex 给该模型的系统提示。从 `gpt-5.5` 克隆会带上 GPT-5 的工具用法；从 `gpt-6-astra` 克隆会带上偏 code mode 的 GPT-6 提示。这就是为什么骨架不能随便用 bundled 第一行。

### 6. 可以当透明字段

`comp_hash`、`default_verbosity`、`support_verbosity`、`default_reasoning_summary`、`supports_image_detail_original`、`input_modalities`、`use_responses_lite`、`node_repl_*`、`model_specialty`。新版本 bundled 可能再多键；不认识的键**保留**，不要删。

## Codex 升级后字段会变吗

会。bundled 第一行往往是最新旗舰（现在是 `gpt-6-astra`），新键也最先出现在那里。

本 skill 的兼容策略：

1. **行为骨架**按「能不能当普通 coding agent」打分：直连工具 + skills/plugin 说明优先，而不是 bundled 顺序。
2. **未知新键**从字段最多、且排在 bundled 最前的那一行补上（不覆盖 `tool_mode`、人设、窗口、slug）。
3. 合成后再强制：去掉 `code_mode_only`，打开 skills/plugin/apps 说明，补 `apply_patch_tool_type=freeform`。

因此：新模型进 bundled 后，一般不用改脚本就能带上新键；同时又不会把第三方模型再次收进 code mode。若官方明确某个第三方模型就该用 code mode，才传 `--clone-from <slug>`。

脚本**不会**猜新键的含义，也不会为写 catalog 去访问 OpenAI。

## 怎么验证

```bash
codex -c model_catalog_json='"/home/<user>/.codex/<profile>-models.json"' debug models > /tmp/codex-models-debug.json
```

在输出里找到你的 `slug`，确认：

- `shell_type` 存在
- `tool_mode` 不是 `code_mode_only`（除非你有意如此）
- `include_skills_usage_instructions` 为 true
- `context_window` 和思考档与预期一致

改完后必须**新开会话**。已有线程不会重载 catalog。不要把路径写进默认 `config.toml`，除非你就是要把所有会话的内置菜单换掉。

## 快速对照：出问题先看哪

| 现象 | 先查 |
|---|---|
| 启动失败 / builder error | 路径不是绝对路径、指向了 `models.json`、或缺 `shell_type` |
| 窗口没生效 | `slug` 和 `model=` 不一致，或只改了 TOML 没改 catalog |
| 思考档缺几个 | 改 `supported_reasoning_levels`，不是只改 `model_reasoning_effort` |
| 很多工具调不了，注释 catalog 又好了 | 这条是 `code_mode_only` 或短条目缺工具字段 |
| 选择器里 OpenAI 模型消失 | catalog 不是「完整 bundled + 一条自定义」，只剩几条 |
