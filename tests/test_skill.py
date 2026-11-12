import io
import json
import os
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from deep_reach.cli import main
from deep_reach.runtime.result import BAD_INPUT, CONFIG_ERROR, ReachError
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
        self.assertEqual(Path(status["target"]).name, "deep-reach")

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

    def test_ahead_with_missing_file_is_still_ahead(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            target = _install_copy(dest)
            _set_version(target, "99.0.0")
            (target / "references" / "capabilities.md").unlink()
            status = skill_status(dest)
            plan = build_install_plan(dest)
        self.assertEqual(status["state"], "ahead")
        self.assertEqual(plan["action"], "none")

    def test_status_dest_is_file_raises_bad_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "skills"
            dest.write_text("not a directory", encoding="utf-8")
            with self.assertRaises(ReachError) as ctx:
                skill_status(dest)
        self.assertEqual(ctx.exception.code, BAD_INPUT)

    def test_status_unreadable_skill_raises_reach_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            _install_copy(dest)
            with mock.patch(
                "pathlib.Path.read_text",
                side_effect=PermissionError("denied"),
            ):
                with self.assertRaises(ReachError) as ctx:
                    skill_status(dest)
        self.assertEqual(ctx.exception.code, CONFIG_ERROR)

    def test_scalar_frontmatter_is_modified(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            target = _install_copy(dest)
            (target / "SKILL.md").write_text(
                "---\njust a string\n---\n", encoding="utf-8"
            )
            status = skill_status(dest)
        self.assertEqual(status["state"], "modified")

    def test_non_dict_metadata_is_modified(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            target = _install_copy(dest)
            (target / "SKILL.md").write_text(
                "---\nmetadata:\n  - a\n---\n", encoding="utf-8"
            )
            status = skill_status(dest)
        self.assertEqual(status["state"], "modified")


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
                with self.assertRaises(ReachError) as ctx:
                    apply_install(plan)
            self.assertEqual(ctx.exception.code, CONFIG_ERROR)
            self.assertEqual((target / "SKILL.md").read_text(encoding="utf-8"), before)

    def test_apply_wraps_mkdtemp_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            with mock.patch(
                "deep_reach.runtime.skill.tempfile.mkdtemp",
                side_effect=PermissionError("denied"),
            ):
                with self.assertRaises(ReachError) as ctx:
                    apply_install(build_install_plan(dest))
            self.assertEqual(ctx.exception.code, CONFIG_ERROR)


def _run(*args: str) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        code = main(list(args))
    return code, out.getvalue()


class SkillCliTest(unittest.TestCase):
    def test_path_text(self):
        code, out = _run("skill", "path")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), str(skill_dir()))

    def test_path_json(self):
        code, out = _run("skill", "path", "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data["ok"])
        self.assertEqual(Path(data["path"]).name, "skill")

    def test_show_text(self):
        code, out = _run("skill", "show")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("---"))

    def test_show_json(self):
        code, out = _run("skill", "show", "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertIn("name: deep-reach", data["content"])

    def test_status_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = _run("skill", "status", "--dest", tmp, "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["state"], "missing")

    def test_status_dest_file_returns_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "skills"
            dest.write_text("not a directory", encoding="utf-8")
            code, _ = _run("skill", "status", "--dest", str(dest))
        self.assertEqual(code, 2)

    def test_install_dest_file_returns_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "skills"
            dest.write_text("not a directory", encoding="utf-8")
            code, _ = _run("skill", "install", "--dest", str(dest), "--yes")
        self.assertEqual(code, 2)

    def test_install_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = _run("skill", "install", "--dest", tmp, "--dry-run")
            self.assertEqual(code, 0)
            self.assertFalse((Path(tmp) / "deep-reach").exists())

    def test_install_non_interactive_requires_yes(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch(
            "sys.stdin.isatty", return_value=False
        ):
            code, _ = _run("skill", "install", "--dest", tmp)
            self.assertEqual(code, 2)
            self.assertFalse((Path(tmp) / "deep-reach").exists())

    def test_install_json_non_interactive_returns_error_envelope(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch(
            "sys.stdin.isatty", return_value=False
        ):
            code, out = _run("skill", "install", "--dest", tmp, "--json")
        self.assertEqual(code, 2)
        data = json.loads(out)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"]["code"], BAD_INPUT)

    def test_install_json_refuse_returns_error_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            (dest / "deep-reach").write_text("x", encoding="utf-8")
            code, out = _run("skill", "install", "--dest", tmp, "--json", "--yes")
        self.assertEqual(code, 2)
        data = json.loads(out)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"]["code"], BAD_INPUT)

    def test_install_yes(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "skill"
            legacy.mkdir()
            code, _ = _run("skill", "install", "--dest", tmp, "--yes")
            self.assertEqual(code, 0)
            self.assertTrue((Path(tmp) / "deep-reach" / "SKILL.md").is_file())
            self.assertTrue(legacy.is_dir())

    def test_install_declined(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch(
            "sys.stdin.isatty", return_value=True
        ), mock.patch("builtins.input", return_value="n"):
            code, _ = _run("skill", "install", "--dest", tmp)
            self.assertEqual(code, 2)
            self.assertFalse((Path(tmp) / "deep-reach").exists())

    def test_install_ahead_does_not_downgrade(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = _install_copy(Path(tmp))
            _set_version(target, "99.0.0")
            code, out = _run("skill", "install", "--dest", tmp, "--yes")
            self.assertEqual(code, 0)
            self.assertIn("not downgrading", out.lower())
            self.assertIn("99.0.0", (target / "SKILL.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
