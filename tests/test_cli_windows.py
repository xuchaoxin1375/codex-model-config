import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from adjust_context_window import (
    cleaned_path,
    decode_utf8_output,
    dump_bundled_catalog,
    find_source_entry,
)
from model_meta import parse_reasoning_levels


class DecodeUtf8Tests(unittest.TestCase):
    def test_decodes_utf8_json_with_non_ascii(self):
        payload = json.dumps(
            {"models": [{"slug": "grok-4.6", "display_name": "model\u2026"}]},
            ensure_ascii=False,
        ).encode("utf-8")
        data = json.loads(decode_utf8_output(payload))
        self.assertEqual(data["models"][0]["slug"], "grok-4.6")
        self.assertTrue(data["models"][0]["display_name"].endswith("\u2026"))

    def test_gbk_cannot_decode_utf8_ellipsis(self):
        raw = b"\xe2\x80\xa6"
        with self.assertRaises(UnicodeDecodeError):
            raw.decode("gbk")
        self.assertEqual(decode_utf8_output(raw), "\u2026")

    def test_none_becomes_empty(self):
        self.assertEqual(decode_utf8_output(None), "")

    def test_stderr_replace_does_not_raise(self):
        # GBK-ish bytes that are invalid UTF-8 should not crash stderr decoding.
        raw = b"\xa6warning"
        self.assertIsInstance(decode_utf8_output(raw, errors="replace"), str)


class ReasoningLevelsParseTests(unittest.TestCase):
    def test_comma_separated(self):
        self.assertEqual(
            parse_reasoning_levels("low,medium,high,xhigh"),
            ["low", "medium", "high", "xhigh"],
        )

    def test_powershell_space_joined_array(self):
        self.assertEqual(
            parse_reasoning_levels("low medium high xhigh"),
            ["low", "medium", "high", "xhigh"],
        )


class CleanedPathTests(unittest.TestCase):
    def test_strips_spaces_around_path_entries(self):
        original = os.environ.get("PATH")
        try:
            os.environ["PATH"] = " C:\\foo ;C:\\bar; "
            parts = cleaned_path().split(os.pathsep)
            self.assertEqual(parts[0], "C:\\foo")
            self.assertEqual(parts[1], "C:\\bar")
        finally:
            if original is None:
                os.environ.pop("PATH", None)
            else:
                os.environ["PATH"] = original


class FindSourceEntryTests(unittest.TestCase):
    def test_vendor_prefixed_unique_suffix(self):
        models = [
            {"slug": "gpt-5.5"},
            {"slug": "x-ai/grok-4.6", "context_window": 500000},
        ]
        found, cloned_from = find_source_entry(models, "grok-4.6", None)
        self.assertEqual(cloned_from, "x-ai/grok-4.6")
        self.assertEqual(found["context_window"], 500000)

    def test_exact_slug_wins(self):
        models = [{"slug": "grok-4.6", "context_window": 1}]
        found, cloned_from = find_source_entry(models, "grok-4.6", None)
        self.assertEqual(cloned_from, "grok-4.6")
        self.assertEqual(found["context_window"], 1)

    def test_ambiguous_suffix_is_none(self):
        models = [{"slug": "x-ai/grok-4.6"}, {"slug": "vendor/grok-4.6"}]
        self.assertIsNone(find_source_entry(models, "grok-4.6", None))


