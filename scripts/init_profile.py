#!/usr/bin/env python3
"""Create a Codex profile TOML from the skill template.

Bulk-replaces provider-id and model-id in references/template.config.toml.
If --provider is omitted, the model series (gpt, grok, deepseek, ...) is used.
If an API key is given, write it to ~/.config/models.env (create or append).
Never write the key into the TOML.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from shell_hints import print_next_load_env
from model_meta import (
    REASONING_EFFORTS,
    WIRE_APIS,
    compact_limit_for,
    install_as_default_config,
    load_skill_defaults,
    parse_kv_pairs,
    set_top_level_key,
)


RESERVED_PROVIDER_IDS = {"openai", "ollama", "lmstudio"}

# Longest-first prefixes matched against the last path segment of the model slug.
SERIES_PREFIXES = (
    "deepseek",
    "chatgpt",
    "claude",
    "gemini",
    "mistral",
    "doubao",
    "llama",
    "grok",
    "qwen",
    "kimi",
    "glm",
    "gpt",
)

SERIES_ALIASES = {
    "chatgpt": "gpt",
    "openai": "gpt",
}

PROVIDER_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
O_SERIES_RE = re.compile(r"^o[1-9](?:[-_.]|$)")
ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ENV_ASSIGN_RE = re.compile(
    r"^(\s*(?:export\s+)?)([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*)(.*)$"
)


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_template() -> Path:
    return skill_root() / "references" / "template.config.toml"


def default_codex_home() -> Path:
    override = os.environ.get("CODEX_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".codex"


def default_env_file() -> Path:
    return Path.home() / ".config" / "models.env"


def model_leaf(model: str) -> str:
    return model.strip().split("/")[-1].lower()


def derive_series(model: str) -> str:
    slug = model_leaf(model)
    if not slug:
        raise ValueError("model slug is empty")
    for prefix in sorted(SERIES_PREFIXES, key=len, reverse=True):
        if slug == prefix or slug.startswith(prefix + "-") or slug.startswith(prefix + "."):
            return SERIES_ALIASES.get(prefix, prefix)
    if O_SERIES_RE.match(slug):
        return "gpt"
    token = re.split(r"[-_.]", slug, maxsplit=1)[0]
    if not token or not re.fullmatch(r"[a-z][a-z0-9]*", token):
        raise ValueError(
            f"cannot derive provider id from model {model!r}; pass --provider"
        )
    return SERIES_ALIASES.get(token, token)


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def format_env_value(value: str) -> str:
    if re.search(r"[\s#'\"]", value) or "\\" in value:
        return json.dumps(value, ensure_ascii=False)
    return value


def upsert_models_env(path: Path, key: str, value: str) -> str:
    """Create models.env or append KEY=value. Same key updates that line."""
    if not ENV_KEY_RE.fullmatch(key):
        raise ValueError(f"invalid env var name: {key!r}")
    if not value:
        raise ValueError("API key is empty")
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    assignment = f"{key}={format_env_value(value)}"
    if not path.exists():
        path.write_text(assignment + "\n", encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return "created"
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    for index, existing in enumerate(lines):
        match = ENV_ASSIGN_RE.match(existing)
        if match and match.group(2) == key:
            lines[index] = (
                f"{match.group(1)}{key}{match.group(3)}{format_env_value(value)}"
            )
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return "updated"
    body = text if not text or text.endswith("\n") else text + "\n"
    path.write_text(body + assignment + "\n", encoding="utf-8")
    return "appended"


def replace_quoted_assignment(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"^(\s*{re.escape(key)}\s*=\s*)(\"[^\"]*\"|'[^']*')", re.M)
    replaced, count = pattern.subn(rf"\1{toml_string(value)}", text, count=1)
    if count != 1:
        raise ValueError(f"expected one {key} assignment in template, found {count}")
    return replaced


def render_template(
    template: str,
    *,
    provider: str,
    model: str,
    base_url: str,
    env_key: str,
    wire_api: str,
    reasoning_effort: str,
) -> str:
    if "provider-id" not in template:
        raise ValueError("template does not contain provider-id")
    if "model-id" not in template:
        raise ValueError("template does not contain model-id")
    text = template.replace("provider-id", provider).replace("model-id", model)
    text = replace_quoted_assignment(text, "base_url", base_url)
    text = replace_quoted_assignment(text, "env_key", env_key)
    text = replace_quoted_assignment(text, "wire_api", wire_api)
    text = replace_quoted_assignment(text, "model_reasoning_effort", reasoning_effort)
    return text


def set_provider_key(text: str, provider: str, key: str, value: str) -> str:
    """Set/replace `key = value` inside `[model_providers.<provider>]` section."""
    lines = text.splitlines(keepends=True)
    header = f"[model_providers.{provider}]"
    start = next(
        (i for i, line in enumerate(lines) if line.strip() == header), None
    )
    if start is None:
        raise ValueError(f"missing section {header}")
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].lstrip().startswith("["):
            end = i
            break
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
    for i in range(start + 1, end):
        stripped = lines[i].lstrip()
        if stripped.startswith("#"):
            continue
        if pattern.match(lines[i]):
            lines[i] = f"{key} = {value}\n"
            return "".join(lines)
    lines.insert(end, f"{key} = {value}\n")
    return "".join(lines)


def toml_table(mapping: dict[str, str]) -> str:
    return "{ " + ", ".join(f"{json.dumps(k)} = {json.dumps(v)}" for k, v in mapping.items()) + " }"


def apply_provider_tuning(
    text: str,
    provider: str,
    *,
    query_params: dict[str, str],
    http_headers: dict[str, str],
    env_http_headers: dict[str, str],
    request_max_retries: int | None,
    stream_max_retries: int | None,
    stream_idle_timeout_ms: int | None,
    supports_websockets: bool | None,
) -> str:
    if query_params:
        text = set_provider_key(text, provider, "query_params", toml_table(query_params))
    if http_headers:
        text = set_provider_key(text, provider, "http_headers", toml_table(http_headers))
    if env_http_headers:
        text = set_provider_key(text, provider, "env_http_headers", toml_table(env_http_headers))
    if request_max_retries is not None:
        text = set_provider_key(text, provider, "request_max_retries", str(request_max_retries))
    if stream_max_retries is not None:
        text = set_provider_key(text, provider, "stream_max_retries", str(stream_max_retries))
    if stream_idle_timeout_ms is not None:
        text = set_provider_key(text, provider, "stream_idle_timeout_ms", str(stream_idle_timeout_ms))
    if supports_websockets is not None:
        text = set_provider_key(
            text, provider, "supports_websockets", "true" if supports_websockets else "false"
        )
    return text


def validate_provider(provider: str) -> None:
    if not PROVIDER_RE.fullmatch(provider):
        raise ValueError(
            f"provider id {provider!r} must be lowercase letters, digits, and hyphens"
        )
    if provider in RESERVED_PROVIDER_IDS:
        raise ValueError(
            f"provider id {provider!r} is reserved; pass a different --provider "
            f"(for OpenAI-compatible GPT models prefer gpt)"
        )


def parse_args() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="TOML model slug, e.g. grok-4.6")
    parser.add_argument(
        "--provider",
        help="provider id and profile stem; default: model series (gpt, grok, deepseek, ...)",
    )
    parser.add_argument("--base-url", required=True, help="provider base_url")
    parser.add_argument(
        "--wire-api",
        choices=WIRE_APIS,
        default="responses",
        help="provider wire_api; only responses is supported since 2026-02",
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=REASONING_EFFORTS,
        default=None,
        help="TOML model_reasoning_effort; default: skill template",
    )
    parser.add_argument(
        "--context-window",
        type=int,
        default=None,
        help="TOML model_context_window; default: skill template 258400",
    )
    parser.add_argument(
        "--defaults",
        action="store_true",
        help="apply skill template defaults (258400 context, five reasoning levels)",
    )
    parser.add_argument(
        "--env-key",
        help="env var name for the API key; default: <PROVIDER>_API_KEY",
    )
    parser.add_argument(
        "--api-key",
        help="API key to store in --env-file; never written to the TOML",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=default_env_file(),
        help="dotenv path; default: ~/.config/models.env",
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=default_template(),
        help="template TOML path",
    )
    parser.add_argument(
        "--codex-home",
        type=Path,
        default=default_codex_home(),
        help="Codex home directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="explicit output path; default: <codex-home>/<provider>.config.toml",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="overwrite an existing profile")
    parser.add_argument(
        "--query-params",
        default=None,
        help="provider query_params as k=v,k=v, e.g. api-version=2025-04-01-preview",
    )
    parser.add_argument(
        "--http-headers",
        default=None,
        help="static provider http_headers as k=v,k=v",
    )
    parser.add_argument(
        "--env-http-headers",
        default=None,
        help="provider env_http_headers as HeaderName=ENV_VAR,HeaderName=ENV_VAR",
    )
    parser.add_argument("--request-max-retries", type=int, default=None)
    parser.add_argument("--stream-max-retries", type=int, default=None)
    parser.add_argument("--stream-idle-timeout-ms", type=int, default=None)
    parser.add_argument("--supports-websockets", action="store_true", default=None)
    parser.add_argument("--no-supports-websockets", action="store_true")
    parser.add_argument(
        "--as-default",
        action="store_true",
        help="backup ~/.codex/config.toml and copy this profile over it",
    )
    parser.add_argument("--yes", action="store_true")
    return parser


def main() -> int:
    parser = parse_args()
    args = parser.parse_args()
    try:
        provider = args.provider or derive_series(args.model)
        validate_provider(provider)
    except ValueError as exc:
        parser.error(str(exc))

    env_key = args.env_key or f"{provider.replace('-', '_').upper()}_API_KEY"
    if not ENV_KEY_RE.fullmatch(env_key):
        parser.error(f"invalid env var name: {env_key!r}")
    skill_defaults = load_skill_defaults(args.template)
    reasoning_effort = args.reasoning_effort or skill_defaults["reasoning_effort"]
    context_window = args.context_window or skill_defaults["context_window"]
    if context_window <= 0:
        parser.error("--context-window must be positive")
    compact_limit = compact_limit_for(context_window, skill_defaults["compact_percent"])
    output = args.output or (args.codex_home / f"{provider}.config.toml")
    default_config = args.codex_home / "config.toml"
    if output.resolve() == default_config.resolve() and not args.force:
        parser.error(f"refusing to write {output}; pass --force to overwrite the default config")

    try:
        template = args.template.read_text(encoding="utf-8")
        try:
            query_params = parse_kv_pairs(args.query_params, flag="--query-params")
            http_headers = parse_kv_pairs(args.http_headers, flag="--http-headers")
            env_http_headers = parse_kv_pairs(args.env_http_headers, flag="--env-http-headers")
        except ValueError as exc:
            parser.error(str(exc))
        if args.request_max_retries is not None and args.request_max_retries < 0:
            parser.error("--request-max-retries must be >= 0")
        if args.stream_max_retries is not None and args.stream_max_retries < 0:
            parser.error("--stream-max-retries must be >= 0")
        if args.stream_idle_timeout_ms is not None and args.stream_idle_timeout_ms <= 0:
            parser.error("--stream-idle-timeout-ms must be positive")
        if args.supports_websockets and args.no_supports_websockets:
            parser.error("use either --supports-websockets or --no-supports-websockets")
        supports_websockets: bool | None = None
        if args.supports_websockets:
            supports_websockets = True
        elif args.no_supports_websockets:
            supports_websockets = False
        rendered = render_template(
            template,
            provider=provider,
            model=args.model,
            base_url=args.base_url,
            env_key=env_key,
            wire_api=args.wire_api,
            reasoning_effort=reasoning_effort,
        )
        rendered = set_top_level_key(rendered, "model_context_window", context_window)
        rendered = set_top_level_key(rendered, "model_auto_compact_token_limit", compact_limit)
        rendered = apply_provider_tuning(
            rendered,
            provider,
            query_params=query_params,
            http_headers=http_headers,
            env_http_headers=env_http_headers,
            request_max_retries=args.request_max_retries,
            stream_max_retries=args.stream_max_retries,
            stream_idle_timeout_ms=args.stream_idle_timeout_ms,
            supports_websockets=supports_websockets,
        )
        tomllib.loads(rendered)
    except FileNotFoundError:
        parser.error(f"template not found: {args.template}")
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        parser.error(str(exc))

    derived = args.provider is None
    env_file = args.env_file.expanduser()
    print("Proposed profile")
    print(f"  model:       {args.model}")
    print(f"  provider:    {provider}{'  (from model series)' if derived else ''}")
    print(f"  base_url:    {args.base_url}")
    print(f"  wire_api:    {args.wire_api}")
    print(f"  reasoning:   {reasoning_effort}")
    print(f"  context:     {context_window}")
    print(f"  compact:     {compact_limit}")
    print(f"  env_key:     {env_key}")
    if args.defaults or args.context_window is None or args.reasoning_effort is None:
        print("  defaults:    skill.codex-model-config template block")
    print(f"  output:      {output}")
    if args.as_default:
        print(f"  as_default:  backup {default_config} then copy this profile over it")
    if args.api_key:
        action = "append" if env_file.exists() else "create"
        print(f"  api_key:     (hidden) {action} {env_file}")
    else:
        print(f"  api_key:     not provided; will not touch {env_file}")
    if derived:
        print("  note:        pass --provider <id> to override the series name")

    if output.exists() and not args.force:
        if args.dry_run:
            print(f"  warning:     {output} exists; write would require --force")
        else:
            parser.error(f"{output} already exists; pass --force to overwrite")
    if args.dry_run:
        return 0
    if not args.yes:
        if not sys.stdin.isatty():
            parser.error("refusing non-interactive create without --yes")
        answer = input("Write profile? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("No changes applied.")
            return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        import datetime as dt
        import shutil

        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = output.with_name(f"{output.name}.bak.{stamp}")
        shutil.copy2(output, backup)
        print(f"Backed up {output} -> {backup}")
    output.write_text(rendered, encoding="utf-8")
    print(f"Wrote {output}")
    if args.as_default:
        backup = install_as_default_config(output, default_config)
        if backup:
            print(f"Backed up {default_config} -> {backup}")
        print(f"Installed {output} as {default_config}")
    if args.api_key:
        try:
            result = upsert_models_env(env_file, env_key, args.api_key)
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        print(f"{result.capitalize()} {env_key} in {env_file}")
        print("Next:")
        print_next_load_env(env_file)
        print(f"  codex --profile {provider}")
        if args.as_default:
            print("  or start without --profile to use the new default config.toml")
    else:
        print("Next:")
        print(f"  add {env_key}=... to {env_file} (create the file if needed)")
        print_next_load_env(env_file)
        print(f"  codex --profile {provider}")
        if args.as_default:
            print("  or start without --profile to use the new default config.toml")
    print("  set model_catalog_json / context window with adjust_context_window.py if needed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
