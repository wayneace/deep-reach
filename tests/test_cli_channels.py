import argparse
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from deep_reach.cli import cmd_channels, cmd_setup
from deep_reach.runtime.keys import Keys
from deep_reach.runtime.result import CONFIG_ERROR, ReachError


class ChannelsJsonTest(unittest.TestCase):
    def test_json_has_effective_next_action(self):
        with mock.patch("deep_reach.cli._load_keys", return_value=Keys({})), mock.patch(
            "deep_reach.runtime.availability.shutil.which", return_value=None
        ), mock.patch.dict("os.environ", {"DEEP_REACH_OPENCLI_BIN": ""}):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = cmd_channels(argparse.Namespace(json=True))

        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        row = next(item for item in payload["channels"] if item["name"] == "weibo")
        self.assertEqual(row["status"], "needs_setup")
        self.assertIn("OpenCLI", row["effective_next_action"])
        self.assertIn("npm install -g @jackwener/opencli", row["effective_next_action"])
        self.assertIn("next_action", row)

    def test_json_shows_risk_and_ui_fallback(self):
        with mock.patch("deep_reach.cli._load_keys", return_value=Keys({})), mock.patch(
            "deep_reach.runtime.availability.shutil.which", return_value=None
        ), mock.patch(
            "deep_reach.runtime.availability.bsk_available", return_value=True
        ), mock.patch.dict("os.environ", {"DEEP_REACH_OPENCLI_BIN": ""}):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = cmd_channels(argparse.Namespace(json=True))

        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        row = next(
            item for item in payload["channels"] if item["name"] == "xiaohongshu"
        )
        self.assertEqual(row["status"], "fallback")
        self.assertEqual(row["risk"], "high")
        self.assertEqual(
            set(row["ui_fallback_actions"]), {"search", "read", "comments"}
        )
        action = next(item for item in row["actions"] if item["name"] == "search")
        self.assertTrue(action["ui_fallback"])
        self.assertEqual(action["risk"], "high")
        self.assertIn("deep-reach bsk", row["effective_next_action"])

    def test_text_shows_risk_and_bsk_suffix(self):
        with mock.patch("deep_reach.cli._load_keys", return_value=Keys({})), mock.patch(
            "deep_reach.runtime.availability.shutil.which", return_value=None
        ), mock.patch(
            "deep_reach.runtime.availability.bsk_available", return_value=True
        ), mock.patch.dict("os.environ", {"DEEP_REACH_OPENCLI_BIN": ""}):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = cmd_channels(argparse.Namespace(json=False))

        self.assertEqual(code, 0)
        line = next(
            line
            for line in buffer.getvalue().splitlines()
            if line.strip().startswith("xiaohongshu")
        )
        self.assertIn("risk=high", line)
        self.assertIn("search(bsk)", line)

    def test_text_only_marks_actual_fallback_routes(self):
        keys = Keys({"xueqiu": {"cookie": "x"}})
        with mock.patch("deep_reach.cli._load_keys", return_value=keys), mock.patch(
            "deep_reach.runtime.availability.shutil.which", return_value=None
        ), mock.patch.dict("os.environ", {"DEEP_REACH_OPENCLI_BIN": ""}):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = cmd_channels(argparse.Namespace(json=False))

        self.assertEqual(code, 0)
        line = next(
            line
            for line in buffer.getvalue().splitlines()
            if line.strip().startswith("xueqiu")
        )
        self.assertNotIn("hot(bsk)", line)
        self.assertNotIn("hot_stocks(bsk)", line)

    def test_bsk_only_channel_next_action_omits_opencli_login(self):
        with mock.patch("deep_reach.cli._load_keys", return_value=Keys({})), mock.patch(
            "deep_reach.runtime.availability.shutil.which",
            return_value="/usr/bin/opencli",
        ), mock.patch(
            "deep_reach.runtime.availability.bsk_available", return_value=True
        ), mock.patch.dict("os.environ", {"DEEP_REACH_OPENCLI_BIN": ""}):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = cmd_channels(argparse.Namespace(json=True))

        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        row = next(item for item in payload["channels"] if item["name"] == "x")
        self.assertEqual(row["status"], "fallback")
        self.assertTrue(row["runnable"])
        self.assertIn("deep-reach bsk", row["effective_next_action"])
        self.assertNotIn("OpenCLI", row["effective_next_action"])
        self.assertNotIn("Chrome profile", row["effective_next_action"])
        self.assertNotIn("Chrome profile", row["next_action"])
        self.assertNotIn("OpenCLI", row["next_action"])


