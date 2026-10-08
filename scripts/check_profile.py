#!/usr/bin/env python3
"""Check a hand-written third-party Codex profile for missing or wrong items.

Read-only: never writes files. Typical catch: ``base_url`` left empty (or
left on the OpenAI default) so requests silently fall back to OpenAI.

Exit codes: 0 = no ERROR findings (warnings allowed), 1 = at least one
ERROR (or warnings with --strict), 2 = CLI usage or file access errors.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10: pip install tomli
    import tomli as tomllib

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from init_profile import ENV_ASSIGN_RE, RESERVED_PROVIDER_IDS, derive_series
from model_meta import WIRE_APIS


ERROR = "ERROR"
WARNING = "WARNING"
INFO = "INFO"

OPENAI_HOST_SUFFIX = "openai.com"
OPENAI_NATIVE_SERIES = {"gpt"}
ALLOWED_MODALITIES = ("text", "image", "audio")
INCLUDE_FLAGS = (
    "include_skills_usage_instructions",
    "include_plugin_usage_instructions",
    "include_apps_usage_instructions",
)


@dataclass
class Finding:
    severity: str
    code: str
    message: str
    hint: str = ""


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def load_toml(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{path} is not valid TOML: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} does not contain a TOML table")
    return data


def load_catalog(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read catalog {path}: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"catalog {path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"catalog {path} top level is not an object")
    return data


def env_key_present(env_file: Path, key: str) -> bool:
    """True when KEY= exists in the process env or in the dotenv file."""
    if os.environ.get(key):
        return True
    try:
        text = env_file.expanduser().read_text(encoding="utf-8")
    except OSError:
        return False
    for line in text.splitlines():
        match = ENV_ASSIGN_RE.match(line)
        if match and match.group(2) == key and match.group(4).strip():
            return True
    return False


def check_toml(
    doc: dict[str, Any],
    *,
    env_file: Path,
    check_env: bool,
) -> tuple[list[Finding], dict[str, Any]]:
    """Validate the profile TOML. Returns (findings, context for catalog)."""
    findings: list[Finding] = []
    ctx: dict[str, Any] = {}

    provider = doc.get("model_provider")
    model = doc.get("model")
    if not provider or not isinstance(provider, str):
        findings.append(
            Finding(ERROR, "E_PROVIDER_MISSING", "top-level model_provider is missing.",
                    "手写第三方配置必须显式设置 model_provider,见 template.config.toml")
        )
        return findings, ctx
    if provider == "provider-id":
        findings.append(
            Finding(ERROR, "E_PLACEHOLDER_PROVIDER", "model_provider is still the template placeholder.",
                    "把 provider-id 全量替换为提供方 id,不要只改第一处")
        )
    if provider in RESERVED_PROVIDER_IDS:
        findings.append(
            Finding(ERROR, "E_RESERVED_PROVIDER", f"provider id {provider!r} is reserved.",
                    "换一个 --provider;OpenAI 兼容的 GPT 模型优先用 gpt")
        )
    if not model or not isinstance(model, str):
        findings.append(
            Finding(ERROR, "E_MODEL_MISSING", "top-level model is missing.",
                    "model 只能填供应商提供的可用模型型号名称,不可猜")
        )
        return findings, ctx
    if model == "model-id":
        findings.append(
            Finding(ERROR, "E_PLACEHOLDER_MODEL", "model is still the template placeholder.",
                    "按供应商提供的可用型号填写 model")
        )
    ctx["provider"] = provider
    ctx["model"] = model

    sections = doc.get("model_providers")
    section: dict[str, Any] = {}
    if isinstance(sections, dict) and isinstance(sections.get(provider), dict):
        section = sections[provider]
    else:
        known = sorted(sections.keys()) if isinstance(sections, dict) else []
        findings.append(
            Finding(ERROR, "E_PROVIDER_SECTION_MISSING",
                    f"[model_providers.{provider}] section is missing.",
                    f"现有 section: {known or '无'};section 名必须与 model_provider 全等")
        )

    base_url = section.get("base_url", "") if section else ""
    if not isinstance(base_url, str) or not base_url.strip():
        findings.append(
            Finding(ERROR, "E_BASE_URL_EMPTY", "base_url is empty or missing.",
                    "空 base_url 必 builder error,还可能回退到 OpenAI 默认地址;按供应商 url 填写")
        )
    else:
        url = base_url.strip()
        if not url.startswith(("http://", "https://")):
            findings.append(
                Finding(ERROR, "E_BASE_URL_SCHEME", f"base_url {url!r} has no http(s) scheme.",
                        "base_url 必须是完整 http(s) 地址,不要只写域名")
            )
        elif _host(url).endswith(OPENAI_HOST_SUFFIX):
            try:
                series = derive_series(model)
            except ValueError:
                series = ""
            if series not in OPENAI_NATIVE_SERIES:
                findings.append(
                    Finding(ERROR, "E_BASE_URL_OPENAI_FALLBACK",
                            f"non-GPT model {model!r} points at OpenAI endpoint {url!r}.",
                            "第三方 base_url 忘记自定义,请求会发往 OpenAI;按供应商 url 改写")
                )

    wire_api = section.get("wire_api") if section else None
    if wire_api not in WIRE_APIS:
        if wire_api is None:
            findings.append(
                Finding(WARNING, "W_WIRE_API_MISSING", "wire_api is not set explicitly.",
                        f"当前唯一合法值是 {WIRE_APIS[0]},建议显式写出")
            )
        else:
            findings.append(
                Finding(ERROR, "E_WIRE_API", f"wire_api {wire_api!r} is not supported.",
                        "2026-02 起 chat 已移除,写 chat 直接启动失败;只能是 responses")
            )

    if section and section.get("experimental_bearer_token"):
        findings.append(
            Finding(ERROR, "E_BEARER_TOKEN", "experimental_bearer_token is set in the TOML.",
                    "密钥本体不进 TOML;用户给出的 key 写入 models.env,TOML 只保留 env_key 变量名")
        )

    env_key = section.get("env_key", "") if section else ""
    if env_key == "API_KEY":
        findings.append(
            Finding(WARNING, "W_ENV_KEY_DEFAULT", "env_key is still the template default 'API_KEY'.",
                    "多配置用户记得改为 <PROVIDER>_API_KEY 这类专名,避免串 key")
        )
    elif isinstance(env_key, str) and env_key and check_env:
        if not env_key_present(env_file, env_key):
            findings.append(
                Finding(WARNING, "W_ENV_KEY_MISSING",
                        f"{env_key} is set nowhere (process env nor {env_file}).",
                        f"把 {env_key}=... 写入 {env_file},或本次进程先加载它")
            )

    if section and section.get("requires_openai_auth") is True:
        try:
            series = derive_series(model)
        except ValueError:
            series = ""
        if series not in OPENAI_NATIVE_SERIES:
            findings.append(
                Finding(WARNING, "W_REQUIRES_OPENAI_AUTH",
                        "requires_openai_auth is true for a non-OpenAI provider.",
                        "接入非 openai 模型可以不配置;确认是复制粘贴残留就删掉")
            )

    for key in ("sandbox_mode", "approval_policy"):
        if key in doc:
            findings.append(
                Finding(WARNING, "W_SANDBOX_IN_PROFILE", f"{key} lives in the provider profile.",
                        "沙箱/审批不要写进提供方 profile,只改用户默认 config.toml 或本次 CLI 参数")
            )

    catalog_raw = doc.get("model_catalog_json")
    if isinstance(section, dict) and isinstance(section.get("model_catalog_json"), str):
        findings.append(
            Finding(WARNING, "W_CATALOG_IN_SECTION",
                    "model_catalog_json sits inside [model_providers.<id>] and is ignored.",
                    "catalog 路径只写顶层(设置了 model= 的那份),不要塞进 provider section 里")
        )
    if isinstance(catalog_raw, str) and catalog_raw.strip():
        catalog_path = Path(catalog_raw.strip()).expanduser()
        ctx["catalog_path"] = catalog_path
        if not catalog_path.is_absolute():
            findings.append(
                Finding(WARNING, "W_CATALOG_RELATIVE", f"model_catalog_json {catalog_raw!r} is not absolute.",
                        "catalog 路径只接受绝对路径,相对路径启动时读不到")
            )
        if catalog_path.name == "models.json":
            findings.append(
                Finding(ERROR, "E_CATALOG_RESERVED_NAME",
                        "model_catalog_json points at the reserved models.json.",
                        "models.json 是 Codex 内部文件 schema 更严;用 <profile>-models.json 专用文件")
            )
        elif not catalog_path.exists():
            findings.append(
                Finding(WARNING, "W_CATALOG_MISSING", f"catalog file {catalog_path} does not exist.",
                        "路径写对但文件还没生成时用 adjust_context_window.py --bootstrap-bundled 建一份")
            )
    else:
        findings.append(
            Finding(INFO, "I_NO_CATALOG", "model_catalog_json is not set; built-in menu applies.",
                    "未知 slug 走 fallback 窗口约 272000x95%%;要精确窗口/档位/工具再配专用 catalog")
        )
    return findings, ctx


def check_catalog_entry(entry: dict[str, Any], *, model: str) -> list[Finding]:
    findings: list[Finding] = []
    if not isinstance(entry.get("shell_type"), str) or not entry.get("shell_type"):
        findings.append(
            Finding(ERROR, "E_SHELL_TYPE", f"catalog entry {model!r} has no shell_type.",
                    "缺 shell_type 可能直接拒启动;现网 bundled 用 unified_exec")
        )
    if entry.get("tool_mode") == "code_mode_only":
        findings.append(
            Finding(WARNING, "W_TOOL_MODE_CODE",
                    f"catalog entry {model!r} is code_mode_only.",
                    "shell/apply_patch/MCP/skills 会被收到嵌套工具里;注释 catalog 反而正常即是此因,除非有意保留")
        )
    modalities = entry.get("input_modalities")
    if isinstance(modalities, list):
        bad = [m for m in modalities if m not in ALLOWED_MODALITIES]
        if bad:
            findings.append(
                Finding(ERROR, "E_MODALITY_VIDEO",
                        f"input_modalities {bad} is not accepted by this Codex build.",
                        "只允许 text/image/audio;照抄上游 omni 的 video 会让整份 catalog 无法解析,Codex 拒绝启动")
            )
    patch = entry.get("apply_patch_tool_type")
    if patch is None and "apply_patch_tool_type" in entry:
        findings.append(
            Finding(INFO, "I_APPLY_PATCH_NULL",
                    f"apply_patch_tool_type is null for {model!r}.",
                    "无 apply_patch、无改文件摘要,只能整文件重写;这是实测后的 deliberate 选择就保留")
        )
    elif patch is None:
        findings.append(
            Finding(WARNING, "W_APPLY_PATCH_MISSING",
                    f"apply_patch_tool_type is unset for {model!r}.",
                    "建议显式 freeform,实测全失败再改 null(--apply-patch-type null)")
        )
    off = [k for k in INCLUDE_FLAGS if entry.get(k) is not True]
    if off:
        findings.append(
            Finding(WARNING, "W_INCLUDES_OFF",
                    f"{', '.join(off)} is not true for {model!r}.",
                    "缺省模型不会用 skills/插件;脚本默认三套全开")
        )
    if entry.get("visibility", "list") != "list" or entry.get("supported_in_api", True) is not True:
        findings.append(
            Finding(WARNING, "W_VISIBILITY",
                    f"visibility/supported_in_api hides {model!r} from the picker or API.",
                    "选择器可见要 visibility=list、supported_in_api=true")
        )
    if "context_window" not in entry:
        findings.append(
            Finding(WARNING, "W_CONTEXT_WINDOW",
                    f"context_window is unset for {model!r}.",
                    "窗口走 fallback;按官方值或模板默认 258400 显式设置")
        )
    if "max_context_window" not in entry:
        findings.append(
            Finding(INFO, "I_MAX_WINDOW",
                    f"max_context_window is unset for {model!r}.",
                    "TOML model_context_window 能达到的上限,精确命中时与目标值相同")
        )
    return findings


def check_profile_file(
    path: Path,
    *,
    env_file: Path,
    check_env: bool,
    catalog_override: Path | None,
) -> list[Finding]:
    try:
        doc = load_toml(path)
    except ValueError as exc:
        return [Finding(ERROR, "E_TOML_PARSE", str(exc), "先修 TOML 语法,命令见 usage.md 校验节")]
    findings, ctx = check_toml(doc, env_file=env_file, check_env=check_env)
    if any(f.code in ("E_PROVIDER_MISSING", "E_MODEL_MISSING", "E_TOML_PARSE") for f in findings):
        return findings
    catalog_path = catalog_override or ctx.get("catalog_path")
    if catalog_path is not None and catalog_path.name != "models.json" and catalog_path.exists():
        try:
            catalog = load_catalog(catalog_path)
        except ValueError as exc:
            return findings + [Finding(ERROR, "E_CATALOG_UNREADABLE", str(exc),
                                       "catalog 必须是 {models:[...]} 的 JSON,不要手写短文件")]
        models = catalog.get("models")
        if not isinstance(models, list):
            return findings + [Finding(ERROR, "E_CATALOG_SHAPE",
                                       f"catalog {catalog_path} has no models array.",
                                       "顶层永远是 {models:[...]},前面是完整 bundled,最后追加自定义模型")]
        entry = next((m for m in models
                      if isinstance(m, dict) and m.get("slug") == ctx["model"]), None)
        if entry is None:
            findings.append(
                Finding(ERROR, "E_CATALOG_SLUG",
                        f"no catalog entry with slug == TOML model {ctx['model']!r}.",
                        "slug 必须与 model= 全等,含 x-ai/ 这类前缀;窗口/档位/工具全不生效的常见根因")
            )
        else:
            findings += check_catalog_entry(entry, model=ctx["model"])
    return findings


def ensure_pipe_utf8() -> None:
    """Piped output (agents, tests, files) is UTF-8; a live console keeps its own encoding.

    Direct ``print`` of Chinese hints would otherwise be encoded with the
    console code page (e.g. GBK) and break any UTF-8 consumer downstream.
    Mirrors the intent of model_meta.print_preview_body for machine output.
    """
    stdout = sys.stdout
    isatty = getattr(stdout, "isatty", None)
    if not callable(isatty):
        return
    try:
        if isatty():
            return
    except (OSError, ValueError):
        return
    reconfig = getattr(stdout, "reconfigure", None)
    if callable(reconfig):
        try:
            reconfig(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            pass


def format_text(findings: list[Finding], *, path: Path) -> str:
    lines = [f"check {path}"]
    if not findings:
        lines.append("clean: no findings")
        return "\n".join(lines)
    for f in findings:
        lines.append(f"[{f.severity}] {f.code}: {f.message}")
        if f.hint:
            lines.append(f"  hint: {f.hint}")
    errors = sum(1 for f in findings if f.severity == ERROR)
    warnings = sum(1 for f in findings if f.severity == WARNING)
    lines.append(f"summary: {errors} error(s), {warnings} warning(s)")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--profile", help="profile id; reads <codex-home>/<profile>.config.toml")
    target.add_argument("--file", type=Path, help="explicit profile TOML path (hand-written config)")
    parser.add_argument("--codex-home", type=Path, default=None,
                        help="Codex home directory; default: $CODEX_HOME or ~/.codex")
    parser.add_argument("--catalog", type=Path, default=None,
                        help="explicit catalog JSON path (default: TOML model_catalog_json)")
    parser.add_argument("--env-file", type=Path, default=None,
                        help="dotenv path for the key presence check; default: ~/.config/models.env")
    parser.add_argument("--no-env-check", action="store_true",
                        help="skip the env_key presence check")
    parser.add_argument("--strict", action="store_true",
                        help="warnings also fail (exit 1)")
    parser.add_argument("--json", action="store_true",
                        help="print findings as JSON instead of text")
    return parser


def default_codex_home() -> Path:
    override = os.environ.get("CODEX_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".codex"


def main(argv: list[str] | None = None) -> int:
    parser = parse_args(argv)
    args = parser.parse_args(argv)
    codex_home = args.codex_home or default_codex_home()
    if args.profile:
        path = codex_home / f"{args.profile}.config.toml"
    else:
        path = args.file.expanduser()
    if not path.exists():
        parser.error(f"profile file not found: {path}")
    ensure_pipe_utf8()
    env_file = args.env_file or (Path.home() / ".config" / "models.env")
    findings = check_profile_file(
        path,
        env_file=env_file,
        check_env=not args.no_env_check,
        catalog_override=args.catalog,
    )
    if args.json:
        print(json.dumps(
            [{"severity": f.severity, "code": f.code,
              "message": f.message, "hint": f.hint} for f in findings],
            ensure_ascii=False, indent=2))
    else:
        print(format_text(findings, path=path))
    errors = sum(1 for f in findings if f.severity == ERROR)
    warnings = sum(1 for f in findings if f.severity == WARNING)
    if errors or (args.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
