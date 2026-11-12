import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from deep_reach.runtime.keys import Keys, template_path
from deep_reach.runtime.result import CONFIG_ERROR, ReachError, clear_secrets
from deep_reach.runtime.setup import (
    apply_setup,
    build_setup_plan,
    format_setup_plan,
    format_setup_summary,
)


class SetupPlanTest(unittest.TestCase):
    def setUp(self):
        clear_secrets()

    def tearDown(self):
        clear_secrets()

    def test_plan_creates_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            path = home / ".deep-reach" / "keys.yaml"
            with mock.patch("deep_reach.runtime.setup.Path.home", return_value=home):
                plan = build_setup_plan(Keys({}, path=path), opencli_version="")
                text = format_setup_plan(plan)
            self.assertTrue(plan.create_dir)
            self.assertTrue(plan.create_file)
            self.assertIn("~/.deep-reach/keys.yaml", text)
            self.assertIn("cli_install", text)
            self.assertIn("npm install -g @jackwener/opencli", text)

    def test_plan_keeps_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keys.yaml"
            path.write_text("version: 1\n", encoding="utf-8")
            plan = build_setup_plan(Keys.load(path), opencli_version="2.0.3")
            self.assertFalse(plan.create_file)
            self.assertIn("keep", format_setup_plan(plan).lower())

    def test_plan_describes_symlink_before_existing_target(self):
        if os.name == "nt":
            self.skipTest("symlink setup is POSIX-only in tests")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target.yaml"
            target.write_text("version: 1\n", encoding="utf-8")
            link = Path(tmp) / "keys.yaml"
            link.symlink_to(target)
            plan = build_setup_plan(Keys.load(link), opencli_version="")
            text = format_setup_plan(plan)
        self.assertIn("symlink", text)
        self.assertNotIn("already exists", text)

    def test_plan_uses_plain_environment_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keys.yaml"
            plan = build_setup_plan(Keys({}, path=path), opencli_version="")
            text = format_setup_plan(plan)
        self.assertIn("Plain-environment install:", text)
        self.assertNotIn("Recommended:", text)

    def test_detect_opencli_version_uses_shared_env_constant(self):
        from deep_reach.runtime import setup as setup_module
        from deep_reach.runtime.availability import OPENCLI_BIN_ENV

        self.assertIs(setup_module.OPENCLI_BIN_ENV, OPENCLI_BIN_ENV)


class SetupApplyTest(unittest.TestCase):
    def setUp(self):
        clear_secrets()

    def tearDown(self):
        clear_secrets()

    def test_apply_creates_private_file(self):
        if os.name == "nt":
            self.skipTest("POSIX permissions only")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            path = home / ".deep-reach" / "keys.yaml"
            with mock.patch("deep_reach.runtime.setup.Path.home", return_value=home):
                plan = build_setup_plan(Keys({}, path=path), opencli_version="")
                results = apply_setup(plan)
            self.assertEqual(path.read_bytes(), template_path().read_bytes())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual([r.status for r in results], ["created", "created"])

    def test_apply_does_not_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keys.yaml"
            path.write_text("version: 1\nofficial:\n  github:\n    token: keep-me\n")
            plan = build_setup_plan(Keys.load(path), opencli_version="")
            apply_setup(plan)
            self.assertIn("keep-me", path.read_text(encoding="utf-8"))

    def test_apply_skips_symlink(self):
        if os.name == "nt":
            self.skipTest("symlink setup is POSIX-only in tests")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target.yaml"
            target.write_text("version: 1\n", encoding="utf-8")
            link = Path(tmp) / "keys.yaml"
            link.symlink_to(target)
            plan = build_setup_plan(Keys.load(link), opencli_version="")
            results = apply_setup(plan)
            self.assertEqual(target.read_text(encoding="utf-8"), "version: 1\n")
            self.assertEqual(results[-1].status, "skipped")

    def test_apply_refuses_to_overwrite_file_created_after_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keys.yaml"
            plan = build_setup_plan(Keys({}, path=path), opencli_version="")
            path.write_text("created-by-someone-else\n", encoding="utf-8")
            with self.assertRaises(ReachError) as ctx:
                apply_setup(plan)
            self.assertEqual(ctx.exception.code, CONFIG_ERROR)
            self.assertEqual(
                path.read_text(encoding="utf-8"), "created-by-someone-else\n"
            )

    def test_apply_tightens_existing_directory_without_deleting(self):
        if os.name == "nt":
            self.skipTest("POSIX permissions only")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            parent = home / ".deep-reach"
            parent.mkdir(mode=0o755, parents=True)
            sentinel = parent / "keep.txt"
            sentinel.write_text("keep", encoding="utf-8")
            path = parent / "keys.yaml"
            with mock.patch("deep_reach.runtime.setup.Path.home", return_value=home):
                plan = build_setup_plan(Keys({}, path=path), opencli_version="")
                apply_setup(plan)
            self.assertEqual(parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_apply_creates_private_custom_parent(self):
        if os.name == "nt":
            self.skipTest("POSIX permissions only")
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / "custom" / "deep-reach"
            path = parent / "keys.yaml"
            plan = build_setup_plan(Keys({}, path=path), opencli_version="")
            self.assertTrue(plan.create_dir)
            apply_setup(plan)
            self.assertEqual(parent.stat().st_mode & 0o777, 0o700)


class SetupSummaryTest(unittest.TestCase):
    def setUp(self):
        clear_secrets()

    def tearDown(self):
        clear_secrets()

    def test_summary_lists_empty_keys_and_extension_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keys.yaml"
            plan = build_setup_plan(
                Keys({"official": {"github": {"token": "secret-value"}}}, path=path),
                opencli_version="",
            )
            text = format_setup_summary(plan, [], plan.keys)
        self.assertIn("official.youtube.api_key", text)
        self.assertNotIn("official.github.token", text)
        self.assertNotIn("secret-value", text)
        self.assertIn("chromewebstore.google.com", text)

    def test_summary_mentions_skill_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keys.yaml"
            plan = build_setup_plan(Keys({}, path=path), opencli_version="")
            text = format_setup_summary(plan, [], plan.keys)
        self.assertIn("Skill:", text)
        self.assertIn("marketplace", text)
        self.assertIn("deep-reach skill install --dest", text)


if __name__ == "__main__":
    unittest.main()
