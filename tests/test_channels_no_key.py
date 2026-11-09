import tempfile
import unittest
from pathlib import Path

from deep_reach.channels import load_channels
from deep_reach.runtime.dispatch import run_action
from deep_reach.runtime.keys import Keys


class NoKeyTest(unittest.TestCase):
    def test_registry_contains_core_channels(self):
        channels = load_channels()
        for name in ["youtube", "github", "v2ex", "bilibili", "xueqiu", "x", "reddit"]:
            self.assertIn(name, channels)

    def test_youtube_without_key_degrades_without_raising(self):
        channels = load_channels()
        env = run_action(
            channels["youtube"],
            "search",
            {"query": "desk", "limit": 5},
            keys=Keys({}),
        )
        self.assertFalse(env["ok"])
        self.assertIn(env["error"]["code"], {"KEY_MISSING", "NEED_SETUP", "SOURCE_DISABLED"})
        self.assertTrue(env["meta"]["attempts"])

    def test_bilibili_without_key_degrades_without_raising(self):
        channels = load_channels()
        env = run_action(
            channels["bilibili"],
            "search",
            {"query": "收纳", "limit": 5},
            keys=Keys({}),
        )
        self.assertFalse(env["ok"])
        self.assertIn(env["error"]["code"], {"NEED_SETUP", "SOURCE_DISABLED"})

    def test_xueqiu_without_key_degrades_without_raising(self):
        channels = load_channels()
        env = run_action(
            channels["xueqiu"],
            "quote",
            {"target": "SH600519"},
            keys=Keys({}),
        )
        self.assertFalse(env["ok"])
        self.assertIn(env["error"]["code"], {"NEED_SETUP", "SOURCE_DISABLED"})

    def test_key_missing_attempt_points_to_keys_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            key_path = Path(tmp) / "keys.yaml"
            env = run_action(
                load_channels()["ebay"],
                "search",
                {"query": "desk", "limit": 1},
                keys=Keys({}, path=key_path),
            )
        self.assertFalse(env["ok"])
        messages = [attempt.get("message", "") for attempt in env["meta"]["attempts"]]
        self.assertTrue(
            any(str(key_path) in message for message in messages),
            messages,
        )
        self.assertIn(str(key_path), env["error"]["hint"])
        self.assertIn("keys.example.yaml", env["error"]["hint"])


if __name__ == "__main__":
    unittest.main()
