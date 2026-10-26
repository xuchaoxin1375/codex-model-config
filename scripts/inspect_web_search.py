#!/usr/bin/env python3
"""One-screen view of the Codex web_search config layers.

Read-only and offline: reads the base config.toml (optionally layered with a
profile), the catalog JSON referenced by ``model_catalog_json``, and prints
only the fields that decide whether hosted ``web_search`` can be sent.

Exit codes: 0 = no blocking gap, 1 = at least one blocking gap,
2 = CLI usage or file access errors.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10: pip install tomli
    import tomli as tomllib

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_profile import (  # noqa: E402
    ERROR,
    INFO,
    WARNING,
    Finding,
    ensure_pipe_utf8,
    load_catalog,
    load_toml,
)
from adjust_context_window import cleaned_path, decode_utf8_output, resolve_codex  # noqa: E402

SEARCH_MODES = ("cached", "live", "indexed", "disabled")
DISPLAY_KEY = "web_search_tool_type"
LITE_KEY = "use_responses_lite"
FORBIDDEN_CATALOG_NAMES = {"models.json", "models_cache.json"}


def default_codex_home() -> Path:
    override = os.environ.get("CODEX_HOME")
    return Path(override).expanduser() if override else Path.home() / ".codex"


def merge_layers(base: dict[str, Any], layer: dict[str, Any]) -> dict[str, Any]:
    """Profile files layer on top of the base config (see ``codex -p --help``)."""
    merged: dict[str, Any] = dict(base)
    for key, value in layer.items():
        current = merged.get(key)
        if isinstance(value, dict) and isinstance(current, dict):
            merged[key] = merge_layers(current, value)
        else:
            merged[key] = value
    return merged


def resolve_catalog(doc: dict[str, Any], *, codex_home: Path) -> tuple[Path | None, str]:
    """Return (path, problem). Path is None when the key is absent or unreadable."""
    raw = doc.get("model_catalog_json")
    if raw is None:
        return None, "model_catalog_json is not set; Codex falls back to the bundled catalog"
    if not isinstance(raw, str):
        return None, f"model_catalog_json must be a string, got {type(raw).__name__}"
    if raw.startswith("~") or not Path(raw).is_absolute():
        return Path(raw).expanduser(), "model_catalog_json must be an absolute path (Codex does not expand ~ or relative paths)"
    return Path(raw), ""


def load_catalog_entries(path: Path) -> tuple[dict[str, dict[str, Any]], str]:
    try:
        data = load_catalog(path)
    except ValueError as exc:
        return {}, str(exc)
    models = data.get("models")
    if not isinstance(models, list):
        return {}, f"catalog {path} has no models array"
    entries = {
        m["slug"]: m for m in models if isinstance(m, dict) and isinstance(m.get("slug"), str)
    }
    return entries, ""


def entry_row(slug: str, entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": slug,
        "use_responses_lite": entry.get(LITE_KEY),
        "web_search_tool_type": entry.get(DISPLAY_KEY),
        "supports_search_tool": entry.get("supports_search_tool"),
    }


def check_search(
    doc: dict[str, Any],
    *,
    catalog_path: Path | None,
    catalog_problem: str,
    entries: dict[str, dict[str, Any]],
    entries_problem: str,
) -> list[Finding]:
    findings: list[Finding] = []
    mode = doc.get("web_search")
    model = doc.get("model")

    if mode is None:
        mode = "cached"
    if not isinstance(mode, str) or mode not in SEARCH_MODES:
        findings.append(Finding(
            ERROR, "E_WEB_SEARCH_MODE",
            f"web_search={mode!r} is not one of {', '.join(SEARCH_MODES)}.",
            "顶层 web_search 写错类型/取值时托管工具形态不可判定;第三方网关实时搜索用 live",
        ))
    elif mode == "disabled":
        findings.append(Finding(
            INFO, "I_MODE_DISABLED",
            "web_search=disabled: hosted search tool is removed from requests.",
            "上游拒收 web_search 时这是正确设置;要搜索改用 live",
        ))
    elif mode == "cached":
        findings.append(Finding(
            INFO, "I_MODE_CACHED",
            "web_search=cached: only the provider index, no live fetch.",
            "要实时搜索用 live(或单次 codex --search)",
        ))

    if mode == "disabled":
        # Tool is removed from requests; catalog fields no longer decide search.
        return findings

    if catalog_problem:
        findings.append(Finding(
            ERROR, "E_CATALOG_PATH", catalog_problem,
            "检查 model_catalog_json 是否绝对路径且文件存在;缺失时目录条目全部不生效",
        ))
        return findings
    if entries_problem:
        findings.append(Finding(
            ERROR, "E_CATALOG_UNREADABLE", entries_problem,
            "目录必须是 {models:[...]};先修 JSON 再看搜索字段",
        ))
        return findings
    if catalog_path is not None and catalog_path.name in FORBIDDEN_CATALOG_NAMES:
        findings.append(Finding(
            WARNING, "W_LEGACY_CATALOG_NAME",
            f"catalog name {catalog_path.name!r} is a Codex-managed filename.",
            "自定义目录用 <profile>-models.json,避免与 Codex 自己写的缓存互覆盖",
        ))
    if not isinstance(model, str) or model not in entries:
        findings.append(Finding(
            ERROR, "E_CATALOG_SLUG",
            f"no catalog entry with slug == model {model!r}.",
            "slug 必须与 model= 全等;不匹配时走 fallback 元数据,搜索字段不生效",
        ))
        return findings

    entry = entries[model]
    lite = entry.get(LITE_KEY)
    if mode != "disabled":
        if lite is True:
            findings.append(Finding(
                ERROR, "E_RESPONSES_LITE",
                f"catalog entry {model!r} has use_responses_lite=true.",
                "托管 web_search 不会进顶层 tools;用 adjust_context_window.py --responses-lite false 整份菜单一起改",
            ))
        elif lite is False:
            findings.append(Finding(
                INFO, "I_LITE_OFF",
                f"{model!r}: use_responses_lite=false, hosted web_search can be sent.",
                "目录层成立;网关是否原样透传仍需 exec --json 看 web_search 事件",
            ))
        else:
            findings.append(Finding(
                WARNING, "W_LITE_UNSET",
                f"{model!r} has no use_responses_lite field.",
                "内置条目均为 true;缺字段时以下发结果为准,显式写 false 更稳",
            ))

    ws_type = entry.get(DISPLAY_KEY)
    if ws_type is None and mode != "disabled":
        findings.append(Finding(
            WARNING, "W_WS_TYPE_MISSING",
            f"{model!r} has no web_search_tool_type.",
            "缺省按 text 处理;显式写 text 便于核对(图片搜索才 text_and_image)",
        ))
    elif ws_type not in (None, "text", "text_and_image"):
        findings.append(Finding(
            ERROR, "E_WS_TYPE",
            f"web_search_tool_type={ws_type!r} is not text/text_and_image.",
            "该字段只定工具形态,取值写错会连带目录校验失败",
        ))

    if mode != "disabled":
        others = [s for s, e in entries.items() if e.get(LITE_KEY) is True and s != model]
        if others:
            findings.append(Finding(
                WARNING, "W_MENU_MIXED",
                f"{len(others)} other catalog entr{'y' if len(others) == 1 else 'ies'} still use_responses_lite=true.",
                "整份菜单一起改;否则换模型时搜索静默失效:" + ", ".join(sorted(others)[:5])
                + (" ..." if len(others) > 5 else ""),
            ))
    return findings


def profile_overrides(codex_home: Path, base: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(codex_home.glob("*.config.toml")):
        try:
            doc = load_toml(path)
        except ValueError as exc:
            rows.append({"profile": path.name[: -len(".config.toml")], "error": str(exc)})
            continue
        merged = merge_layers(base, doc)
        rows.append({
            "profile": path.name[: -len(".config.toml")],
            "model": doc.get("model", "<inherit>"),
            "web_search": doc.get("web_search", "<inherit>"),
            "catalog": doc.get("model_catalog_json", "<inherit>"),
            "effective_web_search": merged.get("web_search", "cached"),
        })
    return rows


def bundled_diff(model: str, entries: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Compare the effective entry against ``codex debug models --bundled``."""
    env = os.environ.copy()
    env["PATH"] = cleaned_path()
    try:
        executable = resolve_codex()
        proc = subprocess.run(
            [executable, "debug", "models", "--bundled"],
            capture_output=True, timeout=30, check=False, env=env,
        )
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        return {"available": False, "reason": str(exc)}
    if proc.returncode != 0:
        detail = decode_utf8_output(proc.stderr or proc.stdout, errors="replace").strip()[:200]
        return {"available": False, "reason": f"exit {proc.returncode}: {detail}"}
    try:
        data = json.loads(decode_utf8_output(proc.stdout))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"available": False, "reason": f"unparsable debug models output: {exc}"}
    bundled = {m["slug"]: m for m in data.get("models", []) if isinstance(m, dict) and "slug" in m}
    mine = entries.get(model)
    if mine is None or model not in bundled:
        return {"available": True, "model": model, "differences": {}, "note": "entry missing on one side"}
    keys = (LITE_KEY, DISPLAY_KEY, "supports_search_tool", "context_window")
    differences = {
        k: {"custom": mine.get(k), "bundled": bundled[model].get(k)}
        for k in keys if mine.get(k) != bundled[model].get(k)
    }
    return {"available": True, "model": model, "differences": differences}


