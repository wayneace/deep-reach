import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from deep_reach.runtime.skill import skill_dir, skill_status


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


if __name__ == "__main__":
    unittest.main()
