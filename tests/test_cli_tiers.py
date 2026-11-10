import argparse
import io
import json
import unittest
from contextlib import redirect_stdout

from deep_reach.cli import cmd_tiers


class TiersOutputTest(unittest.TestCase):
    def test_json_includes_p3_fallback_and_risk(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = cmd_tiers(argparse.Namespace(json=True))
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        p3 = payload["tiers"][-1]
        self.assertEqual(p3["id"], "p3")
        self.assertEqual(p3["kind"], "fallback")
        self.assertTrue(p3["manual"])
        self.assertIn("xiaohongshu", p3["channels"])
        self.assertIn("x", p3["channels"])
        row = next(item for item in payload["channels"] if item["name"] == "xiaohongshu")
        self.assertEqual(row["risk"], "high")
        self.assertIn("search", row["ui_fallback_actions"])

    def test_text_marks_p3_as_manual_and_bsk_actions(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = cmd_tiers(argparse.Namespace(json=False))
        self.assertEqual(code, 0)
        text = buffer.getvalue()
        self.assertIn("P3", text)
        self.assertIn("fallback / manual", text)
        self.assertIn("xiaohongshu", text)
        self.assertIn("search(bsk)", text)


if __name__ == "__main__":
    unittest.main()
