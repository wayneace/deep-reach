import argparse
import io
import json
import unittest
from contextlib import redirect_stdout
from unittest import mock

from deep_reach.cli import cmd_channels
from deep_reach.runtime.keys import Keys


class ChannelsJsonTest(unittest.TestCase):
    def test_json_has_effective_next_action(self):
        with mock.patch("deep_reach.cli._load_keys", return_value=Keys({})), mock.patch(
            "deep_reach.runtime.availability.shutil.which", return_value=None
        ):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = cmd_channels(argparse.Namespace(all=False, json=True))

        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        row = next(item for item in payload["channels"] if item["name"] == "weibo")
        self.assertEqual(row["status"], "needs_setup")
        self.assertIn("OpenCLI", row["effective_next_action"])
        self.assertIn("next_action", row)


if __name__ == "__main__":
    unittest.main()