def render(view: dict[str, Any]) -> str:
    lines: list[str] = ["codex web_search layers", ""]
    lines.append(f"  base config   {view['base_config']}")
    lines.append(f"  profile       {view['profile'] or '(none)'}")
    lines.append("")
    eff = view["effective"]
    lines.append("effective")
    lines.append(f"  model         {eff['model']}")
    lines.append(f"  provider      {eff['provider']}  {eff['base_url']}")
    lines.append(f"  web_search    {eff['web_search']}")
    lines.append(f"  catalog       {eff['catalog']}")
    if eff.get("catalog_entries") is not None:
        lines.append(f"  entries       {eff['catalog_entries']}")
    lines.append("")

    lines.append("checks")
    for finding in view["findings"]:
        mark = {ERROR: "[!!]", WARNING: "[! ]", INFO: "[ok]"}[finding["severity"]]
        lines.append(f"  {mark} {finding['code']}: {finding['message']}")
    lines.append("")

    rows = view["catalog_rows"]
    if rows:
        lines.append("catalog search fields (* = active model)")
        width = max(len(r["slug"]) for r in rows) + 2
        for row in rows:
            mark = "*" if row["slug"] == eff["model"] else " "
            lite = "unset" if row["use_responses_lite"] is None else str(row["use_responses_lite"]).lower()
            ws = row["web_search_tool_type"] or "unset"
            lines.append(f"  {mark} {row['slug']:<{width}} lite={lite:<6} ws={ws}")
        lines.append("")

    if view["profiles"]:
        lines.append("profiles (top-level overrides; <inherit> = base value)")
        ok_rows = [r for r in view["profiles"] if "error" not in r]
        name_w = max([len(r["profile"]) for r in view["profiles"]] + [7]) + 2
        model_w = max([len(r["model"]) for r in ok_rows] + [5]) + 2
        for row in view["profiles"]:
            if "error" in row:
                lines.append(f"  {row['profile']:<{name_w}} unreadable: {row['error']}")
                continue
            lines.append(
                f"  {row['profile']:<{name_w}} model={row['model']:<{model_w}} "
                f"web_search={row['web_search']:<10} catalog={row['catalog']}"
            )
        lines.append("")

    if view.get("bundled") is not None:
        bundled = view["bundled"]
        lines.append("vs bundled catalog (--bundled)")
        if not bundled["available"]:
            lines.append(f"  skipped: {bundled['reason']}")
        elif bundled.get("note"):
            lines.append(f"  {bundled['model']}: {bundled['note']}")
        elif bundled["differences"]:
            for key, pair in bundled["differences"].items():
                lines.append(f"  {key}: custom={pair['custom']!r} bundled={pair['bundled']!r}")
        else:
            lines.append(f"  {bundled['model']}: identical search fields")
        lines.append("")

    lines.append("next")
    for step in view["next_steps"]:
        lines.append(f"  - {step}")
    return "\n".join(lines)


