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

    def test_load_tightens_keys_file_to_600(self):
        if os.name == "nt":
            self.skipTest("POSIX permissions only")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keys.yaml"
            path.write_text(
                "official:\n  github:\n    token: abc12345\n", encoding="utf-8"
            )
            os.chmod(path, 0o644)
            keys = Keys.load(path)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertIn("keys.yaml", str(keys.path))

    def test_yaml_error_does_not_echo_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keys.yaml"
            path.write_text(
                'official:\n  github:\n    token: "ghp_SECRETVALUE" [\n',
                encoding="utf-8",
            )
            with self.assertRaises(ReachError) as ctx:
                Keys.load(path)
            self.assertNotIn("ghp_SECRETVALUE", ctx.exception.message)
            self.assertIn("invalid YAML", ctx.exception.message)
            self.assertIn("line 3", ctx.exception.message)

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


class PackagedTemplateTest(unittest.TestCase):
    def test_keys_template_is_packaged(self):
        from importlib import resources

        template = resources.files("deep_reach.data").joinpath("keys.example.yaml")
        self.assertTrue(template.is_file())
        text = template.read_text(encoding="utf-8")
        self.assertIn("official:", text)
        self.assertIn("xueqiu:", text)
        self.assertIn("browser:", text)


if __name__ == "__main__":
    unittest.main()
