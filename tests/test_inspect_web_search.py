"""inspect_web_search.py: layer view, search findings, JSON and profile behavior."""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import inspect_web_search as mod  # noqa: E402
from tests.test_cli_windows import write_fake_codex  # noqa: E402


def write_fixture(home: Path, *, model="alpha", mode="live", catalog=True,
                  catalog_name="test-models.json", lite=False, ws="text",
                  entries=None):
    cat = home / catalog_name
    models = entries if entries is not None else [
        {"slug": "alpha", "use_responses_lite": lite, "web_search_tool_type": ws},
        {"slug": "beta", "use_responses_lite": True, "web_search_tool_type": "text"},
    ]
    cat.write_text(json.dumps({"models": models}), encoding="utf-8")
    catalog_line = f'model_catalog_json = {json.dumps(cat.as_posix())}\n' if catalog else ""
    (home / "config.toml").write_text(
        f'model = "{model}"\nmodel_provider = "p"\n'
        f'{catalog_line}web_search = "{mode}"\n'
        '[model_providers.p]\nbase_url = "https://example.invalid/v1"\n',
        encoding="utf-8",
    )
    return cat


class InspectTestCase(unittest.TestCase):
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
            except SystemExit as exc:  # argparse usage errors
                code = exc.code if isinstance(exc.code, int) else 2
        return code, out.getvalue(), err.getvalue()


class LayerViewTests(InspectTestCase):
    def test_live_with_lite_false_is_clean(self):
        write_fixture(self.home)
        code, out, _ = self.run_main()
        self.assertEqual(code, 0, out)
        self.assertIn("I_LITE_OFF", out)
        self.assertIn("web_search    live", out)
        self.assertIn("* alpha", out)
        self.assertIn("lite=false  ws=text", out)

    def test_lite_true_blocks(self):
        write_fixture(self.home, lite=True)
        code, out, _ = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("E_RESPONSES_LITE", out)

    def test_cached_is_informational(self):
        write_fixture(self.home, mode="cached")
        code, out, _ = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("I_MODE_CACHED", out)

    def test_disabled_skips_catalog_blockers(self):
        write_fixture(self.home, mode="disabled", catalog=False)
        code, out, _ = self.run_main()
        self.assertEqual(code, 0, out)
        self.assertIn("I_MODE_DISABLED", out)
        self.assertNotIn("E_CATALOG_PATH", out)
        self.assertIn("有意关闭", out)

    def test_missing_catalog_is_blocking(self):
        write_fixture(self.home, catalog=False)
        code, out, _ = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("E_CATALOG_PATH", out)

    def test_relative_catalog_path_is_blocking(self):
        write_fixture(self.home)
        (self.home / "config.toml").write_text(
            'model = "alpha"\nmodel_provider = "p"\n'
            'model_catalog_json = "relative/test-models.json"\n'
            'web_search = "live"\n[model_providers.p]\nbase_url = "https://example.invalid/v1"\n',
            encoding="utf-8",
        )
        code, out, _ = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("absolute path", out)

    def test_missing_slug_is_blocking(self):
        write_fixture(self.home, model="ghost")
        code, out, _ = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("E_CATALOG_SLUG", out)

    def test_missing_ws_type_warns(self):
        write_fixture(self.home, entries=[
            {"slug": "alpha", "use_responses_lite": False},
        ])
        code, out, _ = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("W_WS_TYPE_MISSING", out)

    def test_mixed_menu_warns(self):
        write_fixture(self.home)
        code, out, _ = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("W_MENU_MIXED", out)

    def test_profile_layer_overrides_base(self):
        write_fixture(self.home)
        (self.home / "beta.config.toml").write_text(
            'model = "beta"\n', encoding="utf-8"
        )
        code, out, _ = self.run_main("-p", "beta")
        self.assertEqual(code, 1)
        self.assertIn("E_RESPONSES_LITE", out)
        self.assertIn("model         beta", out)

    def test_unknown_profile_returns_usage_error(self):
        write_fixture(self.home)
        code, _, err = self.run_main("-p", "nope")
        self.assertEqual(code, 2)
        self.assertIn("profile file not found", err)

    def test_all_profiles_lists_overrides(self):
        write_fixture(self.home)
        (self.home / "mimo.config.toml").write_text(
            'model = "mimo-v2"\nweb_search = "disabled"\n', encoding="utf-8"
        )
        code, out, _ = self.run_main("--all-profiles")
        self.assertEqual(code, 0)
        self.assertIn("profiles", out)
        self.assertIn("mimo", out)
        self.assertIn("web_search=disabled", out)

    def test_json_view(self):
        write_fixture(self.home)
        code, out, _ = self.run_main("--json")
        self.assertEqual(code, 0)
        view = json.loads(out)
        self.assertEqual(view["effective"]["model"], "alpha")
        self.assertEqual(view["effective"]["web_search"], "live")
        self.assertGreaterEqual(len(view["catalog_rows"]), 2)
        self.assertEqual(view["catalog_rows"][0]["slug"], "alpha")


class MergeTests(unittest.TestCase):
    def test_nested_tables_merge_instead_of_replace(self):
        base = {"model": "a", "model_providers": {"p": {"base_url": "u", "env_key": "K"}}}
        layer = {"model": "b", "model_providers": {"p": {"base_url": "u2"}}}
        merged = mod.merge_layers(base, layer)
        self.assertEqual(merged["model"], "b")
        self.assertEqual(merged["model_providers"]["p"]["base_url"], "u2")
        self.assertEqual(merged["model_providers"]["p"]["env_key"], "K")

    def test_layer_replaces_scalar(self):
        self.assertEqual(mod.merge_layers({"web_search": "live"}, {"web_search": "disabled"})["web_search"], "disabled")


class BundledDiffTests(InspectTestCase):
    def test_bundled_diff_uses_codex(self):
        write_fixture(self.home)
        bindir = self.home / "bin"
        write_fake_codex(bindir, [
            {"slug": "alpha", "use_responses_lite": True, "web_search_tool_type": "text_and_image"},
        ])
        env = dict(os.environ, PATH=str(bindir) + os.pathsep + os.environ.get("PATH", ""))
        with mock.patch.dict(os.environ, env, clear=False):
            code, out, _ = self.run_main("--bundled")
        self.assertEqual(code, 0, out)
        self.assertIn("use_responses_lite: custom=False bundled=True", out)
        self.assertIn("web_search_tool_type: custom='text' bundled='text_and_image'", out)

    def test_bundled_diff_marks_unavailable_without_codex(self):
        write_fixture(self.home)
        with mock.patch.dict(os.environ, {"PATH": str(self.home / "empty")}):
            diff = mod.bundled_diff("alpha", {"alpha": {"use_responses_lite": False}})
        self.assertFalse(diff["available"])
        self.assertIn("codex", diff["reason"])


if __name__ == "__main__":
    unittest.main()
