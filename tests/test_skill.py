import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from deep_reach.runtime.result import ReachError
from deep_reach.runtime.skill import (
    apply_install,
    build_install_plan,
    skill_dir,
    skill_status,
)


def _install_copy(dest: Path) -> Path:
    target = dest / "deep-reach"
    shutil.copytree(skill_dir(), target)
    return target


def _set_version(target: Path, version: str) -> None:
    path = target / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    if re.search(r'(?m)^\s+version:\s*".*"$', text):
        text = re.sub(
            r'(?m)^(\s+version:\s*)".*"$',
            rf'\1"{version}"',
            text,
            count=1,
        )
    elif re.search(r"(?m)^metadata:\s*$", text):
        text = re.sub(
            r"(?m)^metadata:\s*$",
            f'metadata:\n  version: "{version}"',
            text,
            count=1,
        )
    else:
        text = text.replace(
            "\n---\n",
            f'\nmetadata:\n  version: "{version}"\n---\n',
            1,
        )
    path.write_text(text, encoding="utf-8")


class SkillStatusTest(unittest.TestCase):
    def test_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            status = skill_status(Path(tmp))
        self.assertEqual(status["state"], "missing")
        self.assertTrue(status["target"].endswith("/deep-reach"))

    def test_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            _install_copy(dest)
            status = skill_status(dest)
        self.assertEqual(status["state"], "current")
        self.assertEqual(status["installed_version"], status["packaged_version"])
        self.assertEqual(status["diff"], [])

    def test_outdated(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            target = _install_copy(dest)
            _set_version(target, "0.0.1")
            status = skill_status(dest)
        self.assertEqual(status["state"], "outdated")

    def test_ahead(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            target = _install_copy(dest)
            _set_version(target, "99.0.0")
            status = skill_status(dest)
        self.assertEqual(status["state"], "ahead")

    def test_modified_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            target = _install_copy(dest)
            (target / "SKILL.md").write_text("changed", encoding="utf-8")
            status = skill_status(dest)
        self.assertEqual(status["state"], "modified")
        self.assertIn("SKILL.md", status["diff"])

    def test_modified_extra_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            target = _install_copy(dest)
            (target / "extra.md").write_text("custom", encoding="utf-8")
            status = skill_status(dest)
        self.assertEqual(status["state"], "modified")
        self.assertIn("extra.md", status["diff"])

    def test_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            target = _install_copy(dest)
            (target / "references" / "capabilities.md").unlink()
            status = skill_status(dest)
        self.assertEqual(status["state"], "incomplete")
        self.assertIn("references/capabilities.md", status["diff"])

    def test_invalid_regular_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            (dest / "deep-reach").write_text("not a dir", encoding="utf-8")
            status = skill_status(dest)
        self.assertEqual(status["state"], "invalid")

    def test_symlink(self):
        if os.name == "nt":
            self.skipTest("symlinks need privileges on Windows")
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            real = dest / "real"
            real.mkdir()
            (dest / "deep-reach").symlink_to(real, target_is_directory=True)
            status = skill_status(dest)
        self.assertEqual(status["state"], "symlink")

    def test_legacy_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            (dest / "skill").mkdir()
            status = skill_status(dest)
        self.assertTrue(status["legacy"])
        self.assertEqual(status["state"], "missing")


class SkillInstallTest(unittest.TestCase):
    def test_plan_actions(self):
        cases = {
            "missing": "create",
            "current": "none",
            "ahead": "none",
            "outdated": "replace",
            "modified": "replace",
            "incomplete": "replace",
            "invalid": "refuse",
            "symlink": "refuse",
        }
        for state, action in cases.items():
            with self.subTest(state=state):
                with tempfile.TemporaryDirectory() as tmp:
                    dest = Path(tmp)
                    target = dest / "deep-reach"
                    if state == "missing":
                        pass
                    elif state == "invalid":
                        target.write_text("x", encoding="utf-8")
                    elif state == "symlink":
                        if os.name == "nt":
                            continue
                        real = dest / "real"
                        real.mkdir()
                        target.symlink_to(real, target_is_directory=True)
                    else:
                        _install_copy(dest)
                        if state == "current":
                            pass
                        elif state == "ahead":
                            _set_version(target, "99.0.0")
                        elif state == "outdated":
                            _set_version(target, "0.0.1")
                        elif state == "modified":
                            (target / "extra.md").write_text("x", encoding="utf-8")
                        elif state == "incomplete":
                            (target / "references" / "capabilities.md").unlink()
                    self.assertEqual(build_install_plan(dest)["action"], action)

    def test_apply_creates_named_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            plan = build_install_plan(dest)
            result = apply_install(plan)
            self.assertTrue((dest / "deep-reach" / "SKILL.md").is_file())
            self.assertFalse((dest / "skill").exists())
            self.assertTrue(result["written"])

    def test_apply_creates_missing_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "clients" / "cherry"
            apply_install(build_install_plan(dest))
            self.assertTrue((dest / "deep-reach" / "SKILL.md").is_file())

    def test_apply_preserves_siblings(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            (dest / "other").mkdir()
            (dest / "other" / "keep.txt").write_text("keep", encoding="utf-8")
            apply_install(build_install_plan(dest))
            self.assertEqual((dest / "other" / "keep.txt").read_text(), "keep")

    def test_apply_replaces_and_removes_stale_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            target = _install_copy(dest)
            _set_version(target, "0.0.1")
            (target / "extra.md").write_text("old", encoding="utf-8")
            apply_install(build_install_plan(dest))
            self.assertFalse((target / "extra.md").exists())
            self.assertEqual(skill_status(dest)["state"], "current")

    def test_apply_noop_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            _install_copy(dest)
            result = apply_install(build_install_plan(dest))
            self.assertFalse(result["written"])

    def test_apply_refuses_invalid_and_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            (dest / "deep-reach").write_text("x", encoding="utf-8")
            with self.assertRaises(ReachError):
                apply_install(build_install_plan(dest))
        if os.name != "nt":
            with tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp)
                real = dest / "real"
                real.mkdir()
                (dest / "deep-reach").symlink_to(real, target_is_directory=True)
                with self.assertRaises(ReachError):
                    apply_install(build_install_plan(dest))

    def test_copy_failure_leaves_target_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            target = _install_copy(dest)
            _set_version(target, "0.0.1")
            before = (target / "SKILL.md").read_text(encoding="utf-8")
            plan = build_install_plan(dest)
            with mock.patch(
                "deep_reach.runtime.skill.shutil.copytree",
                side_effect=OSError("disk full"),
            ):
                with self.assertRaises(OSError):
                    apply_install(plan)
            self.assertEqual((target / "SKILL.md").read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
