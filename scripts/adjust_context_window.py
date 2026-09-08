#!/usr/bin/env python3
"""Adjust the context window of one Codex model entry.

Edits:
  - top-level keys in a config/profile TOML
  - the matching entry in models.json

If the catalog or model entry is missing, pass --bootstrap-bundled and/or
--from-cache/--clone-from instead of hand-editing JSON. If --profile points at
a missing TOML, the skill template is used to create it (pass --base-url).
Backups are written beside the edited files.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from shell_hints import print_next_debug_models, python_cmd
from model_meta import (
    REASONING_EFFORTS,
    WIRE_APIS,
    build_reasoning_levels,
    compact_limit_for,
    load_skill_defaults,
    parse_modalities,
    parse_reasoning_levels,
)
from init_profile import default_template, render_template, validate_provider


def toml_value(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def load_catalog(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {"models": data}, data
    if isinstance(data, dict) and "models" in data:
        models = data["models"]
        if not isinstance(models, list):
            raise ValueError(f"{path}: 'models' must be a list")
        return data, models
    if isinstance(data, dict) and "slug" in data:
        return {"models": [data]}, [data]
    raise ValueError(f"{path}: must be a 'models' array or object with 'models'")


def set_top_level_key(text: str, key: str, value: Any) -> str:
    lines = text.splitlines(keepends=True)
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
    section_index = len(lines)
    for index, line in enumerate(lines):
        if line.lstrip().startswith("["):
            section_index = index
            break
    for index in range(section_index):
        if pattern.match(lines[index]):
            lines[index] = f"{key} = {toml_value(value)}\n"
            return "".join(lines)
    lines.insert(section_index, f"{key} = {toml_value(value)}\n")
    return "".join(lines)


def top_level_model(config_text: str) -> str | None:
    data = tomllib.loads(config_text)
    model = data.get("model")
    return model if isinstance(model, str) else None


def find_profiles_with_model(codex_home: Path, slug: str) -> list[Path]:
    hits: list[Path] = []
    for path in sorted(codex_home.glob("*.config.toml")):
        try:
            model = top_level_model(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        if model == slug:
            hits.append(path)
    return hits


def cleaned_path() -> str:
    return os.pathsep.join(
        part.strip() for part in os.environ.get("PATH", "").split(os.pathsep) if part.strip()
    )


def resolve_codex() -> str:
    path = cleaned_path()
    names = ("codex.exe", "codex.cmd", "codex") if os.name == "nt" else ("codex",)
    for name in names:
        found = shutil.which(name, path=path)
        if found:
            return found
    raise RuntimeError(
        "`codex` executable not found on PATH. "
        "In PowerShell, `Get-Command codex` may be a .ps1 shim that Python cannot launch. "
        "Install Codex CLI so `codex.cmd` or `codex.exe` is on PATH."
    )


def decode_utf8_output(raw: bytes | str | None, *, errors: str = "strict") -> str:
    """Decode Codex CLI output as UTF-8.

    Windows `text=True` uses the locale encoding (often GBK), which cannot
    decode bundled models.json and leaves stdout as None.
    """
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    return raw.decode("utf-8", errors=errors)


def dump_bundled_catalog(catalog: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env["PATH"] = cleaned_path()
    try:
        result = subprocess.run(
            [resolve_codex(), "debug", "models", "--bundled"],
            check=False,
            capture_output=True,
            env=env,
        )
    except OSError as exc:
        raise RuntimeError(f"failed to run `codex debug models --bundled`: {exc}") from exc
    try:
        stdout = decode_utf8_output(result.stdout)
    except UnicodeDecodeError as exc:
        raise RuntimeError(
            "`codex debug models --bundled` stdout is not valid UTF-8; "
            "Windows text=True/GBK decoding is the usual cause"
        ) from exc
    stderr = decode_utf8_output(result.stderr, errors="replace")
    if result.returncode != 0:
        detail = (stderr or stdout).strip()
        raise RuntimeError(f"`codex debug models --bundled` failed: {detail or result.returncode}")
    if not stdout.strip():
        raise RuntimeError("`codex debug models --bundled` produced empty stdout")
    data = json.loads(stdout)
    if isinstance(data, list):
        data = {"models": data}
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        raise RuntimeError("bundled catalog did not contain a models array")
    try:
        catalog.parent.mkdir(parents=True, exist_ok=True)
        catalog.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"cannot write catalog {catalog}: {exc}") from exc
    return data


def load_cache_models(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("models"), list):
        return data["models"]
    raise ValueError(f"{path}: no models array")


def find_source_entry(
    models: list[dict[str, Any]],
    slug: str,
    clone_from: str | None,
) -> tuple[dict[str, Any], str] | None:
    wanted = clone_from or slug
    exact = next((m for m in models if m.get("slug") == wanted), None)
    if exact is not None:
        return exact, str(exact.get("slug") or wanted)
    if clone_from:
        return None
    suffixed = [m for m in models if str(m.get("slug") or "").endswith("/" + slug)]
    if len(suffixed) == 1:
        found = suffixed[0]
        return found, str(found.get("slug"))
    return None



def missing_config_text(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    config: Path,
    codex_home: Path,
    reasoning_effort: str,
) -> tuple[str, bool]:
    hits = find_profiles_with_model(codex_home, args.model)
    hit_names = ", ".join(path.name.removesuffix(".config.toml") for path in hits)
    init_cmd = (
        f"{python_cmd()} scripts/init_profile.py --model {args.model} "
        f"--provider {args.profile or '<id>'} --base-url <url> --yes"
    )
    if not args.profile:
        extra = f" Matching profile(s): --profile {hit_names}." if hits else ""
        parser.error(
            f"config file not found: {config}.{extra} "
            f"Pass --profile <id> to create it from the skill template, or run: {init_cmd}"
        )

    try:
        validate_provider(args.profile)
        env_key = f"{args.profile.replace('-', '_').upper()}_API_KEY"
        rendered = render_template(
            default_template().read_text(encoding="utf-8"),
            provider=args.profile,
            model=args.model,
            base_url=args.base_url or "",
            env_key=env_key,
            wire_api=args.wire_api,
            reasoning_effort=reasoning_effort,
        )
        tomllib.loads(rendered)
    except FileNotFoundError:
        parser.error(f"config file not found: {config}; template missing: {default_template()}")
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        parser.error(
            f"config file not found: {config}; could not create from template: {exc}. "
            f"Create it first: {init_cmd}"
        )
    return rendered, True


def print_proposal(
    slug: str,
    context: int,
    compact: int,
    catalog: Path,
    config: Path,
    cloned_from: str | None,
    bootstrapped: bool,
    *,
    effective_percent: int,
    reasoning_effort: str | None,
    default_reasoning: str | None,
    reasoning_levels: list[str] | None,
    input_modalities: list[str] | None,
    using_defaults: bool,
    created_profile: bool = False,
    base_url: str = "",
) -> None:
    print("Proposed change")
    print(f"  model:                {slug}")
    print(f"  context_window:       {context}")
    print(f"  max_context_window:   {context}")
    print(f"  effective_percent:    {effective_percent}")
    print(f"  compact_limit:        {compact}")
    print(f"  model_catalog_json:   {catalog}")
    print(f"  config file:          {config}")
    if reasoning_effort:
        print(f"  reasoning_effort:     {reasoning_effort}")
    if default_reasoning:
        print(f"  default_reasoning:    {default_reasoning}")
    if reasoning_levels:
        print(f"  reasoning_levels:     {','.join(reasoning_levels)}")
    if input_modalities:
        print(f"  input_modalities:     {','.join(input_modalities)}")
    if using_defaults:
        print("  defaults:             skill.codex-model-config template block")
    if bootstrapped:
        print("  catalog source:       codex debug models --bundled")
    if cloned_from:
        print(f"  cloned from:          {cloned_from}")
    if created_profile:
        print("  profile source:       skill template (file was missing)")
        if not base_url:
            print("  warning:              base_url is empty; fill it before starting Codex")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="catalog slug; must match config model=")
    parser.add_argument(
        "--context-window",
        type=int,
        default=None,
        help="target context window; default: skill template 258400",
    )
    parser.add_argument(
        "--defaults",
        action="store_true",
        help="apply skill template defaults (258400 context, five reasoning levels)",
    )
    limit_group = parser.add_mutually_exclusive_group()
    limit_group.add_argument("--compact-limit", type=int, help="explicit compaction token limit")
    limit_group.add_argument(
        "--compact-percent",
        type=float,
        default=90.0,
        help="compaction limit as %% of context (default: skill template)",
    )
    parser.add_argument("--codex-home", default=os.environ.get("CODEX_HOME") or str(Path.home() / ".codex"))
    parser.add_argument(
        "--profile",
        help="edit <codex-home>/<profile>.config.toml; create it from the skill template if missing",
    )
    parser.add_argument("--config", help="config.toml path (default: <codex-home>/config.toml)")
    parser.add_argument(
        "--base-url",
        help="provider base_url; used when creating a missing --profile from the template",
    )
    parser.add_argument(
        "--wire-api",
        choices=WIRE_APIS,
        default="responses",
        help="provider wire_api when creating a missing --profile; default: responses",
    )
    parser.add_argument("--catalog", help="models.json path (default: <codex-home>/models.json)")
    parser.add_argument(
        "--bootstrap-bundled",
        action="store_true",
        help="create models.json from `codex debug models --bundled` when missing",
    )
    parser.add_argument(
        "--from-cache",
        action="store_true",
        help="if the slug is missing, clone it from models_cache.json (including vendor-prefixed slugs)",
    )
    parser.add_argument("--clone-from", help="clone this catalog/cache slug when --model is missing")
    parser.add_argument(
        "--effective-percent",
        type=int,
        default=None,
        help="catalog effective_context_window_percent; default: skill template 100",
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=REASONING_EFFORTS,
        help="set TOML model_reasoning_effort; default: skill template",
    )
    parser.add_argument(
        "--default-reasoning-level",
        choices=REASONING_EFFORTS,
        help="catalog default_reasoning_level; default: skill template",
    )
    parser.add_argument(
        "--reasoning-levels",
        default=None,
        help="comma-separated catalog levels; default: low,medium,high,xhigh,max",
    )
    parser.add_argument(
        "--input-modalities",
        help="comma-separated catalog input_modalities, e.g. text,image",
    )
    parser.add_argument("--force", action="store_true", help="allow editing a TOML whose model= does not match --model")
    parser.add_argument("--yes", action="store_true", help="apply without prompting")
    parser.add_argument("--dry-run", action="store_true", help="print the proposal and exit")
    args = parser.parse_args()

    if args.profile and args.config:
        parser.error("use either --profile or --config, not both")

    codex_home = Path(args.codex_home).expanduser()
    if args.profile:
        config = (codex_home / f"{args.profile}.config.toml").expanduser().resolve()
    else:
        config = (Path(args.config) if args.config else codex_home / "config.toml").expanduser().resolve()
    catalog = (Path(args.catalog) if args.catalog else codex_home / "models.json").expanduser().resolve()
    cache_path = codex_home / "models_cache.json"

    skill_defaults = load_skill_defaults()
    context_window = args.context_window or skill_defaults["context_window"]
    effective_percent = args.effective_percent or skill_defaults["effective_percent"]
    reasoning_effort = args.reasoning_effort or skill_defaults["reasoning_effort"]
    if context_window <= 0:
        parser.error("--context-window must be positive")
    if args.compact_limit is not None and not 0 < args.compact_limit <= context_window:
        parser.error("--compact-limit must be between 1 and --context-window")
    if not 0 < args.compact_percent <= 100:
        parser.error("--compact-percent must be between 0 and 100")
    if not 1 <= effective_percent <= 100:
        parser.error("--effective-percent must be between 1 and 100")
    try:
        reasoning_levels = (
            parse_reasoning_levels(args.reasoning_levels)
            if args.reasoning_levels
            else list(skill_defaults["reasoning_levels"])
        )
        input_modalities = (
            parse_modalities(args.input_modalities) if args.input_modalities else None
        )
    except ValueError as exc:
        parser.error(str(exc))
    default_reasoning = args.default_reasoning_level or skill_defaults["reasoning_effort"]
    if default_reasoning not in reasoning_levels:
        default_reasoning = reasoning_levels[0]
    if reasoning_effort not in reasoning_levels:
        parser.error("--reasoning-effort must be in --reasoning-levels")
    using_defaults = (
        args.defaults
        or args.context_window is None
        or args.reasoning_levels is None
        or args.effective_percent is None
        or args.reasoning_effort is None
    )
    created_profile = False
    if not config.exists():
        config_text, created_profile = missing_config_text(parser, args, config, codex_home, reasoning_effort)
    else:
        config_text = config.read_text(encoding="utf-8")
    try:
        current_model = top_level_model(config_text)
    except tomllib.TOMLDecodeError as exc:
        parser.error(f"{config} is invalid TOML: {exc}")

    if current_model and current_model != args.model and not args.force:
        profile_hits = find_profiles_with_model(codex_home, args.model)
        hint = ""
        if profile_hits:
            names = ", ".join(path.name.removesuffix(".config.toml") for path in profile_hits)
            hint = f" Matching profile(s): --profile {names}."
        parser.error(
            f"{config} has model={current_model!r}, not {args.model!r}. "
            f"Edit the TOML that actually selects this model, or pass --force.{hint}"
        )

    if not args.profile and current_model != args.model:
        profile_hits = find_profiles_with_model(codex_home, args.model)
        if profile_hits and not args.force:
            names = ", ".join(path.name.removesuffix(".config.toml") for path in profile_hits)
            parser.error(
                f"{args.model} is configured in profile {names}, not {config.name}. "
                "Pass --profile <name> so model_catalog_json is not written into the default config."
            )

    bootstrapped = False
    if not catalog.exists():
        if not args.bootstrap_bundled:
            parser.error(f"catalog file not found: {catalog}; pass --bootstrap-bundled")
        if args.dry_run:
            print(f"Would create {catalog} from `codex debug models --bundled`")
            root, models = {"models": []}, []
            bootstrapped = True
        else:
            try:
                root = dump_bundled_catalog(catalog)
            except (OSError, RuntimeError, json.JSONDecodeError) as exc:
                parser.error(str(exc))
            models = root["models"]
            bootstrapped = True
    else:
        try:
            root, models = load_catalog(catalog)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            parser.error(str(exc))

    index = next((i for i, m in enumerate(models) if m.get("slug") == args.model), None)
    cloned_from = None
    if index is None:
        source = None
        if args.clone_from:
            source = find_source_entry(models, args.model, args.clone_from)
        if source is None and args.from_cache:
            if not cache_path.exists():
                parser.error(f"--from-cache set but {cache_path} does not exist")
            try:
                source = find_source_entry(load_cache_models(cache_path), args.model, args.clone_from)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                parser.error(str(exc))
        if source is None:
            parser.error(
                f"model '{args.model}' is not present in {catalog}; "
                "pass --from-cache and/or --clone-from <slug>, or add the entry first"
            )
        source_entry, cloned_from = source
        models.append(copy.deepcopy(source_entry))
        index = len(models) - 1
        root["models"] = models

    compact = (
        args.compact_limit
        if args.compact_limit is not None
        else compact_limit_for(context_window, args.compact_percent)
    )
    clean_compact = max(1, compact)
    print_proposal(
        args.model,
        context_window,
        clean_compact,
        catalog,
        config,
        cloned_from,
        bootstrapped,
        effective_percent=effective_percent,
        reasoning_effort=reasoning_effort,
        default_reasoning=default_reasoning,
        reasoning_levels=reasoning_levels,
        input_modalities=input_modalities,
        using_defaults=using_defaults,
        created_profile=created_profile,
        base_url=args.base_url or "",
    )

    if args.dry_run:
        return 0
    if not args.yes:
        if not sys.stdin.isatty():
            parser.error("refusing non-interactive change without --yes")
        answer = input("Apply changes? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("No changes applied.")
            return 0

    model = dict(models[index])
    model["slug"] = args.model
    model["context_window"] = context_window
    model["max_context_window"] = context_window
    model["effective_context_window_percent"] = effective_percent
    model["auto_compact_token_limit"] = None
    model["supported_reasoning_levels"] = build_reasoning_levels(reasoning_levels, model)
    model["default_reasoning_level"] = default_reasoning
    if input_modalities:
        model["input_modalities"] = input_modalities
    if "comp_hash" in model:
        model["comp_hash"] = f"{args.model}-{context_window}"
    models[index] = model

    config_text = set_top_level_key(config_text, "model_context_window", context_window)
    config_text = set_top_level_key(config_text, "model_auto_compact_token_limit", clean_compact)
    config_text = set_top_level_key(config_text, "model_catalog_json", str(catalog))
    config_text = set_top_level_key(config_text, "model_reasoning_effort", reasoning_effort)
    try:
        tomllib.loads(config_text)
    except tomllib.TOMLDecodeError as exc:
        parser.error(f"generated config is invalid: {exc}")

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    if config.exists():
        shutil.copy2(config, config.with_name(f"{config.name}.bak.{stamp}"))
    if catalog.exists():
        shutil.copy2(catalog, catalog.with_name(f"{catalog.name}.bak.{stamp}"))
    config.parent.mkdir(parents=True, exist_ok=True)
    catalog.write_text(json.dumps(root, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    config.write_text(config_text, encoding="utf-8")

    print(f"{'Created' if created_profile else 'Updated'} {config}")
    print(f"Updated {catalog}")
    if created_profile and not (args.base_url or "").strip():
        print("Fill base_url in the new profile before starting Codex.")
    print("Next:")
    print_next_debug_models(catalog)
    if args.profile:
        print(f"  start a new session with: codex --profile {args.profile}")
    print("  Reload VS Code and open a new conversation. `codex --profile` does not apply to doctor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
