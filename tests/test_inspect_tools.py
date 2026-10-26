"""inspect_tools.py: tool-surface inference, nesting, MCP and JSON output."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import inspect_tools as mod  # noqa: E402


DEFAULT_ENTRY = {
    "slug": "alpha",
    "use_responses_lite": False,
    "web_search_tool_type": "text",
    "supports_search_tool": True,
    "apply_patch_tool_type": "freeform",
    "shell_type": "unified_exec",
    "tool_mode": "direct",
    "include_skills_usage_instructions": True,
    "include_plugin_usage_instructions": True,
    "include_apps_usage_instructions": True,
    "experimental_supported_tools": ["clock"],
}


def write_fixture(home: Path, *, mode="live", entry=None, catalog=True,
                  extra_config="", model="alpha"):
    cat = home / "test-models.json"
    entries = [entry if entry is not None else DEFAULT_ENTRY,
               {"slug": "beta", "use_responses_lite": True, "web_search_tool_type": "text"}]
    cat.write_text(json.dumps({"models": entries}), encoding="utf-8")
    catalog_line = f'model_catalog_json = {json.dumps(cat.as_posix())}\n' if catalog else ""
    (home / "config.toml").write_text(
        f'model = "{model}"\nmodel_provider = "p"\n'
        f'{catalog_line}web_search = "{mode}"\n'
        '[model_providers.p]\nbase_url = "https://example.invalid/v1"\n'
        f'{extra_config}',
        encoding="utf-8",
    )
    return cat


class ToolSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = mod.main(["--codex-home", str(self.home), *argv])
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 2
        return code, out.getvalue(), err.getvalue()

    def states(self, *argv):
        code, out, _ = self.run_main(*argv)
        self.assertEqual(code, 0, out)
        view = json.loads(self.run_main("--json", *argv)[1])
        return {row["tool"]: row["state"] for row in view["tools"]}

    def test_live_config_exposes_search_and_builtins(self):
        write_fixture(self.home)
        states = self.states()
        self.assertEqual(states["web_search"], "send")
        self.assertEqual(states["tool_search"], "send")
        self.assertEqual(states["apply_patch"], "send")
        self.assertEqual(states["shell"], "send")
        self.assertEqual(states["clock"], "send")

    def test_disabled_mode_turns_web_search_off(self):
        write_fixture(self.home, mode="disabled")
        self.assertEqual(self.states()["web_search"], "off")

    def test_lite_true_blocks_web_search(self):
        entry = dict(DEFAULT_ENTRY, use_responses_lite=True)
        write_fixture(self.home, entry=entry)
        self.assertEqual(self.states()["web_search"], "blocked")

    def test_missing_lite_is_unknown(self):
        entry = {k: v for k, v in DEFAULT_ENTRY.items() if k != "use_responses_lite"}
        write_fixture(self.home, entry=entry)
        self.assertEqual(self.states()["web_search"], "unknown")

    def test_search_tool_flag_controls_tool_search_only(self):
        entry = dict(DEFAULT_ENTRY, supports_search_tool=False)
        write_fixture(self.home, entry=entry)
        states = self.states()
        self.assertEqual(states["tool_search"], "off")
        self.assertEqual(states["web_search"], "send")

    def test_null_patch_and_disabled_shell_turn_off(self):
        entry = dict(DEFAULT_ENTRY, apply_patch_tool_type=None, shell_type="disabled")
        write_fixture(self.home, entry=entry)
        states = self.states()
        self.assertEqual(states["apply_patch"], "off")
        self.assertEqual(states["shell"], "off")

    def test_code_mode_nests_shell_and_patch(self):
        entry = dict(DEFAULT_ENTRY, tool_mode="code_mode_only")
        write_fixture(self.home, entry=entry)
        states = self.states()
        self.assertEqual(states["apply_patch"], "nested")
        self.assertEqual(states["shell"], "nested")
        self.assertEqual(states["web_search"], "send")

    def test_missing_catalog_marks_unknown(self):
        write_fixture(self.home, catalog=False)
        states = self.states()
        self.assertEqual(states["web_search"], "unknown")
        self.assertEqual(states["apply_patch"], "unknown")

    def test_profile_layer_changes_model(self):
        write_fixture(self.home)
        (self.home / "beta.config.toml").write_text('model = "beta"\n', encoding="utf-8")
        self.assertEqual(self.states("-p", "beta")["web_search"], "blocked")

    def test_mcp_servers_listed_from_config(self):
        write_fixture(self.home, extra_config='\n[mcp_servers.demo]\ncommand = "demo"\n')
        code, out, _ = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("mcp servers", out)
        self.assertIn("demo", out)

    def test_unknown_profile_returns_usage_error(self):
        write_fixture(self.home)
        code, _, err = self.run_main("-p", "nope")
        self.assertEqual(code, 2)
        self.assertIn("profile file not found", err)

    def test_json_view_shape(self):
        write_fixture(self.home)
        code, out, _ = self.run_main("--json")
        self.assertEqual(code, 0)
        view = json.loads(out)
        self.assertEqual(view["model"], "alpha")
        self.assertEqual(view["web_search_mode"], "live")
        self.assertTrue(any(t["tool"] == "web_search" for t in view["tools"]))
        self.assertIn("instruction surfaces", self.run_main()[1])

    def test_instruction_flags_surface(self):
        entry = dict(DEFAULT_ENTRY, include_skills_usage_instructions=False)
        write_fixture(self.home, entry=entry)
        code, out, _ = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("skills=False", out)
        self.assertIn("plugin=True", out)


if __name__ == "__main__":
    unittest.main()