class DumpBundledCatalogTests(unittest.TestCase):
    def test_writes_utf8_catalog_without_text_true(self):
        payload = json.dumps(
            {"models": [{"slug": "grok-4.6", "display_name": "model\u2026"}]},
            ensure_ascii=False,
        ).encode("utf-8")
        captured = {}

        class Result:
            returncode = 0
            stdout = payload
            stderr = b"\xa6ignored"

        import adjust_context_window as mod

        def fake_run(*args, **kwargs):
            captured.update(kwargs)
            captured["argv"] = args[0] if args else kwargs.get("args")
            return Result()

        original_run = mod.subprocess.run
        original_resolve = mod.resolve_codex
        try:
            mod.subprocess.run = fake_run
            mod.resolve_codex = lambda: "codex"
            with tempfile.TemporaryDirectory() as tmp:
                catalog = Path(tmp) / "models.json"
                data = dump_bundled_catalog(catalog)
                self.assertEqual(data["models"][0]["slug"], "grok-4.6")
                loaded = json.loads(catalog.read_text(encoding="utf-8"))
                self.assertTrue(loaded["models"][0]["display_name"].endswith("\u2026"))
        finally:
            mod.subprocess.run = original_run
            mod.resolve_codex = original_resolve

        self.assertFalse(captured.get("text"))
        self.assertIsNone(captured.get("encoding"))
        self.assertTrue(captured.get("capture_output"))

    def test_empty_stdout_raises(self):
        class Result:
            returncode = 0
            stdout = b""
            stderr = b""

        import adjust_context_window as mod

        original_run = mod.subprocess.run
        original_resolve = mod.resolve_codex
        try:
            mod.subprocess.run = lambda *args, **kwargs: Result()
            mod.resolve_codex = lambda: "codex"
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(RuntimeError) as ctx:
                    dump_bundled_catalog(Path(tmp) / "models.json")
            self.assertIn("empty stdout", str(ctx.exception))
        finally:
            mod.subprocess.run = original_run
            mod.resolve_codex = original_resolve

    def test_invalid_utf8_stdout_has_clear_error(self):
        class Result:
            returncode = 0
            stdout = b"\xa6not-utf8"
            stderr = b""

        import adjust_context_window as mod

        original_run = mod.subprocess.run
        original_resolve = mod.resolve_codex
        try:
            mod.subprocess.run = lambda *args, **kwargs: Result()
            mod.resolve_codex = lambda: "codex"
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(RuntimeError) as ctx:
                    dump_bundled_catalog(Path(tmp) / "models.json")
            self.assertIn("UTF-8", str(ctx.exception))
        finally:
            mod.subprocess.run = original_run
            mod.resolve_codex = original_resolve


