import argparse
import io
import json
import unittest
from contextlib import redirect_stdout

from deep_reach.cli import cmd_capabilities


class CapabilitiesOutputTest(unittest.TestCase):
    def test_json_shows_bsk_fallback_and_risk(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = cmd_capabilities(
                argparse.Namespace(channel="xiaohongshu", all=False, json=True)
            )
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        channel = payload["channels"][0]
        action = next(item for item in channel["actions"] if item["name"] == "search")
        self.assertTrue(action["ui_fallback"])
        self.assertEqual(action["risk"], "high")
        self.assertEqual(action["tiers"], [])

    def test_text_uses_bsk_tier_and_risk(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = cmd_capabilities(
                argparse.Namespace(channel="xiaohongshu", all=False, json=False)
            )
        self.assertEqual(code, 0)
        text = buffer.getvalue()
        self.assertIn("tiers=bsk", text)
        self.assertIn("risk=high", text)


if __name__ == "__main__":
    unittest.main()