class SetupDeploymentTest(unittest.TestCase):
    def _keys(self, tmp):
        return Path(tmp) / "home" / ".deep-reach" / "keys.yaml"

    def test_setup_dry_run_makes_no_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            key_path = self._keys(tmp)
            with mock.patch(
                "deep_reach.cli._load_keys",
                return_value=Keys({}, path=key_path),
            ):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = cmd_setup(
                        argparse.Namespace(dry_run=True, yes=False)
                    )

            self.assertEqual(code, 0)
            self.assertFalse(key_path.exists())
            self.assertIn("Will create", buffer.getvalue())

    def test_setup_yes_creates_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            key_path = self._keys(tmp)
            with mock.patch(
                "deep_reach.cli._load_keys",
                return_value=Keys({}, path=key_path),
            ), mock.patch(
                "deep_reach.runtime.setup.detect_opencli_version", return_value=""
            ):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = cmd_setup(
                        argparse.Namespace(dry_run=False, yes=True)
                    )

            self.assertEqual(code, 0)
            self.assertTrue(key_path.exists())
            output = buffer.getvalue()
            self.assertIn("Empty keys", output)
            self.assertIn("chromewebstore.google.com", output)
            self.assertIn("cli_install", output)
            self.assertIn("npm:@jackwener/opencli", output)

    def test_setup_dry_run_does_not_create_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            with mock.patch(
                "pathlib.Path.home", return_value=home
            ), mock.patch.dict(
                "os.environ", {"DEEP_REACH_KEYS_FILE": ""}
            ), mock.patch(
                "deep_reach.runtime.setup.detect_opencli_version", return_value=""
            ):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = cmd_setup(
                        argparse.Namespace(dry_run=True, yes=False)
                    )

            self.assertEqual(code, 0)
            self.assertFalse((home / ".deep-reach").exists())

    def test_setup_dry_run_does_not_tighten_existing_file(self):
        if os.name == "nt":
            self.skipTest("POSIX permissions only")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            parent = home / ".deep-reach"
            parent.mkdir(mode=0o755, parents=True)
            key_path = parent / "keys.yaml"
            key_path.write_text("version: 1\n", encoding="utf-8")
            key_path.chmod(0o644)
            with mock.patch(
                "pathlib.Path.home", return_value=home
            ), mock.patch.dict(
                "os.environ", {"DEEP_REACH_KEYS_FILE": ""}
            ), mock.patch(
                "deep_reach.runtime.setup.detect_opencli_version", return_value=""
            ):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = cmd_setup(
                        argparse.Namespace(dry_run=True, yes=False)
                    )

            self.assertEqual(code, 0)
            self.assertEqual(key_path.stat().st_mode & 0o777, 0o644)
            self.assertEqual(parent.stat().st_mode & 0o777, 0o755)

    def test_setup_yes_reports_created_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            with mock.patch(
                "pathlib.Path.home", return_value=home
            ), mock.patch.dict(
                "os.environ", {"DEEP_REACH_KEYS_FILE": ""}
            ), mock.patch(
                "deep_reach.runtime.setup.detect_opencli_version", return_value=""
            ):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = cmd_setup(
                        argparse.Namespace(dry_run=False, yes=True)
                    )

            output = buffer.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("created  ~/.deep-reach  700", output)
            self.assertIn("created  ~/.deep-reach/keys.yaml  600", output)
            self.assertTrue((home / ".deep-reach").is_dir())

    def test_setup_opencli_installed_skips_install_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            key_path = self._keys(tmp)
            with mock.patch(
                "deep_reach.cli._load_keys",
                return_value=Keys({}, path=key_path),
            ), mock.patch(
                "deep_reach.runtime.setup.detect_opencli_version",
                return_value="2.0.3",
            ):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = cmd_setup(
                        argparse.Namespace(dry_run=True, yes=False)
                    )

            output = buffer.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("installed; no install needed", output)
            self.assertNotIn("cli_install", output)

    def test_setup_declined_makes_no_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            key_path = self._keys(tmp)
            with mock.patch(
                "deep_reach.cli._load_keys",
                return_value=Keys({}, path=key_path),
            ), mock.patch(
                "deep_reach.cli.sys.stdin.isatty", return_value=True
            ), mock.patch("builtins.input", return_value="n"):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = cmd_setup(
                        argparse.Namespace(dry_run=False, yes=False)
                    )

            self.assertEqual(code, 2)
            self.assertFalse(key_path.exists())

    def test_setup_non_interactive_without_yes_makes_no_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            key_path = self._keys(tmp)
            with mock.patch(
                "deep_reach.cli._load_keys",
                return_value=Keys({}, path=key_path),
            ), mock.patch(
                "deep_reach.cli.sys.stdin.isatty", return_value=False
            ):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = cmd_setup(
                        argparse.Namespace(dry_run=False, yes=False)
                    )

            self.assertEqual(code, 2)
            self.assertFalse(key_path.exists())
            self.assertIn("--yes", buffer.getvalue())

    def test_setup_eof_makes_no_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            key_path = self._keys(tmp)
            with mock.patch(
                "deep_reach.cli._load_keys",
                return_value=Keys({}, path=key_path),
            ), mock.patch(
                "deep_reach.cli.sys.stdin.isatty", return_value=True
            ), mock.patch("builtins.input", side_effect=EOFError):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = cmd_setup(
                        argparse.Namespace(dry_run=False, yes=False)
                    )

            self.assertEqual(code, 2)
            self.assertFalse(key_path.exists())

    def test_setup_write_error_returns_config_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            with mock.patch(
                "pathlib.Path.home", return_value=home
            ), mock.patch.dict(
                "os.environ", {"DEEP_REACH_KEYS_FILE": ""}
            ), mock.patch(
                "deep_reach.runtime.setup.detect_opencli_version", return_value=""
            ), mock.patch(
                "deep_reach.runtime.setup.os.open",
                side_effect=PermissionError("denied"),
            ):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = cmd_setup(
                        argparse.Namespace(dry_run=False, yes=True)
                    )

            self.assertEqual(code, 2)

    def test_setup_invalid_yaml_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            key_path = self._keys(tmp)
            key_path.parent.mkdir(parents=True)
            key_path.write_text("bad: [", encoding="utf-8")
            with mock.patch(
                "deep_reach.cli._load_keys",
                side_effect=ReachError(CONFIG_ERROR, "invalid YAML"),
            ):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = cmd_setup(
                        argparse.Namespace(dry_run=False, yes=True)
                    )

            self.assertEqual(code, 2)
            self.assertEqual(key_path.read_text(encoding="utf-8"), "bad: [")


if __name__ == "__main__":
    unittest.main()
