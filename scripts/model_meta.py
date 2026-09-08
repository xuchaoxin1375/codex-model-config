"""Shared model metadata helpers for Codex profile/catalog scripts."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

WIRE_APIS = ("responses", "chat")
REASONING_EFFORTS = ("low", "medium", "high", "xhigh", "max")

SKILL_DEFAULTS_BEGIN = "# BEGIN skill.codex-model-config"
SKILL_DEFAULTS_END = "# END skill.codex-model-config"

# Used only if the template block is missing.
FALLBACK_SKILL_DEFAULTS: dict[str, Any] = {
    "context_window": 258400,
    "compact_percent": 90,
    "effective_percent": 100,
    "reasoning_effort": "low",
    "reasoning_levels": list(REASONING_EFFORTS),
    "input_modalities": ["text", "image"],
}

DEFAULT_REASONING_DESCRIPTIONS = {
    "low": "Fast responses with lighter reasoning",
    "medium": "Balanced speed and reasoning depth",
    "high": "Deep reasoning for complex problems",
    "xhigh": "Extra-deep reasoning for the hardest problems",
    "max": "Maximum reasoning effort",
}


def skill_template_path() -> Path:
    return Path(__file__).resolve().parent.parent / "references" / "template.config.toml"


def compact_limit_for(context_window: int, compact_percent: float) -> int:
    return max(1, int(context_window * compact_percent / 100))


def load_skill_defaults(template: Path | None = None) -> dict[str, Any]:
    path = Path(template) if template is not None else skill_template_path()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return dict(FALLBACK_SKILL_DEFAULTS)
    start = text.find(SKILL_DEFAULTS_BEGIN)
    stop = text.find(SKILL_DEFAULTS_END)
    if start < 0 or stop < 0 or stop <= start:
        return dict(FALLBACK_SKILL_DEFAULTS)
    lines: list[str] = []
    for raw in text[start:stop].splitlines()[1:]:
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            stripped = stripped[1:]
            if stripped.startswith(" "):
                stripped = stripped[1:]
        if stripped.startswith("BEGIN ") or stripped.startswith("END "):
            continue
        if stripped.startswith("[") or stripped.startswith("本 ") or stripped.startswith("主流") or stripped.startswith("部分"):
            continue
        if "=" not in stripped:
            continue
        lines.append(stripped)
    try:
        parsed = tomllib.loads("\n".join(lines) + "\n")
    except tomllib.TOMLDecodeError:
        return dict(FALLBACK_SKILL_DEFAULTS)
    data = dict(FALLBACK_SKILL_DEFAULTS)
    if isinstance(parsed.get("context_window"), int):
        data["context_window"] = parsed["context_window"]
    if isinstance(parsed.get("compact_percent"), (int, float)):
        data["compact_percent"] = parsed["compact_percent"]
    if isinstance(parsed.get("effective_percent"), int):
        data["effective_percent"] = parsed["effective_percent"]
    if parsed.get("reasoning_effort") in REASONING_EFFORTS:
        data["reasoning_effort"] = parsed["reasoning_effort"]
    levels = parsed.get("reasoning_levels")
    if isinstance(levels, list) and all(item in REASONING_EFFORTS for item in levels):
        data["reasoning_levels"] = [str(item) for item in levels]
    modalities = parsed.get("input_modalities")
    if isinstance(modalities, list) and all(isinstance(item, str) for item in modalities):
        data["input_modalities"] = [str(item) for item in modalities]
    return data


def parse_csv_tokens(raw: str, *, allowed: tuple[str, ...], flag: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for part in raw.replace(",", " ").split():
        token = part.strip().lower()
        if not token:
            continue
        if token not in allowed:
            raise ValueError(f"{flag}: unknown value {token!r}; allowed: {', '.join(allowed)}")
        if token not in seen:
            values.append(token)
            seen.add(token)
    if not values:
        raise ValueError(f"{flag}: expected at least one value")
    return values


def parse_reasoning_levels(raw: str) -> list[str]:
    return parse_csv_tokens(raw, allowed=REASONING_EFFORTS, flag="--reasoning-levels")


def parse_modalities(raw: str) -> list[str]:
    return parse_csv_tokens(
        raw,
        allowed=("text", "image", "audio"),
        flag="--input-modalities",
    )


def build_reasoning_levels(
    efforts: list[str],
    source: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    existing: dict[str, dict[str, Any]] = {}
    if source:
        for item in source.get("supported_reasoning_levels") or []:
            if isinstance(item, dict) and item.get("effort"):
                existing[str(item["effort"])] = dict(item)
    built: list[dict[str, Any]] = []
    for effort in efforts:
        if effort in existing:
            entry = dict(existing[effort])
            entry["effort"] = effort
            built.append(entry)
        else:
            built.append(
                {
                    "effort": effort,
                    "description": DEFAULT_REASONING_DESCRIPTIONS[effort],
                }
            )
    return built


def toml_value(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def set_top_level_key(text: str, key: str, value: Any) -> str:
    import re

    lines = text.splitlines(keepends=True)
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
    section_index = len(lines)
    for index, line in enumerate(lines):
        if line.lstrip().startswith("["):
            section_index = index
            break
    for index in range(section_index):
        stripped = lines[index].lstrip()
        if stripped.startswith("#") and key in stripped:
            continue
        if pattern.match(lines[index]):
            lines[index] = f"{key} = {toml_value(value)}\n"
            return "".join(lines)
    lines.insert(section_index, f"{key} = {toml_value(value)}\n")
    return "".join(lines)