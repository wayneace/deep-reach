import argparse
import io
import json
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
                code = cmd_channels(argparse.Namespace(all=False, json=True))

        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        row = next(item for item in payload["channels"] if item["name"] == "weibo")
        self.assertEqual(row["status"], "needs_setup")
        self.assertIn("OpenCLI", row["effective_next_action"])
        self.assertIn("npm install -g @jackwener/opencli", row["effective_next_action"])
        self.assertIn("next_action", row)


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
                return_value={"opencli": {"connected": False}},
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
                return_value={"opencli": {"connected": True, "context_id": "ctx"}},
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