class AdjustCliIntegrationTests(unittest.TestCase):
    def test_user_command_from_cache_vendor_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "yjwd-grok.config.toml").write_text(
                'model = "grok-4.6"\n'
                'model_provider = "yjwd-grok"\n'
                'model_reasoning_effort = "high"\n',
                encoding="utf-8",
            )
            (home / "models.json").write_text(
                json.dumps({"models": [{"slug": "gpt-5.5", "context_window": 272000}]}),
                encoding="utf-8",
            )
            (home / "models_cache.json").write_text(
                json.dumps(
                    {
                        "models": [
                            {
                                "slug": "x-ai/grok-4.6",
                                "display_name": "Grok 4.6",
                                "context_window": 500000,
                                "supported_reasoning_levels": [
                                    {"effort": "low", "description": "Fast"}
                                ],
                                "input_modalities": ["text", "image"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "adjust_context_window.py"),
                    "--model",
                    "grok-4.6",
                    "--profile",
                    "yjwd-grok",
                    "--from-cache",
                    "--context-window",
                    "300000",
                    "--reasoning-levels",
                    "low,medium,high,xhigh",
                    "--yes",
                    "--codex-home",
                    str(home),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            catalog = json.loads((home / "models.json").read_text(encoding="utf-8"))
            grok = next(item for item in catalog["models"] if item["slug"] == "grok-4.6")
            self.assertEqual(grok["context_window"], 300000)
            self.assertEqual(grok["max_context_window"], 300000)
            self.assertEqual(
                [item["effort"] for item in grok["supported_reasoning_levels"]],
                ["low", "medium", "high", "xhigh"],
            )
            toml = (home / "yjwd-grok.config.toml").read_text(encoding="utf-8")
            self.assertIn("model_context_window = 300000", toml)
            self.assertIn("cloned from:          x-ai/grok-4.6", result.stdout)

    def test_bootstrap_bundled_then_from_cache(self):
        import adjust_context_window as mod

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "yjwd-grok.config.toml").write_text(
                'model = "grok-4.6"\nmodel_provider = "yjwd-grok"\n',
                encoding="utf-8",
            )
            (home / "models_cache.json").write_text(
                json.dumps({"models": [{"slug": "x-ai/grok-4.6", "context_window": 500000}]}),
                encoding="utf-8",
            )

            def fake_dump(catalog: Path):
                data = {"models": [{"slug": "gpt-5.5", "display_name": "model\u2026"}]}
                catalog.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                return data

            argv = [
                "adjust_context_window.py",
                "--model",
                "grok-4.6",
                "--profile",
                "yjwd-grok",
                "--bootstrap-bundled",
                "--from-cache",
                "--context-window",
                "300000",
                "--reasoning-levels",
                "low,medium,high,xhigh",
                "--yes",
                "--codex-home",
                str(home),
            ]
            with mock.patch.object(sys, "argv", argv):
                with mock.patch.object(mod, "dump_bundled_catalog", fake_dump):
                    rc = mod.main()
            self.assertEqual(rc, 0)
            catalog = json.loads((home / "models.json").read_text(encoding="utf-8"))
            slugs = [item["slug"] for item in catalog["models"]]
            self.assertIn("gpt-5.5", slugs)
            self.assertIn("grok-4.6", slugs)

    def test_missing_profile_creates_from_template(self):
        import adjust_context_window as mod

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "models_cache.json").write_text(
                json.dumps({"models": [{"slug": "x-ai/grok-4.6", "context_window": 500000}]}),
                encoding="utf-8",
            )

            def fake_dump(catalog: Path):
                data = {"models": [{"slug": "gpt-5.5", "display_name": "model"}]}
                catalog.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                return data

            argv = [
                "adjust_context_window.py",
                "--model",
                "grok-4.6",
                "--profile",
                "yjwd-grok",
                "--bootstrap-bundled",
                "--from-cache",
                "--context-window",
                "300000",
                "--reasoning-levels",
                "low,medium,high,xhigh",
                "--base-url",
                "https://example.invalid/v1",
                "--yes",
                "--codex-home",
                str(home),
            ]
            with mock.patch.object(sys, "argv", argv):
                with mock.patch.object(mod, "dump_bundled_catalog", fake_dump):
                    rc = mod.main()
            self.assertEqual(rc, 0)
            profile = (home / "yjwd-grok.config.toml").read_text(encoding="utf-8")
            self.assertIn('model = "grok-4.6"', profile)
            self.assertIn('model_provider = "yjwd-grok"', profile)
            self.assertIn('base_url = "https://example.invalid/v1"', profile)
            self.assertIn("model_context_window = 300000", profile)
            catalog = json.loads((home / "models.json").read_text(encoding="utf-8"))
            self.assertIn("grok-4.6", [item["slug"] for item in catalog["models"]])

    def test_missing_default_config_explains_profile(self):
        import adjust_context_window as mod

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            argv = [
                "adjust_context_window.py",
                "--model",
                "grok-4.6",
                "--yes",
                "--codex-home",
                str(home),
            ]
            with mock.patch.object(sys, "argv", argv):
                with self.assertRaises(SystemExit) as ctx:
                    mod.main()
            self.assertNotEqual(ctx.exception.code, 0)

    def test_missing_profile_dry_run_does_not_write(self):
        import adjust_context_window as mod

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "models.json").write_text(
                json.dumps({"models": [{"slug": "grok-4.6", "context_window": 272000}]}),
                encoding="utf-8",
            )
            argv = [
                "adjust_context_window.py",
                "--model",
                "grok-4.6",
                "--profile",
                "yjwd-grok",
                "--dry-run",
                "--codex-home",
                str(home),
            ]
            with mock.patch.object(sys, "argv", argv):
                rc = mod.main()
            self.assertEqual(rc, 0)
            self.assertFalse((home / "yjwd-grok.config.toml").exists())


class LiveCodexDumpTests(unittest.TestCase):
    def test_live_bundled_catalog_is_utf8_json(self):
        try:
            from adjust_context_window import resolve_codex
            resolve_codex()
        except RuntimeError:
            self.skipTest("codex executable not on PATH")
        with tempfile.TemporaryDirectory() as tmp:
            catalog = Path(tmp) / "models.json"
            data = dump_bundled_catalog(catalog)
            self.assertIsInstance(data.get("models"), list)
            self.assertGreater(len(data["models"]), 0)
            json.loads(catalog.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
