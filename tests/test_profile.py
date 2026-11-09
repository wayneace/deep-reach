import os
import tempfile
import unittest
from pathlib import Path

from deep_reach.runtime.profile import set_context


class ProfileTest(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get("DEEP_REACH_KEYS_FILE")

    def tearDown(self):
        if self._old is None:
            os.environ.pop("DEEP_REACH_KEYS_FILE", None)
        else:
            os.environ["DEEP_REACH_KEYS_FILE"] = self._old

    def test_set_context_preserves_comments_and_other_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keys.yaml"
            path.write_text(
                "# keep this comment\n"
                "version: 1\n"
                "official:\n"
                "  github:\n"
                "    token: abc\n"
                "browser:\n"
                "  opencli_profile: \"auto\"  # old\n",
                encoding="utf-8",
            )
            os.environ["DEEP_REACH_KEYS_FILE"] = str(path)
            set_context("ctx-123")
            text = path.read_text(encoding="utf-8")
            self.assertIn("# keep this comment", text)
            self.assertIn("token: abc", text)
            self.assertIn('opencli_profile: "ctx-123"', text)


if __name__ == "__main__":
    unittest.main()
