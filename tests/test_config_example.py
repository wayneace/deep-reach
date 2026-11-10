import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class ConfigExampleTest(unittest.TestCase):
    def test_bsk_and_risk_defaults_are_documented(self):
        data = yaml.safe_load(
            (ROOT / "deep_reach/data/keys.example.yaml").read_text(encoding="utf-8")
        )
        self.assertNotIn("bsk_profile", data["browser"])
        self.assertTrue(data["browser"]["bsk_guard"])
        self.assertTrue(data["risk"]["allow_high"])

    def test_template_has_no_keys_for_removed_channels(self):
        data = yaml.safe_load(
            (ROOT / "deep_reach/data/keys.example.yaml").read_text(encoding="utf-8")
        )
        for name in ("kipris", "euipo"):
            self.assertNotIn(name, data["official"])


if __name__ == "__main__":
    unittest.main()
