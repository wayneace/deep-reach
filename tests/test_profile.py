import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def test_set_context_restricts_keys_file_permissions(self):
        if os.name == "nt":
            self.skipTest("POSIX permissions only")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keys.yaml"
            os.environ["DEEP_REACH_KEYS_FILE"] = str(path)
            set_context("ctx-123")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_set_context_survives_chmod_failure(self):
        if os.name == "nt":
            self.skipTest("POSIX permissions only")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keys.yaml"
            os.environ["DEEP_REACH_KEYS_FILE"] = str(path)
            with mock.patch(
                "deep_reach.runtime.profile.os.chmod", side_effect=OSError("nope")
            ):
                set_context("ctx-123")
            self.assertIn(
                'opencli_profile: "ctx-123"',
                path.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
