"""Window updates must respect budgets, preview mode, and unrelated settings."""

import json
import importlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.test_cli_windows import ROOT, write_fake_codex

tomllib = importlib.import_module("tomllib" if sys.version_info >= (3, 11) else "tomli")


class ContextWindowCliTests(unittest.TestCase):
    def fixture(self, directory):
        home = Path(directory)
        catalog = home / "test-models.json"
        config = home / "test.config.toml"
        config.write_text(
            'model = "test-model"\nmodel_reasoning_effort = "high"\n'
            f'model_catalog_json = {json.dumps(catalog.as_posix())}\n'
            'web_search = "live"\n[projects."example"]\ntrust_level = "trusted"\n',
            encoding="utf-8",
        )
        catalog.write_text(json.dumps({"models": [
            {"slug": "test-model", "context_window": 200000,
             "shell_type": "unified_exec", "tool_mode": "code_mode_only",
             "apply_patch_tool_type": "freeform",
             "supported_reasoning_levels": [{"effort": "high", "description": "existing"}],
             "default_reasoning_level": "high"},
            {"slug": "other-model", "context_window": 100000,
             "shell_type": "default", "apply_patch_tool_type": None,
             "future_metadata": {"keep": True}},
        ]}), encoding="utf-8")
        return home, config, catalog

    def run_adjust(self, home, *extra, env=None):
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "adjust_context_window.py"),
             "--codex-home", str(home), "--profile", "test", "--model", "test-model",
             "--context-window", "400000", *extra],
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            encoding="utf-8", timeout=20, env=env,
        )

    def test_compaction_uses_effective_budget_and_backups_keep_originals(self):
        with tempfile.TemporaryDirectory() as directory:
            home, config, catalog = self.fixture(directory)
            before_config, before_catalog = config.read_bytes(), catalog.read_bytes()
            result = self.run_adjust(home, "--effective-percent", "80", "--yes")
            self.assertEqual(result.returncode, 0, result.stderr)
            updated = tomllib.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(updated["model_context_window"], 400000)
            self.assertEqual(updated["model_auto_compact_token_limit"], 288000)
            self.assertEqual(updated["web_search"], "live")
            self.assertEqual(updated["projects"]["example"]["trust_level"], "trusted")
            self.assertEqual(next(home.glob("test.config.toml.bak.*")).read_bytes(), before_config)
            self.assertEqual(next(home.glob("test-models.json.bak.*")).read_bytes(), before_catalog)

    def test_explicit_compaction_cannot_exceed_effective_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            home, config, catalog = self.fixture(directory)
            before = {p.name: p.read_bytes() for p in home.iterdir()}
            result = self.run_adjust(home, "--effective-percent", "80",
                                     "--compact-limit", "320001", "--yes")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual({p.name: p.read_bytes() for p in home.iterdir()}, before)

    def test_zero_window_and_percentage_are_rejected(self):
        for option in ("--context-window", "--effective-percent"):
            with self.subTest(option=option), tempfile.TemporaryDirectory() as directory:
                home, _, _ = self.fixture(directory)
                before = {p.name: p.read_bytes() for p in home.iterdir()}
                result = self.run_adjust(home, option, "0", "--yes")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual({p.name: p.read_bytes() for p in home.iterdir()}, before)

    def test_init_rejects_zero_window_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "init_profile.py"),
                 "--codex-home", directory, "--model", "test-model", "--provider", "test",
                 "--base-url", "https://example.invalid/v1", "--context-window", "0", "--yes"],
                capture_output=True, text=True, encoding="utf-8", timeout=20,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_bootstrap_preview_and_declined_change_write_nothing(self):
        for mode in ("--dev", "--dry-run", None):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                home, _, catalog = self.fixture(directory)
                catalog.unlink()
                bindir = home / "bin"
                write_fake_codex(bindir, [{"slug": "base-model", "shell_type": "unified_exec"}])
                env = os.environ.copy()
                env["PATH"] = str(bindir) + os.pathsep + env.get("PATH", "")
                before = {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()}
                result = self.run_adjust(home, "--bootstrap-bundled", *([mode] if mode else []), env=env)
                self.assertEqual(result.returncode, 0 if mode else 2, result.stderr)
                self.assertEqual(
                    {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()}, before,
                )

    def test_window_change_preserves_reasoning_tools_and_other_models(self):
        with tempfile.TemporaryDirectory() as directory:
            home, config, catalog = self.fixture(directory)
            before = json.loads(catalog.read_text(encoding="utf-8"))["models"]
            result = self.run_adjust(home, "--yes")
            self.assertEqual(result.returncode, 0, result.stderr)
            after = json.loads(catalog.read_text(encoding="utf-8"))["models"]
            self.assertEqual(after[1], before[1])
            for key in ("supported_reasoning_levels", "default_reasoning_level", "tool_mode"):
                self.assertEqual(after[0][key], before[0][key])
            self.assertEqual(tomllib.loads(config.read_text(encoding="utf-8"))["model_reasoning_effort"], "high")

    def test_existing_null_patch_preference_survives_window_update(self):
        with tempfile.TemporaryDirectory() as directory:
            home, _, catalog = self.fixture(directory)
            data = json.loads(catalog.read_text(encoding="utf-8"))
            data["models"][0]["apply_patch_tool_type"] = None
            catalog.write_text(json.dumps(data), encoding="utf-8")
            result = self.run_adjust(home, "--yes")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsNone(json.loads(catalog.read_text(encoding="utf-8"))["models"][0]["apply_patch_tool_type"])

    def test_metadata_only_update_keeps_existing_window(self):
        with tempfile.TemporaryDirectory() as directory:
            home, config, catalog = self.fixture(directory)
            config.write_text(config.read_text(encoding="utf-8").replace(
                'model = "test-model"', 'model = "test-model"\nmodel_context_window = 200000'), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "adjust_context_window.py"),
                 "--codex-home", str(home), "--profile", "test", "--model", "test-model",
                 "--web-search-type", "text", "--yes"],
                capture_output=True, text=True, encoding="utf-8", timeout=20,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(catalog.read_text(encoding="utf-8"))["models"][0]["context_window"], 200000)

    def test_catalog_only_requires_catalog_to_be_referenced(self):
        with tempfile.TemporaryDirectory() as directory:
            home, config, _ = self.fixture(directory)
            config.write_text('model = "test-model"\n', encoding="utf-8")
            before = {p.name: p.read_bytes() for p in home.iterdir()}
            result = self.run_adjust(home, "--catalog-only", "--yes")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual({p.name: p.read_bytes() for p in home.iterdir()}, before)


if __name__ == "__main__":
    unittest.main()
