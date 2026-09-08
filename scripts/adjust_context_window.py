#!/usr/bin/env python3
"""Adjust the context window of one Codex model entry.

Edits:
  - top-level keys in a config/profile TOML
  - the matching entry in models.json

If the catalog or model entry is missing, pass --bootstrap-bundled and/or
--from-cache/--clone-from instead of hand-editing JSON. Backups are written
beside the edited files.
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


def dump_bundled_catalog(catalog: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["codex", "debug", "models", "--bundled"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"`codex debug models --bundled` failed: {detail or result.returncode}")
    data = json.loads(result.stdout)
    if isinstance(data, list):
        data = {"models": data}
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        raise RuntimeError("bundled catalog did not contain a models array")
    catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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


def print_proposal(
    slug: str,
    context: int,
    compact: int,
    catalog: Path,
    config: Path,
    cloned_from: str | None,
    bootstrapped: bool,
) -> None:
    print("Proposed change")
    print(f"  model:                {slug}")
    print(f"  context_window:       {context}")
    print(f"  max_context_window:   {context}")
    print(f"  effective_percent:    100")
    print(f"  compact_limit:        {compact}")
    print(f"  model_catalog_json:   {catalog}")
    print(f"  config file:          {config}")
    if bootstrapped:
        print("  catalog source:       codex debug models --bundled")
    if cloned_from:
        print(f"  cloned from:          {cloned_from}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="catalog slug; must match config model=")
    parser.add_argument("--context-window", required=True, type=int, help="target context window in tokens")
    limit_group = parser.add_mutually_exclusive_group()
    limit_group.add_argument("--compact-limit", type=int, help="explicit compaction token limit")
    limit_group.add_argument(
        "--compact-percent",
        type=float,
        default=90.0,
        help="compaction limit as % of context (default 90)",
    )
    parser.add_argument("--codex-home", default=os.environ.get("CODEX_HOME") or str(Path.home() / ".codex"))
    parser.add_argument("--profile", help="edit <codex-home>/<profile>.config.toml instead of config.toml")
    parser.add_argument("--config", help="config.toml path (default: <codex-home>/config.toml)")
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

    if args.context_window <= 0:
        parser.error("--context-window must be positive")
    if args.compact_limit is not None and not 0 < args.compact_limit <= args.context_window:
        parser.error("--compact-limit must be between 1 and --context-window")
    if not 0 < args.compact_percent <= 100:
        parser.error("--compact-percent must be between 0 and 100")
    if not config.exists():
        parser.error(f"config file not found: {config}")

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

    compact = args.compact_limit if args.compact_limit is not None else int(
        args.context_window * args.compact_percent / 100
    )
    clean_compact = max(1, compact)
    print_proposal(args.model, args.context_window, clean_compact, catalog, config, cloned_from, bootstrapped)

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
    model["context_window"] = args.context_window
    model["max_context_window"] = args.context_window
    model["effective_context_window_percent"] = 100
    model["auto_compact_token_limit"] = None
    if "comp_hash" in model:
        model["comp_hash"] = f"{args.model}-{args.context_window}"
    models[index] = model

    config_text = set_top_level_key(config_text, "model_context_window", args.context_window)
    config_text = set_top_level_key(config_text, "model_auto_compact_token_limit", clean_compact)
    config_text = set_top_level_key(config_text, "model_catalog_json", str(catalog))
    try:
        tomllib.loads(config_text)
    except tomllib.TOMLDecodeError as exc:
        parser.error(f"generated config is invalid: {exc}")

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(config, config.with_name(f"{config.name}.bak.{stamp}"))
    if catalog.exists():
        shutil.copy2(catalog, catalog.with_name(f"{catalog.name}.bak.{stamp}"))
    catalog.write_text(json.dumps(root, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    config.write_text(config_text, encoding="utf-8")

    print(f"Updated {config}")
    print(f"Updated {catalog}")
    print("Next:")
    print(f"  codex -c model_catalog_json='\"{catalog}\"' debug models")
    if args.profile:
        print(f"  start a new session with: codex --profile {args.profile}")
    print("  Reload VS Code and open a new conversation. `codex --profile` does not apply to doctor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
