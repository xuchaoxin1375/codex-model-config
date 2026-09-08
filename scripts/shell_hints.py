"""OS-aware next-step hints for the Codex model-config scripts."""

from __future__ import annotations

import os
from pathlib import Path


def on_windows() -> bool:
    return os.name == "nt"


def python_cmd() -> str:
    return "python" if on_windows() else "python3"


def catalog_posix(catalog: Path) -> str:
    catalog = Path(catalog).expanduser()
    try:
        catalog = catalog.resolve()
    except OSError:
        pass
    return catalog.as_posix()


def print_next_load_env(env_file: Path) -> None:
    env_file = Path(env_file).expanduser()
    if on_windows():
        print(f"  $envFile = '{env_file}'")
        print("  Get-Content -LiteralPath $envFile | ForEach-Object {")
        print("    if ($_ -match '^\\s*(?:export\\s+)?([A-Za-z_][A-Za-z0-9_]*)\\s*=\\s*(.*)$') {")
        print("      Set-Item -Path \"Env:$($Matches[1])\" -Value $Matches[2].Trim().Trim('\"').Trim(\"'\")")
        print("    }")
        print("  }")
    else:
        print(f"  set -a && . {env_file} && set +a")


def print_next_debug_models(catalog: Path) -> None:
    catalog_path = catalog_posix(catalog)
    if on_windows():
        print(f"  codex -c 'model_catalog_json=\"{catalog_path}\"' debug models")
    else:
        print(f"  codex -c model_catalog_json='\"{catalog_path}\"' debug models")