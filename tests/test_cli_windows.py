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


def write_fake_codex(bindir: Path, models: list) -> None:
    bindir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"models": models}, ensure_ascii=False)
    helper = bindir / "_codex_debug.py"
    helper.write_text(
        "import sys\n"
        f"data = {payload!r}\n"
        "args = sys.argv[1:]\n"
        "if args[:2] == ['debug', 'models'] and '--bundled' in args:\n"
        "    sys.stdout.buffer.write(data.encode('utf-8'))\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(2)\n",
        encoding="utf-8",
    )
    launcher = (
        f"import runpy, sys\n"
        f"sys.argv = [sys.argv[0], *sys.argv[1:]]\n"
        f"runpy.run_path({str(helper)!r}, run_name='__main__')\n"
    )
    if os.name == "nt":
        py = bindir / "_codex_launch.py"
        py.write_text(launcher, encoding="utf-8")
        (bindir / "codex.cmd").write_text(
            f"@echo off\r\n\"{sys.executable}\" \"{py}\" %*\r\n",
            encoding="utf-8",
        )
    shim = bindir / "codex"
    shim.write_text("#!/usr/bin/env python3\n" + launcher, encoding="utf-8")
    try:
        shim.chmod(0o755)
    except OSError:
        pass

from adjust_context_window import (
    cleaned_path,
    decode_utf8_output,
    dump_bundled_catalog,
    find_source_entry,
    is_reserved_catalog,
    resolve_catalog_path,
)
from model_meta import install_as_default_config
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
            (home / "yjwd-grok-models.json").write_text(
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
            catalog = json.loads((home / "yjwd-grok-models.json").read_text(encoding="utf-8"))
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
            catalog = json.loads((home / "yjwd-grok-models.json").read_text(encoding="utf-8"))
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
            catalog = json.loads((home / "yjwd-grok-models.json").read_text(encoding="utf-8"))
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
            (home / "yjwd-grok-models.json").write_text(
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

    def test_exact_user_command_missing_profile_catalog_and_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "codex-home"
            home.mkdir()
            bindir = root / "bin"
            write_fake_codex(
                bindir,
                [{"slug": "gpt-5.5", "display_name": "GPT", "context_window": 272000}],
            )
            env = os.environ.copy()
            env["PATH"] = str(bindir) + os.pathsep + env.get("PATH", "")
            env["CODEX_HOME"] = str(home)
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "adjust_context_window.py"),
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
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("does not exist", result.stderr)
            self.assertIn("synthesizing", result.stderr)
            profile = (home / "yjwd-grok.config.toml").read_text(encoding="utf-8")
            self.assertIn('model = "grok-4.6"', profile)
            self.assertIn("model_context_window = 300000", profile)
            self.assertIn("yjwd-grok-models.json", profile)
            self.assertFalse((home / "models.json").exists())
            catalog = json.loads((home / "yjwd-grok-models.json").read_text(encoding="utf-8"))
            grok = next(item for item in catalog["models"] if item["slug"] == "grok-4.6")
            self.assertEqual(grok["context_window"], 300000)
            self.assertEqual(grok.get("shell_type"), "shell_command")
            self.assertEqual(
                [item["effort"] for item in grok["supported_reasoning_levels"]],
                ["low", "medium", "high", "xhigh"],
            )
            self.assertIn("cloned from:          (synthesized)", result.stdout)

    def test_reserved_models_json_is_migrated(self):
        import adjust_context_window as mod

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "yjwd-grok.config.toml").write_text(
                'model = "grok-4.6"\n'
                'model_catalog_json = "' + (home / "models.json").as_posix() + '"\n',
                encoding="utf-8",
            )
            (home / "models.json").write_text(
                json.dumps({"models": [{"slug": "gpt-5.5", "context_window": 272000}]}),
                encoding="utf-8",
            )
            (home / "yjwd-grok-models.json").write_text(
                json.dumps(
                    {
                        "models": [
                            {"slug": "gpt-5.5", "context_window": 272000, "shell_type": "shell_command"},
                            {"slug": "grok-4.6", "context_window": 1000},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            argv = [
                "adjust_context_window.py",
                "--model",
                "grok-4.6",
                "--profile",
                "yjwd-grok",
                "--context-window",
                "300000",
                "--yes",
                "--codex-home",
                str(home),
            ]
            with mock.patch.object(sys, "argv", argv):
                rc = mod.main()
            self.assertEqual(rc, 0)
            toml = (home / "yjwd-grok.config.toml").read_text(encoding="utf-8")
            self.assertIn("yjwd-grok-models.json", toml)
            self.assertNotIn('model_catalog_json = "' + (home / "models.json").as_posix() + '"', toml)
            catalog = json.loads((home / "yjwd-grok-models.json").read_text(encoding="utf-8"))
            grok = next(item for item in catalog["models"] if item["slug"] == "grok-4.6")
            self.assertEqual(grok["context_window"], 300000)
            self.assertEqual(grok.get("shell_type"), "shell_command")
            # Codex-reserved file is left alone
            original = json.loads((home / "models.json").read_text(encoding="utf-8"))
            self.assertEqual(original["models"][0]["slug"], "gpt-5.5")

    def test_existing_custom_catalog_is_edited(self):
        import adjust_context_window as mod

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            custom = home / "openrouter-models.json"
            (home / "yjwd-grok.config.toml").write_text(
                'model = "grok-4.6"\n'
                'model_catalog_json = "' + custom.as_posix() + '"\n',
                encoding="utf-8",
            )
            custom.write_text(
                json.dumps({"models": [{"slug": "grok-4.6", "context_window": 1000}]}),
                encoding="utf-8",
            )
            argv = [
                "adjust_context_window.py",
                "--model",
                "grok-4.6",
                "--profile",
                "yjwd-grok",
                "--context-window",
                "300000",
                "--yes",
                "--codex-home",
                str(home),
            ]
            with mock.patch.object(sys, "argv", argv):
                rc = mod.main()
            self.assertEqual(rc, 0)
            self.assertFalse((home / "yjwd-grok-models.json").exists())
            catalog = json.loads(custom.read_text(encoding="utf-8"))
            grok = next(item for item in catalog["models"] if item["slug"] == "grok-4.6")
            self.assertEqual(grok["context_window"], 300000)
            toml = (home / "yjwd-grok.config.toml").read_text(encoding="utf-8")
            self.assertIn("openrouter-models.json", toml)

    def test_explicit_catalog_flag_edits_existing_file(self):
        import adjust_context_window as mod

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            custom = home / "already.json"
            (home / "yjwd-grok.config.toml").write_text(
                'model = "grok-4.6"\n',
                encoding="utf-8",
            )
            custom.write_text(
                json.dumps({"models": [{"slug": "grok-4.6", "context_window": 1000}]}),
                encoding="utf-8",
            )
            argv = [
                "adjust_context_window.py",
                "--model",
                "grok-4.6",
                "--profile",
                "yjwd-grok",
                "--catalog",
                str(custom),
                "--context-window",
                "300000",
                "--yes",
                "--codex-home",
                str(home),
            ]
            with mock.patch.object(sys, "argv", argv):
                rc = mod.main()
            self.assertEqual(rc, 0)
            self.assertFalse((home / "yjwd-grok-models.json").exists())
            catalog = json.loads(custom.read_text(encoding="utf-8"))
            grok = next(item for item in catalog["models"] if item["slug"] == "grok-4.6")
            self.assertEqual(grok["context_window"], 300000)

    def test_as_default_copies_profile_over_config_toml(self):
        import adjust_context_window as mod

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "config.toml").write_text('model = "old-model"\n', encoding="utf-8")
            (home / "yjwd-grok.config.toml").write_text(
                'model = "grok-4.6"\n',
                encoding="utf-8",
            )
            (home / "yjwd-grok-models.json").write_text(
                json.dumps({"models": [{"slug": "grok-4.6", "context_window": 1000}]}),
                encoding="utf-8",
            )
            argv = [
                "adjust_context_window.py",
                "--model",
                "grok-4.6",
                "--profile",
                "yjwd-grok",
                "--context-window",
                "300000",
                "--as-default",
                "--yes",
                "--codex-home",
                str(home),
            ]
            with mock.patch.object(sys, "argv", argv):
                rc = mod.main()
            self.assertEqual(rc, 0)
            default = (home / "config.toml").read_text(encoding="utf-8")
            self.assertIn('model = "grok-4.6"', default)
            self.assertIn("model_context_window = 300000", default)
            backups = list(home.glob("config.toml.bak.*"))
            self.assertEqual(len(backups), 1)
            self.assertIn('model = "old-model"', backups[0].read_text(encoding="utf-8"))

    def test_as_default_dry_run_does_not_replace_config(self):
        import adjust_context_window as mod

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "config.toml").write_text('model = "old-model"\n', encoding="utf-8")
            (home / "yjwd-grok.config.toml").write_text(
                'model = "grok-4.6"\n',
                encoding="utf-8",
            )
            (home / "yjwd-grok-models.json").write_text(
                json.dumps({"models": [{"slug": "grok-4.6", "context_window": 1000}]}),
                encoding="utf-8",
            )
            argv = [
                "adjust_context_window.py",
                "--model",
                "grok-4.6",
                "--profile",
                "yjwd-grok",
                "--as-default",
                "--dry-run",
                "--codex-home",
                str(home),
            ]
            with mock.patch.object(sys, "argv", argv):
                rc = mod.main()
            self.assertEqual(rc, 0)
            self.assertEqual((home / "config.toml").read_text(encoding="utf-8"), 'model = "old-model"\n')
            self.assertFalse(list(home.glob("config.toml.bak.*")))


class DefaultConfigInstallTests(unittest.TestCase):
    def test_backup_then_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            source = home / "yjwd-grok.config.toml"
            default = home / "config.toml"
            source.write_text('model = "grok-4.6"\n', encoding="utf-8")
            default.write_text('model = "old"\n', encoding="utf-8")
            backup = install_as_default_config(source, default)
            self.assertIsNotNone(backup)
            self.assertTrue(backup.exists())
            self.assertEqual(default.read_text(encoding="utf-8"), 'model = "grok-4.6"\n')
            self.assertEqual(backup.read_text(encoding="utf-8"), 'model = "old"\n')

    def test_init_profile_as_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "config.toml").write_text('model = "old"\n', encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "init_profile.py"),
                    "--model",
                    "grok-4.6",
                    "--provider",
                    "yjwd-grok",
                    "--base-url",
                    "https://example.invalid/v1",
                    "--as-default",
                    "--yes",
                    "--codex-home",
                    str(home),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            profile = (home / "yjwd-grok.config.toml").read_text(encoding="utf-8")
            default = (home / "config.toml").read_text(encoding="utf-8")
            self.assertEqual(profile, default)
            self.assertIn('model = "grok-4.6"', default)
            backups = list(home.glob("config.toml.bak.*"))
            self.assertEqual(len(backups), 1)
            self.assertIn('model = "old"', backups[0].read_text(encoding="utf-8"))


class CatalogPathTests(unittest.TestCase):
    def test_codex_home_models_json_is_reserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.assertTrue(is_reserved_catalog(home / "models.json", home))
            self.assertFalse(is_reserved_catalog(home / "yjwd-grok-models.json", home))

    def test_resolve_skips_reserved_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            path, note = resolve_catalog_path(
                explicit=None,
                config_text='model_catalog_json = "' + (home / "models.json").as_posix() + '"\n',
                codex_home=home,
                profile="yjwd-grok",
            )
            self.assertEqual(path, (home / "yjwd-grok-models.json").resolve())
            self.assertIsNotNone(note)

    def test_explicit_catalog_keeps_reserved_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            reserved = home / "models.json"
            path, note = resolve_catalog_path(
                explicit=str(reserved),
                config_text="",
                codex_home=home,
                profile="yjwd-grok",
            )
            self.assertEqual(path, reserved.resolve())
            self.assertIsNotNone(note)

    def test_existing_toml_catalog_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            custom = home / "openrouter-models.json"
            path, note = resolve_catalog_path(
                explicit=None,
                config_text='model_catalog_json = "' + custom.as_posix() + '"\n',
                codex_home=home,
                profile="yjwd-grok",
            )
            self.assertEqual(path, custom.resolve())
            self.assertIsNone(note)


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