def next_steps(findings: list[Finding]) -> list[str]:
    if any(f.code == "I_MODE_DISABLED" for f in findings):
        return [
            "web_search=disabled:托管搜索工具不会下发,这是有意关闭时无需处理",
            "要启用搜索:顶层改 web_search = \"live\" 并确认目录 use_responses_lite=false",
        ]
    fatal = [f for f in findings if f.severity == ERROR]
    if fatal:
        return [
            "先修 ERROR 项;目录/模式不成立时后端验证没有意义",
            "修完重跑本脚本,再跑 check_profile.py 看完整 profile 告警",
        ]
    return [
        "配置层已成立;网关是否原样透传 /responses 顶层 tools 仍需一次真实请求取证",
        "会话内用 exec --json 看是否出现 \"type\":\"web_search\" 的 item 事件",
        "真实搜索按次计费:一次请求、不重试,同一配置至多验一次",
    ]


def build_view(
    *,
    codex_home: Path,
    config_path: Path,
    profile: str | None,
    all_profiles: bool,
    bundled: bool,
) -> tuple[dict[str, Any], int]:
    base_doc = load_toml(config_path)
    doc = base_doc
    if profile:
        layer_path = codex_home / f"{profile}.config.toml"
        if not layer_path.exists():
            raise ValueError(f"profile file not found: {layer_path}")
        doc = merge_layers(base_doc, load_toml(layer_path))

    catalog_path, catalog_problem = resolve_catalog(doc, codex_home=codex_home)
    entries: dict[str, dict[str, Any]] = {}
    entries_problem = ""
    if catalog_path is not None and catalog_problem == "":
        if not catalog_path.exists():
            catalog_problem = f"catalog not found: {catalog_path}"
        else:
            entries, entries_problem = load_catalog_entries(catalog_path)
    if catalog_problem:
        entries = {}

    findings = check_search(
        doc,
        catalog_path=catalog_path,
        catalog_problem=catalog_problem,
        entries=entries,
        entries_problem=entries_problem,
    )

    provider_id = doc.get("model_provider", "")
    provider: dict[str, Any] = {}
    providers = doc.get("model_providers")
    if isinstance(providers, dict) and isinstance(providers.get(provider_id), dict):
        provider = providers[provider_id]

    model = doc.get("model", "<unset>")
    rows = sorted(entries.values(), key=lambda e: (e["slug"] != model, e["slug"]))
    view: dict[str, Any] = {
        "base_config": str(config_path),
        "profile": profile,
        "effective": {
            "model": model,
            "provider": provider_id or "<unset>",
            "base_url": provider.get("base_url") or "<unset>",
            "web_search": doc.get("web_search", "cached"),
            "catalog": str(catalog_path) if catalog_path else "<unset>",
            "catalog_entries": len(entries) if entries else None,
        },
        "findings": [asdict(f) for f in findings],
        "catalog_rows": [entry_row(e["slug"], e) for e in rows],
        "profiles": profile_overrides(codex_home, base_doc) if all_profiles else [],
        "bundled": bundled_diff(model, entries) if bundled else None,
        "next_steps": next_steps(findings),
    }
    return view, 1 if any(f.severity == ERROR for f in findings) else 0


