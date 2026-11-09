import os
import tempfile
import unittest
from pathlib import Path

from deep_reach.runtime.keys import Keys
from deep_reach.runtime.result import CONFIG_ERROR, ReachError


class KeysTest(unittest.TestCase):
    def setUp(self):
        self._env_backup = {
            "DEEP_REACH_OFFICIAL_GITHUB_TOKEN": os.environ.get(
                "DEEP_REACH_OFFICIAL_GITHUB_TOKEN"
            )
        }
        for key in self._env_backup:
            os.environ.pop(key, None)

    def tearDown(self):
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_missing_file_is_empty_and_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            keys = Keys.load(Path(tmp) / "missing.yaml")
            self.assertFalse(keys.has("official.github.token"))
            self.assertEqual(keys.status("official.github.token"), "missing")

    def test_reads_nested_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keys.yaml"
            path.write_text(
                "official:\n  github:\n    token: abc123\n", encoding="utf-8"
            )
            keys = Keys.load(path)
            self.assertTrue(keys.has("official.github.token"))
            self.assertEqual(keys.get("official.github.token"), "abc123")

    def test_placeholder_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keys.yaml"
            path.write_text(
                "official:\n  github:\n    token: changeme\n", encoding="utf-8"
            )
            keys = Keys.load(path)
            self.assertFalse(keys.has("official.github.token"))

    def test_env_override_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keys.yaml"
            path.write_text(
                "official:\n  github:\n    token: from-file\n", encoding="utf-8"
            )
            os.environ["DEEP_REACH_OFFICIAL_GITHUB_TOKEN"] = "from-env"
            keys = Keys.load(path)
            self.assertEqual(keys.get("official.github.token"), "from-env")

    def test_invalid_yaml_is_config_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keys.yaml"
            path.write_text("official: [unclosed\n", encoding="utf-8")
            with self.assertRaises(ReachError) as ctx:
                Keys.load(path)
            self.assertEqual(ctx.exception.code, CONFIG_ERROR)


if __name__ == "__main__":
    unittest.main()
