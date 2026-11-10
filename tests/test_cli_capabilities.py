import argparse
import io
import json
import unittest
from contextlib import redirect_stdout
from unittest import mock

from deep_reach.channels.base import Action, BackendSpec, Channel
from deep_reach.channels.registry import Registry
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

    def test_backend_only_risk_is_shown_in_text_and_json(self):
        channel = Channel(
            name="demo",
            category="test",
            status="ready",
            description="demo",
            actions=(
                Action(
                    "search",
                    backends=(BackendSpec("demo-api", "search", risk="high"),),
                ),
            ),
        )
        registry = Registry(channels={"demo": channel}, planned={})
        with mock.patch("deep_reach.cli.load_registry", return_value=registry):
            json_buffer = io.StringIO()
            with redirect_stdout(json_buffer):
                self.assertEqual(
                    cmd_capabilities(
                        argparse.Namespace(channel="demo", all=False, json=True)
                    ),
                    0,
                )
            text_buffer = io.StringIO()
            with redirect_stdout(text_buffer):
                self.assertEqual(
                    cmd_capabilities(
                        argparse.Namespace(channel="demo", all=False, json=False)
                    ),
                    0,
                )

        payload = json.loads(json_buffer.getvalue())
        self.assertEqual(payload["channels"][0]["actions"][0]["risk"], "high")
        action_line = next(
            line
            for line in text_buffer.getvalue().splitlines()
            if line.strip().startswith("search")
        )
        self.assertIn("risk=high", action_line)


if __name__ == "__main__":
    unittest.main()
