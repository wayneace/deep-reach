import os
import signal
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from deep_reach.runtime.profile import chrome_path, close, launch, set_context
from deep_reach.runtime.result import ReachError


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

    def test_set_context_rejects_auto(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["DEEP_REACH_KEYS_FILE"] = str(Path(tmp) / "keys.yaml")
            with self.assertRaises(ReachError):
                set_context("auto")

    def test_set_context_rejects_whitespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["DEEP_REACH_KEYS_FILE"] = str(Path(tmp) / "keys.yaml")
            with self.assertRaises(ReachError):
                set_context("ctx 123")

    def test_chrome_path_finds_macos_app_bundle(self):
        if sys.platform != "darwin":
            self.skipTest("macOS path")
        target = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        with mock.patch(
            "deep_reach.runtime.profile.Path.exists",
            autospec=True,
            side_effect=lambda path: str(path) == target,
        ), mock.patch("deep_reach.runtime.profile.shutil.which", return_value=None):
            self.assertEqual(chrome_path(), target)

    def test_profile_launch_uses_sanitized_env_and_private_dir(self):
        fake = mock.Mock(pid=1234)
        directory = Path(tempfile.mkdtemp())
        with mock.patch(
            "deep_reach.runtime.profile.chrome_path", return_value="/chrome"
        ), mock.patch(
            "deep_reach.runtime.profile.profile_dir", return_value=directory
        ), mock.patch(
            "deep_reach.runtime.profile.subprocess.Popen", return_value=fake
        ) as popen, mock.patch.dict(
            "os.environ", {"DEEP_REACH_OFFICIAL_GITHUB_TOKEN": "x"}
        ):
            result = launch()
        self.assertTrue(result["ok"])
        env = popen.call_args.kwargs["env"]
        self.assertNotIn("DEEP_REACH_OFFICIAL_GITHUB_TOKEN", env)
        self.assertEqual(directory.stat().st_mode & 0o777, 0o700)

    def test_profile_launch_can_open_about_blank(self):
        fake = mock.Mock(pid=1234)
        directory = Path(tempfile.mkdtemp())
        with mock.patch(
            "deep_reach.runtime.profile.chrome_path", return_value="/chrome"
        ), mock.patch(
            "deep_reach.runtime.profile.profile_dir", return_value=directory
        ), mock.patch(
            "deep_reach.runtime.profile.subprocess.Popen", return_value=fake
        ) as popen:
            launch(page="about:blank")
        self.assertEqual(popen.call_args.args[0][-1], "about:blank")

    def test_close_kills_only_the_dedicated_profile(self):
        if os.name == "nt":
            self.skipTest("POSIX ps parsing only")
        directory = Path("/tmp/deep-reach-profile")
        output = (
            f" 123 /chrome --user-data-dir={directory} --profile-directory=Default\n"
            " 456 /chrome --user-data-dir=/tmp/other\n"
            f" 789 /bin/zsh -c echo --user-data-dir={directory}\n"
        )
        with mock.patch(
            "deep_reach.runtime.profile.profile_dir", return_value=directory
        ), mock.patch(
            "deep_reach.runtime.profile.subprocess.run",
            return_value=mock.Mock(stdout=output),
        ), mock.patch(
            "deep_reach.runtime.profile.os.kill"
        ) as kill:
            result = close()
        self.assertEqual(result["closed"], [123])
        kill.assert_called_once_with(123, signal.SIGTERM)

    def test_set_context_preserves_symlink_target(self):
        if os.name == "nt":
            self.skipTest("symlinks need privileges on Windows")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "dotfiles-keys.yaml"
            target.write_text(
                'version: 1\nbrowser:\n  opencli_profile: ""\n', encoding="utf-8"
            )
            link = Path(tmp) / "keys.yaml"
            link.symlink_to(target)
            os.environ["DEEP_REACH_KEYS_FILE"] = str(link)
            set_context("ctx-1234")
            self.assertTrue(link.is_symlink())
            self.assertIn(
                'opencli_profile: "ctx-1234"',
                target.read_text(encoding="utf-8"),
            )

    def test_set_context_survives_chmod_failure(self):
        if os.name == "nt":
            self.skipTest("POSIX permissions only")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keys.yaml"
            os.environ["DEEP_REACH_KEYS_FILE"] = str(path)
            with mock.patch(
                "deep_reach.runtime.secure_paths.os.chmod",
                side_effect=OSError("nope"),
            ):
                set_context("ctx-123")
            self.assertIn(
                'opencli_profile: "ctx-123"',
                path.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
