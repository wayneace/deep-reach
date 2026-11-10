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
from deep_reach.runtime.keys import Keys, template_path


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


class SetupTextTest(unittest.TestCase):
    def test_setup_prompts_opencli_install_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            key_path = Path(tmp) / "home" / ".deep-reach" / "keys.yaml"
            with mock.patch(
                "deep_reach.cli.shutil.which", return_value=None
            ), mock.patch(
                "deep_reach.cli._load_keys",
                return_value=Keys({}, path=key_path),
            ), mock.patch(
                "deep_reach.cli.profile_status",
                return_value={
                    "opencli": {
                        "connected": False,
                        "configured": False,
                        "context_id": None,
                    }
                },
            ), mock.patch.dict("os.environ", {"DEEP_REACH_OPENCLI_BIN": ""}):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = cmd_setup(argparse.Namespace())

            self.assertTrue(key_path.parent.is_dir())
        output = buffer.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("npm install -g @jackwener/opencli", output)
        self.assertIn(
            f"Keys: optional — copy {template_path()} to {key_path}.", output
        )

    def test_setup_reports_insecure_keys_mode(self):
        if os.name == "nt":
            self.skipTest("POSIX permissions only")
        with tempfile.TemporaryDirectory() as tmp:
            key_path = Path(tmp) / "keys.yaml"
            key_path.write_text("version: 1\n", encoding="utf-8")
            os.chmod(key_path, 0o644)
            with mock.patch(
                "deep_reach.cli.shutil.which", return_value=None
            ), mock.patch(
                "deep_reach.cli._load_keys",
                return_value=Keys({}, path=key_path),
            ), mock.patch(
                "deep_reach.cli.profile_status",
                return_value={
                    "opencli": {
                        "connected": False,
                        "configured": False,
                        "context_id": None,
                    }
                },
            ), mock.patch.dict("os.environ", {"DEEP_REACH_OPENCLI_BIN": ""}):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = cmd_setup(argparse.Namespace())
        output = buffer.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("keys mode", output)
        self.assertIn("644", output)
        self.assertIn("warning", output)

    def test_setup_points_to_keys_file_when_browser_connected(self):
        with tempfile.TemporaryDirectory() as tmp:
            key_path = Path(tmp) / "keys.yaml"
            with mock.patch(
                "deep_reach.cli.shutil.which", return_value="/usr/bin/opencli"
            ), mock.patch(
                "deep_reach.cli._load_keys",
                return_value=Keys({}, path=key_path),
            ), mock.patch(
                "deep_reach.cli.profile_status",
                return_value={
                    "opencli": {
                        "connected": True,
                        "configured": True,
                        "context_id": "ctx",
                    }
                },
            ), mock.patch.dict("os.environ", {"DEEP_REACH_OPENCLI_BIN": ""}):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = cmd_setup(argparse.Namespace())

        output = buffer.getvalue()
        self.assertEqual(code, 0)
        self.assertIn(
            f"Keys: optional — copy {template_path()} to {key_path}.", output
        )
        self.assertIn("Next: deep-reach doctor", output)


if __name__ == "__main__":
    unittest.main()