def parse_args(argv: list[str] | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path, default=None,
                        help="Codex home directory; default: $CODEX_HOME or ~/.codex")
    parser.add_argument("--file", type=Path, default=None,
                        help="base config TOML; default: <codex-home>/config.toml")
    parser.add_argument("-p", "--profile", default=None,
                        help="layer <codex-home>/<profile>.config.toml on top of the base config")
    parser.add_argument("-a", "--all-profiles", action="store_true",
                        help="list top-level overrides of every <name>.config.toml")
    parser.add_argument("-b", "--bundled", action="store_true",
                        help="diff the active entry against `codex debug models --bundled` (local, no network)")
    parser.add_argument("--json", action="store_true", help="print the view as JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = parse_args(argv)
    args = parser.parse_args(argv)
    codex_home = (args.codex_home or default_codex_home()).expanduser()
    config_path = (args.file or codex_home / "config.toml").expanduser()
    if not config_path.exists():
        parser.error(f"config file not found: {config_path}")
    ensure_pipe_utf8()
    try:
        view, code = build_view(
            codex_home=codex_home,
            config_path=config_path,
            profile=args.profile,
            all_profiles=args.all_profiles,
            bundled=args.bundled,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(view, ensure_ascii=False, indent=2))
    else:
        print(render(view))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
