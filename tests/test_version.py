import re
import unittest
from pathlib import Path

import deep_reach


class VersionTest(unittest.TestCase):
    def test_package_version_matches_pyproject(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'(?m)^version = "([^"]+)"', text)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), deep_reach.__version__)


if __name__ == "__main__":
    unittest.main()
