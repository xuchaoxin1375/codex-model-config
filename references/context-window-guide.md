# Codex 上下文窗口字段指南

本文只讲窗口如何被目录钳制。提供方、密钥、profile 与完整接入顺序见 [workflow.md](workflow.md)。

## 有效窗口

Codex 不会单独使用 `model_context_window`。最终输入预算还受模型目录条目影响：

```text
effective = min(model_context_window, max_context_window) * effective_context_window_percent
```

若要精确命中目标，把 `context_window` 和 `max_context_window` 都设成该目标，并把 `effective_context_window_percent` 设为 `100`。

`effective_context_window_percent` 的存在，是因为供应商公布的名义上下文可能大于实际可用输入预算。内置 fallback 目录里它默认低于 `100`，所以只改 `model_context_window` 时，运行值仍可能比请求值更小。

## 各字段位置

| 字段 | 文件 | 含义 |
|---|---|---|
| `model_context_window` | `config.toml` | 请求的上下文窗口。 |
| `model_auto_compact_token_limit` | `config.toml` | 压缩阈值。 |
| `model_catalog_json` | `config.toml` | 本进程使用的目录绝对路径。 |
| `context_window` | `models.json` 模型条目 | 该模型声明的基础上下文。 |
| `max_context_window` | `models.json` 模型条目 | 运行时 `model_context_window` 能达到的上限。 |
| `effective_context_window_percent` | `models.json` 模型条目 | 钳制后真正可用的百分比。 |
| `auto_compact_token_limit` | `models.json` 模型条目 | 按模型的压缩限制。留 `null` 则由 `config.toml` 决定。 |
| `comp_hash` | `models.json` 模型条目 | 可选缓存键。上下文值变化时考虑更新。 |

表中的 `config.toml` 也包括 profile 文件 `~/.codex/<profile>.config.toml`。

## 目录结构

自定义目录必须是带 `models` 数组的顶层对象：

```json
{
  "models": [
    { "slug": "my-model", "display_name": "My Model" }
  ]
}
```

如果文件是单个模型对象（没有 `models` 键），加载前先包一层。这是 `model_catalog_json` 解析失败的常见原因。

配置了 `model_catalog_json` 后，它会替换该进程的内置目录。若还要保留内置模型，从完整目录开始改（例如 `/tmp/codex-models.json`，或 `codex debug models --bundled` 的输出），再追加或编辑自定义条目。`--bundled` 是把 Codex 安装包里的菜单抄到磁盘上，不是访问 OpenAI。来源说明见 [catalog-source.md](catalog-source.md)。

## 压缩阈值

使用不超过有效窗口的限制。常用 90%：

```text
compact_limit = effective_window * 0.90
```

目标 400000、有效比例 100% 时，90% 就是 `360000`。

## 手工修改

更新某个模型条目，不要删掉其他字段：

```bash
jq '
  .models = (
    .models | map(
      if .slug == "deepseek-v4-flash-vision-exp"
      then . + {
        context_window: 400000,
        max_context_window: 400000,
        effective_context_window_percent: 100,
        auto_compact_token_limit: null,
        comp_hash: "deepseek-v4-flash-vision-exp-400k"
      }
      else . end
    )
  )
' models.json > models.json.new
mv models.json.new models.json
```

然后设置顶层 TOML 键：

```toml
model_context_window = 400000
model_auto_compact_token_limit = 360000
model_catalog_json = "/home/<user>/.codex/models.json"
```

`model_catalog_json` 必须是绝对路径；相对路径会相对进程工作目录解析，在 VS Code 里不稳定。

## 该改哪份文件

第三方模型经常由 profile 文件选择，也就是 `~/.codex/<profile>.config.toml`，而不是默认 `config.toml`。

默认配置里的 `model_catalog_json` 会替换每一个会话的内置目录。如果 `model = "grok-4.6"` 写在某个 profile 里，就把目录路径写进那个 profile。

`codex --profile` 只对运行时命令生效，不能搭配 `codex doctor`。

## 目录 slug

目录 `slug` 必须和 TOML 的 `model` 值完全一致。缓存里的 `x-ai/grok-4.6` 不会抬高 `model = "grok-4.6"` 的窗口。先克隆对象，再把 `slug` 改成 TOML 里的值。克隆后若 `apply_patch_tool_type` 为空，一般改成 `"freeform"`，`shell_type` 为空或 `default` 时改成 `"unified_exec"`；这与窗口无关。Grok 若 patch 调用全失败则保持 `null`，不要改 `web_search_tool_type`。见 [常见陷阱.md](常见陷阱.md)。

如果还没有 `models.json`，先从本机引导一份完整目录（不需要外网或代理）：

```bash
codex debug models --bundled > ~/.codex/models.json
```

然后追加自定义模型。只含一条模型的目录会把内置模型藏掉。不要为了写 catalog 去下载 OpenAI 目录。

未知 slug 会走内置 fallback，通常是 `272000` 且 `effective_context_window_percent = 95`（`≈ 258400`）。

`~/.codex/models_cache.json` 适合当克隆源，但它的 slug 常常带供应商前缀。

## 校验

CLI：

```bash
codex --strict-config doctor
codex -c model_catalog_json='"/home/<user>/.codex/models.json"' debug models > /tmp/codex-models-debug.json
```

把 JSON 重定向到文件再查询。不要把 `codex debug models` 管道进 Python heredoc，heredoc 会吃掉 stdin。

```bash
python3 -c 'import json; from pathlib import Path; data=json.loads(Path("/tmp/codex-models-debug.json").read_text()); m=next(x for x in data["models"] if x["slug"]=="grok-4.6"); print({k:m.get(k) for k in ["slug","context_window","max_context_window","effective_context_window_percent","apply_patch_tool_type","shell_type"]})'
```

VS Code 要用新的 app-server 进程，并检查 `model/list`。测试前先重载窗口：

```text
Ctrl+Shift+P
Developer: Reload Window
```

重载后开新对话。已有线程和已经在跑的 app-server 会保留旧目录和旧窗口值。

## 排障

- **目录解析失败：** 确认文件是 `{"models": [...]}`，不是裸的单个模型对象。
- **自定义模型在 VS Code 里消失：** 旧扩展或编辑前就启动的 app-server 不会重载目录。重载窗口，并使用当前已安装的最新扩展。
- **上下文仍低于目标：** 检查 `max_context_window` 和 `effective_context_window_percent`，其中一个在钳制。
- **内置模型消失：** 自定义目录替换了整份内置目录。恢复完整目录后再追加自定义条目。
- **供应商拒绝请求：** 本地数值不会改变上游上限。先确认所选模型确实支持目标上下文。
- **改错了 TOML：** `model_catalog_json` 写进了默认 `config.toml`，而 `model=` 在 profile 里。改 profile。
- **slug 不一致：** 目录是 `x-ai/grok-4.6`，TOML 是 `model = "grok-4.6"`。把 `slug` 改成 TOML 里的值。
- **`codex --profile ... doctor` 报错：** `--profile` 对 `doctor` 无效。改用 `-c model_catalog_json=... debug models`。
