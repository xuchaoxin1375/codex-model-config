# 模型目录从哪来

`model_catalog_json` **不是**去网上下载一份 OpenAI 目录，也不是供应商接口返回的实时列表。它只是告诉 Codex：启动时请读**这个本地 JSON 文件**。

写或改 catalog 时，本 skill 只用本机数据。这一步不需要访问 `api.openai.com`，也不需要探测本地代理。

配某个模型的**窗口和思考档位**时可以（也应该）联网查供应商官方文档。那是查规格，不是下载目录。查到的数字再写进本机专用 catalog（`<profile>-models.json`）；`models_cache.json` 只提供克隆骨架。不要覆盖 Codex 自己的 `~/.codex/models.json`。

目录形状、该改哪份 TOML、校验命令见 [workflow.md](workflow.md)。窗口字段如何钳制见 [context-window-guide.md](context-window-guide.md)。

## 两个容易混的名字

| 名字 | 是什么 | 写在哪里 |
|---|---|---|
| `<profile>-models.json` | 本 skill 维护的本地模型菜单：slug、窗口、思考档、`shell_type` 等 | 通常是 `~/.codex/<profile>-models.json` |
| `models.json` | Codex 自己的目录文件，schema 更严 | **不要**当作 `model_catalog_json` |
| `model_catalog_json` | 指向自定义菜单的绝对路径 | 真正设置了 `model = "<slug>"` 的那份 TOML |

可以把它想成：

- `<profile>-models.json` = 给这个 profile 单独打印的菜单
- `model_catalog_json` = 门口告示「今天用这张纸」，必须写成绝对路径，例如 `/home/alice/.codex/yjwd-grok-models.json`
- `~/.codex/models.json` = Codex 内部文件，缺字段（如 `shell_type`）会直接拒绝启动
- Codex 安装包里的 bundled 目录 = 出厂自带的完整菜单

配了 `model_catalog_json` 之后，这份文件会**整份替换**当前进程的内置目录。所以先导出完整菜单，再追加自定义模型；不要写成只有一条。否则 OpenAI 等内置模型会从选择器里消失。

默认写入 `~/.codex/<profile>-models.json`。若 profile 里已有 `model_catalog_json` 且文件存在，就改那份。`--catalog path.json` 可显式指定已有 JSON（包括非默认文件名）。不要默认去改 Codex 保留的 `models.json`；只有你显式 `--catalog` 时才会动它。

`~/.codex/models.json` 或带波浪号的路径在部分客户端不可靠；必须用绝对路径，且不要指向 Codex 保留文件名 `models.json` / `models_cache.json`。相对路径会相对进程工作目录解析，在 VS Code 里尤其不稳定。

## 创建或修改时用什么

`scripts/init_profile.py` 只新建 profile，**不写** `model_catalog_json`。窗口和目录由 `scripts/adjust_context_window.py` 补，或按下面手工做。

写入前先备份将要改的 TOML 和已有 `<profile>-models.json`。

### 1. 已经有 `<profile>-models.json`

直接在现有专用文件里改对应 `slug`，或追加一条。保留其他模型对象和其他字段。

### 2. 还没有这个文件

从 Codex **本机安装包**里的内置目录导出到**专用文件名**，不是访问外网，也不是写 `~/.codex/models.json`：

```bash
codex debug models --bundled > ~/.codex/yjwd-grok-models.json
```

脚本等价于加 `--bootstrap-bundled`。成功后磁盘上会有一份与当前 Codex 版本匹配的完整菜单，再追加自定义条目。

### 3. 自定义模型还不在目录里

不要手写一整份 DeepSeek / OpenAI 目录。克隆一条现成条目，再把需要的键改掉。

克隆顺序：

1. 现有 `<profile>-models.json` 里的同 slug 条目
2. `--clone-from` 指定的条目
3. `~/.codex/models_cache.json` 里精确匹配，或唯一的 `*/slug` 后缀匹配
4. 克隆后把 `slug` 改成 TOML 里的 `model` 值

`models_cache.json` 是 Codex 用过的模型缓存，适合当模板，但 slug 常常带供应商前缀。例如缓存里是 `x-ai/grok-4.6`，而 TOML 是 `model = "grok-4.6"`，必须把目录 `slug` 改成后者，否则窗口和显示名都不会作用到正在用的模型。

### 4. 把路径写进哪份 TOML

只写进真正设置了 `model = "<slug>"` 的那份文件，常见是 `~/.codex/<profile>.config.toml`。脚本在 `model=` 对不上时会拒绝写入默认 `config.toml`，避免把所有会话的内置目录一起换掉。

```toml
model_catalog_json = "/home/<user>/.codex/yjwd-grok-models.json"
```

不要用供应商 `curl | bash` 安装器覆盖目录：那些脚本常写成「只有这一家模型」。

## 网络和代理

| 你在做什么 | 要不要上网 | 要不要代理 |
|---|---|---|
| 导出 bundled、改 `<profile>-models.json`、写 `model_catalog_json` | 不要 | 不要。本机命令即可。 |
| 核对供应商是否真提供该模型/窗口，或实际发 API 请求 | 可能要访问 `base_url` | 仅当直连失败、且本机已有代理客户端时 |

创建 catalog **不会**去拉 OpenAI 官方目录，也 **不要**为了写 JSON 去扫端口或设置 `HTTP_PROXY`。

模板里 OpenRouter 的 `auth.command` 可在联网环境刷新**该提供方**的官方目录，那是另一条机制，仍不是访问 OpenAI，也不能代替本 skill 的本地 `<profile>-models.json`。

若实际调用上游（例如 `https://api.openai.com` 或中转站）失败，而本机已经开了 Clash / V2Ray 一类客户端，可先试这些常见**本地 HTTP** 代理。用环境变量，不要写进 TOML 或 `models.json`：

- `http://127.0.0.1:7897`
- `http://127.0.0.1:7890`
- `http://127.0.0.1:10808`（有的软件此端口是 HTTP，有的是 SOCKS5）

```bash
export HTTPS_PROXY=http://127.0.0.1:7897
export HTTP_PROXY=http://127.0.0.1:7897
```

先确认该端口真的在听，不要扫全端口。代理只影响出站请求，不能代替 `model_catalog_json`，也不能抬高上游不支持的上下文窗口。
