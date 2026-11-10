import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class ConfigExampleTest(unittest.TestCase):
    def test_bsk_and_risk_defaults_are_documented(self):
        data = yaml.safe_load(
            (ROOT / "deep_reach/data/keys.example.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(data["browser"]["bsk_profile"], "main")
        self.assertTrue(data["browser"]["bsk_guard"])
        self.assertTrue(data["risk"]["allow_high"])


if __name__ == "__main__":
    unittest.main()
