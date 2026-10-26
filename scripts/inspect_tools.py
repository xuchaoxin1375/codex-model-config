#!/usr/bin/env python3
"""One-screen view of the Codex tool surface inferred from config + catalog.

Read-only and offline. Infers which tools Codex is configured to expose
(hosted web_search, delayed tool discovery, apply_patch, shell, experimental
tools) from the catalog entry and config.toml. This is config-layer intent,
not proof that a request carries them: that needs one ``/responses`` request
(see references/tool-calling.md).

Exit codes: 0 = view rendered, 2 = CLI usage or file access errors.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_profile import ensure_pipe_utf8, load_toml  # noqa: E402
from inspect_web_search import (  # noqa: E402
    default_codex_home,
    load_catalog_entries,
    merge_layers,
    resolve_catalog,
)

SEND = "send"
OFF = "off"
BLOCKED = "blocked"
UNKNOWN = "unknown"
NESTED = "nested"

SHELL_TYPES = ("unified_exec", "default", "shell_command", "local")
PATCH_TYPES = ("freeform",)


def infer_tools(
    doc: dict[str, Any],
    entry: dict[str, Any] | None,
    *,
    catalog_problem: str,
) -> list[dict[str, str]]:
    """Return one row per tool face: name, state, reason, note."""
    rows: list[dict[str, str]] = []
    mode = doc.get("web_search", "cached")
    lite = entry.get("use_responses_lite") if entry else None
    ws_type = entry.get("web_search_tool_type") if entry else None

    if mode == "disabled":
        rows.append({"tool": "web_search", "state": OFF,
                     "reason": "web_search=disabled", "note": "hosted tool removed from requests"})
    elif entry is None:
        rows.append({"tool": "web_search", "state": UNKNOWN,
                     "reason": catalog_problem or "catalog entry missing",
                     "note": "fix the catalog path/slug before judging"})
    elif lite is True:
        rows.append({"tool": "web_search", "state": BLOCKED,
                     "reason": f"use_responses_lite=true (web_search={mode})",
                     "note": "tool goes to input[].additional_tools, not top-level tools"})
    elif lite is not False:
        rows.append({"tool": "web_search", "state": UNKNOWN,
                     "reason": f"use_responses_lite={lite!r} (web_search={mode})",
                     "note": "field missing; result depends on the client default"})
    elif ws_type not in (None, "text", "text_and_image"):
        rows.append({"tool": "web_search", "state": BLOCKED,
                     "reason": f"web_search_tool_type={ws_type!r}",
                     "note": "invalid form value; catalog validation will reject it"})
    else:
        rows.append({"tool": "web_search", "state": SEND,
                     "reason": f"web_search={mode}, use_responses_lite=false, form={ws_type or 'text (default)'}",
                     "note": "gateway must pass top-level tools through unchanged"})

    search_tool = entry.get("supports_search_tool") if entry else None
    rows.append({
        "tool": "tool_search",
        "state": SEND if search_tool is True else (OFF if entry is not None else UNKNOWN),
        "reason": f"supports_search_tool={search_tool!r}" if entry is not None else catalog_problem or "catalog entry missing",
        "note": "delayed discovery for MCP/app extension tools; not the web search switch",
    })

    patch = entry.get("apply_patch_tool_type") if entry else None
    nested = bool(entry) and entry.get("tool_mode") == "code_mode_only"
    visible_state = NESTED if nested else SEND
    rows.append({
        "tool": "apply_patch",
        "state": visible_state if patch in PATCH_TYPES else (OFF if entry is not None else UNKNOWN),
        "reason": f"apply_patch_tool_type={patch!r}" + (", tool_mode=code_mode_only" if nested else "") if entry is not None else "catalog entry missing",
        "note": "freeform gives per-turn edit summaries; null falls back to whole-file writes"
                + ("; reachable through the nested code-mode tool" if nested else ""),
    })

    shell = entry.get("shell_type") if entry else None
    rows.append({
        "tool": "shell",
        "state": visible_state if shell in SHELL_TYPES else (OFF if entry is not None else UNKNOWN),
        "reason": f"shell_type={shell!r}" + (", tool_mode=code_mode_only" if nested else "") if entry is not None else "catalog entry missing",
        "note": "needed for curl/fetch of a specific URL; network still gated by sandbox + approval"
                + ("; reachable through the nested code-mode tool" if nested else ""),
    })

    if entry is not None:
        tool_mode = entry.get("tool_mode")
        rows.append({
            "tool": "tool_mode",
            "state": "note",
            "reason": f"tool_mode={tool_mode!r}",
            "note": "code_mode_only nests shell/apply_patch/MCP; direct exposure is the default",
        })
        for extra in entry.get("experimental_supported_tools") or []:
            if isinstance(extra, str):
                rows.append({"tool": extra, "state": SEND,
                             "reason": "experimental_supported_tools",
                             "note": "experimental; unknown clients may ignore it"})
    return rows


def include_flags(entry: dict[str, Any] | None) -> dict[str, Any]:
    keys = ("include_skills_usage_instructions",
            "include_plugin_usage_instructions",
            "include_apps_usage_instructions")
    if entry is None:
        return {k: None for k in keys}
    return {k: entry.get(k) for k in keys}


def mcp_servers(doc: dict[str, Any]) -> list[str]:
    servers = doc.get("mcp_servers")
    if isinstance(servers, dict):
        return sorted(str(k) for k in servers)
    return []


def build_view(
    *,
    codex_home: Path,
    config_path: Path,
    profile: str | None,
) -> dict[str, Any]:
    base_doc = load_toml(config_path)
    doc = base_doc
    if profile:
        layer_path = codex_home / f"{profile}.config.toml"
        if not layer_path.exists():
            raise ValueError(f"profile file not found: {layer_path}")
        doc = merge_layers(base_doc, load_toml(layer_path))

    catalog_path, catalog_problem = resolve_catalog(doc, codex_home=codex_home)
    entries: dict[str, dict[str, Any]] = {}
    if catalog_path is not None and catalog_problem == "":
        if not catalog_path.exists():
            catalog_problem = f"catalog not found: {catalog_path}"
        else:
            entries, entries_problem = load_catalog_entries(catalog_path)
            if entries_problem:
                catalog_problem = entries_problem
    model = doc.get("model")
    entry = entries.get(model) if isinstance(model, str) else None

    provider_id = doc.get("model_provider", "")
    provider: dict[str, Any] = {}
    providers = doc.get("model_providers")
    if isinstance(providers, dict) and isinstance(providers.get(provider_id), dict):
        provider = providers[provider_id]

    return {
        "config": str(config_path),
        "profile": profile,
        "model": model,
        "provider": provider_id,
        "base_url": provider.get("base_url"),
        "web_search_mode": doc.get("web_search", "cached"),
        "catalog": str(catalog_path) if catalog_path else None,
        "catalog_problem": catalog_problem,
        "tools": infer_tools(doc, entry, catalog_problem=catalog_problem),
        "mcp_servers": mcp_servers(doc),
        "instructions": include_flags(entry),
        "evidence": [
            {"layer": "config", "done": True,
             "detail": "catalog fields + TOML read by this script"},
            {"layer": "request", "done": False,
             "detail": "one /responses request via a local echo proxy shows top-level tools"},
            {"layer": "session", "done": False,
             "detail": "one exec --json run shows web_search / tool-call item events"},
        ],
    }


def render(view: dict[str, Any]) -> str:
    lines = ["codex tool surface (config-layer inference; not request proof)", ""]
    lines.append(f"  config    {view['config']}")
    lines.append(f"  profile   {view['profile'] or '(none)'}")
    lines.append(f"  model     {view['model']}")
    lines.append(f"  provider  {view['provider']}  {view['base_url']}")
    lines.append("")

    if view["catalog_problem"]:
        lines.append(f"  catalog: {view['catalog_problem']}")
    else:
        lines.append(f"  catalog: {view['catalog']}")
    lines.append("")

    lines.append("inferred from catalog + config")
    width = max(len(r["tool"]) for r in view["tools"]) + 2
    marks = {SEND: "[send]", OFF: "[off ]", BLOCKED: "[!!  ]", UNKNOWN: "[?   ]",
             NESTED: "[nest]", "note": "[note]"}
    for row in view["tools"]:
        lines.append(f"  {marks.get(row['state'], '[?   ]')} {row['tool']:<{width}} {row['reason']}")
        if row["state"] in (BLOCKED, UNKNOWN, NESTED) or row["tool"] in ("web_search", "tool_search", "tool_mode"):
            lines.append(f"          {row['note']}")
    lines.append("")

    lines.append("mcp servers (config.toml [mcp_servers])")
    lines.append("  " + (", ".join(view["mcp_servers"]) if view["mcp_servers"] else "none configured"))
    lines.append("")

    flags = view["instructions"]
    lines.append("instruction surfaces")
    lines.append("  " + "  ".join(f"{k.replace('include_', '').replace('_usage_instructions', '')}={v!r}"
                                   for k, v in flags.items()))
    lines.append("")

    lines.append("evidence ladder")
    for item in view["evidence"]:
        mark = "[x]" if item["done"] else "[ ]"
        lines.append(f"  {mark} {item['layer']:<8} {item['detail']}")
    lines.append("")

    lines.append("next")
    lines.append("  - config layer does not prove request contents; collect one request-layer sample if it matters")
    lines.append("  - request layer: point base_url at a local echo proxy, run one exec, inspect top-level tools")
    lines.append("  - session layer: exec --json, look for item events of type web_search / tool call")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path, default=None,
                        help="Codex home directory; default: $CODEX_HOME or ~/.codex")
    parser.add_argument("--file", type=Path, default=None,
                        help="base config TOML; default: <codex-home>/config.toml")
    parser.add_argument("-p", "--profile", default=None,
                        help="layer <codex-home>/<profile>.config.toml on top of the base config")
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
        view = build_view(codex_home=codex_home, config_path=config_path, profile=args.profile)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(view, ensure_ascii=False, indent=2))
    else:
        print(render(view))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
