# Deep-Reach Skill 入口与触发优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Deep-Reach skill 在正确的时机触发，并提供可安装、可检查、可更新的 `deep-reach skill` 入口，安装目录名为 `deep-reach`。

**Architecture:** 把 canonical skill 移入 `deep_reach/data/skill/`，随 wheel 打包；新增 `deep_reach/runtime/skill.py` 负责状态比较和原子安装；`cli.py` 注册 `skill path|show|status|install`；重写 SKILL.md 的 description、路由、命令分组和错误表；版本升到 0.14.0。

**Tech Stack:** Python 3.10+、PyYAML、setuptools、pytest、ruff、importlib.resources。

**Spec:** `docs/superpowers/specs/2026-11-12-skill-entrypoint-design.md`

## Global Constraints

- Python 3.10+；不新增运行时依赖。
- 所有 `skill` 子命令默认文本输出，`--json` 输出机器可读 JSON。
- `status` 是可读诊断命令：missing/invalid/symlink/incomplete/ahead/outdated/modified/current 都返回 0；参数错误或 `ReachError` 返回 2。
- `install` 成功/无需更新返回 0；用户拒绝或非交互缺少 `--yes` 返回 2。
- `install` 目标固定为 `<dest>/deep-reach`，绝不写 `<dest>/skill`。
- 不删除用户已有的 `<dest>/skill`；只提示 legacy。
- 不降级：安装版本高于包版本时 `ahead`，install no-op。
- 安装目录中多出的文件算 `modified`，覆盖前必须确认。
- skill 示例统一用 `deep-reach`；不出现完整字面量 `uv run deep-reach`。
- skill metadata 的版本必须等于 `deep_reach.__version__`。
- 未经用户同意不合并、不推送、不删除用户数据。

## Review Focus

- `<dest>` 不存在或父目录不存在：install 应创建父目录，不应失败。
- `<dest>/deep-reach` 是 symlink 或普通文件：必须拒绝写入，避免写到目录外。
- 用户安装目录里有自定义文件：status 应为 `modified`，install 必须先确认，替换后自定义文件被移除。
- 已安装版本高于 CLI：`ahead`，install 不降级。
- `<dest>/skill` 旧目录存在：只提示 legacy，不删除。
- 非交互环境没有 `--yes`：不产生任何写入。

---

## Task 1: Move skill into package data

**Files:**
- Move: `skill/SKILL.md` → `deep_reach/data/skill/SKILL.md`
- Move: `skill/references/capabilities.md` → `deep_reach/data/skill/references/capabilities.md`
- Modify: `MANIFEST.in`
- Modify: `pyproject.toml:50-51`
- Modify: `tests/test_docs_contract.py:5-14`
- Modify: `README.md:263-265`（目录树）

**Interfaces:**
- Produces: packaged skill at `deep_reach/data/skill/` with `SKILL.md` and `references/capabilities.md`.
- Later tasks locate it via `importlib.resources.files("deep_reach.data").joinpath("skill")`.

- [ ] **Step 1: Move the skill tree**

```bash
mkdir -p deep_reach/data/skill/references
git mv skill/SKILL.md deep_reach/data/skill/SKILL.md
git mv skill/references/capabilities.md deep_reach/data/skill/references/capabilities.md
rmdir skill/references skill
```

在移动后的 `SKILL.md` frontmatter 末尾加入当前版本，保证 Task 2 的
`test_current` 能读到版本：

```yaml
metadata:
  homepage: https://github.com/wayneace/deep-reach
  version: "0.13.0"
```

- [ ] **Step 2: Update packaging**

`MANIFEST.in` 改为：

```text
include LICENSE
include NOTICE
include README.md
include CHANGELOG.md
include SECURITY.md
include CONTRIBUTING.md
recursive-include deep_reach/data *.yaml *.md
recursive-include tests *.py
recursive-include scripts *.py
```

`pyproject.toml` 的 `package-data` 改为：

```toml
[tool.setuptools.package-data]
"deep_reach.data" = ["*.yaml", "skill/*.md", "skill/references/*.md"]
```

- [ ] **Step 3: Update docs contract paths and README tree**

`tests/test_docs_contract.py` 的 `DOCS` 改为：

```python
DOCS = (
    "README.md",
    "PRODUCT.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "pyproject.toml",
    "deep_reach/data/skill/SKILL.md",
    "deep_reach/data/skill/references/capabilities.md",
    "deep_reach/product.py",
)
```

`README.md` 目录树改为：

```text
deep_reach/
  ...
  data/
    channels.yaml       # 精选渠道 + backend tier（随 wheel 打包）
    keys.example.yaml   # key 模板（随 wheel 打包）
    skill/              # agent skill（随 wheel 打包）
```

- [ ] **Step 4: Run focused tests**

Run: `uv run pytest tests/test_docs_contract.py -q`  
Expected: PASS.

- [ ] **Step 5: Verify the wheel contains the skill**

Run:

```bash
uv build --wheel
WHEEL=$(ls -t dist/deep_reach-*.whl | head -1)
unzip -l "$WHEEL" | grep 'deep_reach/data/skill'
```

Expected: `SKILL.md` and `references/capabilities.md` present.

- [ ] **Step 6: Commit**

```bash
git add deep_reach/data/skill MANIFEST.in pyproject.toml tests/test_docs_contract.py README.md
git commit -m "refactor: package the agent skill with deep-reach"
```

---

## Task 2: Skill status and comparison

**Files:**
- Create: `deep_reach/runtime/skill.py`
- Create: `tests/test_skill.py`

**Interfaces:**
- Produces:
  - `skill_dir() -> Path`：包内 skill 目录。
  - `packaged_version() -> str`：`deep_reach.__version__`。
  - `installed_skill_dir(dest: Path) -> Path`：`Path(dest).expanduser() / "deep-reach"`。
  - `read_skill_version(root: Path) -> Optional[str]`：读 `SKILL.md` frontmatter 的 `metadata.version`。
  - `skill_status(dest: Path) -> dict`，键为 `ok`, `target`, `state`, `installed_version`, `packaged_version`, `legacy`, `diff`, `diff_count`。
- State: `missing` / `invalid` / `symlink` / `incomplete` / `ahead` / `outdated` / `modified` / `current`。

- [ ] **Step 1: Write the failing status tests**

`tests/test_skill.py` 先写这些测试：

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_skill.py -q`  
Expected: FAIL with `ModuleNotFoundError: No module named 'deep_reach.runtime.skill'`.

- [ ] **Step 3: Implement the status module**

在 `deep_reach/runtime/skill.py` 实现：

```python
from __future__ import annotations

import hashlib
import re
from importlib import resources
from pathlib import Path
from typing import Optional

import yaml

SKILL_NAME = "deep-reach"
SKILL_PACKAGE = "deep_reach.data"
SKILL_REL = "skill"


def skill_dir() -> Path:
    return Path(str(resources.files(SKILL_PACKAGE).joinpath(SKILL_REL)))


def packaged_version() -> str:
    from .. import __version__

    return __version__


def installed_skill_dir(dest: Path) -> Path:
    return Path(dest).expanduser() / SKILL_NAME


def read_skill_version(root: Path) -> Optional[str]:
    path = root / "SKILL.md"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    front, sep, _ = text[4:].partition("\n---")
    if not sep:
        return None
    try:
        data = yaml.safe_load(front) or {}
    except yaml.YAMLError:
        return None
    metadata = data.get("metadata") or {}
    version = metadata.get("version")
    return str(version).strip() if version else None


def _version_tuple(text: Optional[str]) -> Optional[tuple[int, int, int]]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", text or "")
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def _skill_files(root: Path) -> dict[str, str]:
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            rel = path.relative_to(root).as_posix()
            files[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def _diff_files(expected: dict[str, str], actual: dict[str, str]) -> list[str]:
    keys = sorted(set(expected) | set(actual))
    return [key for key in keys if expected.get(key) != actual.get(key)]


def skill_status(dest: Path) -> dict:
    target = installed_skill_dir(dest)
    legacy = Path(dest).expanduser() / "skill"
    packaged = skill_dir()
    packaged_files = _skill_files(packaged)
    version = packaged_version()
    result = {
        "ok": True,
        "target": str(target),
        "state": "missing",
        "installed_version": None,
        "packaged_version": version,
        "legacy": legacy.exists() or legacy.is_symlink(),
        "diff": [],
        "diff_count": 0,
    }
    if target.is_symlink():
        result["state"] = "symlink"
        return result
    if not target.exists():
        return result
    if not target.is_dir():
        result["state"] = "invalid"
        return result
    installed_files = _skill_files(target)
    missing = sorted(set(packaged_files) - set(installed_files))
    if "SKILL.md" not in installed_files or missing:
        result["state"] = "incomplete"
        result["diff"] = missing[:20]
        result["diff_count"] = len(missing)
        return result
    installed_version = read_skill_version(target)
    result["installed_version"] = installed_version
    installed_tuple = _version_tuple(installed_version)
    packaged_tuple = _version_tuple(version)
    if installed_tuple is None or packaged_tuple is None:
        result["state"] = "modified"
        result["diff"] = _diff_files(packaged_files, installed_files)[:20]
        result["diff_count"] = len(_diff_files(packaged_files, installed_files))
        return result
    if installed_tuple > packaged_tuple:
        result["state"] = "ahead"
        return result
    if installed_tuple < packaged_tuple:
        diff = _diff_files(packaged_files, installed_files)
        result["state"] = "outdated"
        result["diff"] = diff[:20]
        result["diff_count"] = len(diff)
        return result
    diff = _diff_files(packaged_files, installed_files)
    result["state"] = "current" if not diff else "modified"
    result["diff"] = diff[:20]
    result["diff_count"] = len(diff)
    return result
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_skill.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deep_reach/runtime/skill.py tests/test_skill.py
git commit -m "feat: compare installed and packaged skills"
```

---

## Task 3: Install plan and atomic apply

**Files:**
- Modify: `deep_reach/runtime/skill.py`
- Modify: `tests/test_skill.py`

**Interfaces:**
- Produces:
  - `build_install_plan(dest: Path) -> dict`：status + `action`（`create` / `replace` / `none` / `refuse`）。
  - `apply_install(plan: dict) -> dict`：`{ok, target, state, written, files}`；`refuse` 抛 `ReachError(BAD_INPUT)`。
  - `format_skill_status(status: dict) -> str`
  - `format_install_plan(plan: dict) -> str`
  - `format_install_result(result: dict) -> str`

- [ ] **Step 1: Write the failing install tests**

在 `tests/test_skill.py` 追加：

```python
from unittest import mock

from deep_reach.runtime.result import ReachError
from deep_reach.runtime.skill import (
    apply_install,
    build_install_plan,
)


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
            before = (target / "SKILL.md").read_text(encoding="utf-8")
            plan = build_install_plan(dest)
            with mock.patch(
                "deep_reach.runtime.skill.shutil.copytree",
                side_effect=OSError("disk full"),
            ):
                with self.assertRaises(OSError):
                    apply_install(plan)
            self.assertEqual((target / "SKILL.md").read_text(encoding="utf-8"), before)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_skill.py -q`  
Expected: FAIL with `ImportError` for `build_install_plan`.

- [ ] **Step 3: Implement plan/apply**

在 `deep_reach/runtime/skill.py` 追加：

```python
import os
import shutil
import tempfile

from .result import BAD_INPUT, ReachError


def build_install_plan(dest: Path) -> dict:
    status = skill_status(dest)
    actions = {
        "missing": "create",
        "current": "none",
        "ahead": "none",
        "outdated": "replace",
        "modified": "replace",
        "incomplete": "replace",
        "invalid": "refuse",
        "symlink": "refuse",
    }
    return {**status, "action": actions[status["state"]]}


def apply_install(plan: dict) -> dict:
    target = Path(plan["target"])
    if plan["action"] == "none":
        return {
            "ok": True,
            "target": str(target),
            "state": plan["state"],
            "written": False,
            "files": [],
        }
    if plan["action"] == "refuse":
        raise ReachError(
            BAD_INPUT,
            f"refusing to install over {plan['state']} target: {target}",
        )
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".deep-reach-skill-", dir=str(parent)))
    backup = parent / f".deep-reach-skill-backup-{os.getpid()}"
    try:
        staged = temp / "skill"
        shutil.copytree(skill_dir(), staged)
        if target.exists() or target.is_symlink():
            if backup.exists():
                shutil.rmtree(backup)
            os.replace(target, backup)
        try:
            os.replace(staged, target)
        except Exception:
            if backup.exists():
                os.replace(backup, target)
            raise
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    return {
        "ok": True,
        "target": str(target),
        "state": "current",
        "written": True,
        "files": sorted(_skill_files(target)),
    }


def format_skill_status(status: dict) -> str:
    lines = [
        f"skill: {status['target']}",
        f"state: {status['state']}",
        f"installed: {status['installed_version'] or '-'}",
        f"packaged: {status['packaged_version']}",
    ]
    if status["legacy"]:
        lines.append("legacy: <dest>/skill exists; not removed")
    if status["diff"]:
        lines.append("diff: " + ", ".join(status["diff"]))
    return "\n".join(lines)


def format_install_plan(plan: dict) -> str:
    lines = [
        "Deep-Reach skill install",
        f"  target: {plan['target']}",
        f"  state: {plan['state']}",
        f"  action: {plan['action']}",
    ]
    if plan["legacy"]:
        lines.append("  legacy: <dest>/skill exists; not removed")
    return "\n".join(lines)


def format_install_result(result: dict) -> str:
    if not result["written"]:
        if result["state"] == "ahead":
            return (
                "installed skill is newer than this CLI; "
                f"not downgrading: {result['target']}"
            )
        return f"skill already current: {result['target']}"
    return f"installed skill: {result['target']} ({len(result['files'])} files)"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_skill.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deep_reach/runtime/skill.py tests/test_skill.py
git commit -m "feat: install the skill atomically"
```

---

## Task 4: CLI `skill` subcommands

**Files:**
- Modify: `deep_reach/cli.py`
- Modify: `tests/test_skill.py`

**Interfaces:**
- Produces:
  - `cmd_skill(args: argparse.Namespace) -> int`
  - CLI: `deep-reach skill path [--json]`
  - CLI: `deep-reach skill show [--json]`
  - CLI: `deep-reach skill status --dest <dir> [--json]`
  - CLI: `deep-reach skill install --dest <dir> [--dry-run] [--yes] [--json]`

- [ ] **Step 1: Write the failing CLI tests**

在 `tests/test_skill.py` 追加：

```python
import io
import json
from contextlib import redirect_stdout

from deep_reach.cli import main


def _run(*args: str) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        code = main(list(args))
    return code, out.getvalue()


class SkillCliTest(unittest.TestCase):
    def test_path_text(self):
        code, out = _run("skill", "path")
        self.assertEqual(code, 0)
        self.assertIn("deep-reach", out)

    def test_path_json(self):
        code, out = _run("skill", "path", "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data["ok"])
        self.assertTrue(data["path"].endswith("skill"))

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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_skill.py -q`  
Expected: FAIL because `skill` is not a valid command.

- [ ] **Step 3: Implement `cmd_skill` and parser**

`deep_reach/cli.py`：

- 导入：

```python
from .runtime.skill import (
    apply_install,
    build_install_plan,
    format_install_plan,
    format_install_result,
    format_skill_status,
    packaged_version,
    skill_dir,
    skill_status,
)
```

- 增加：

```python
def cmd_skill(args: argparse.Namespace) -> int:
    command = getattr(args, "skill_command", None)
    if command == "path":
        payload = {"ok": True, "path": str(skill_dir()), "version": packaged_version()}
        if args.json:
            _print_json(payload)
        else:
            print(payload["path"])
        return 0
    if command == "show":
        path = skill_dir() / "SKILL.md"
        content = path.read_text(encoding="utf-8")
        if args.json:
            _print_json({"ok": True, "path": str(path), "content": content})
        else:
            print(content, end="" if content.endswith("\n") else "\n")
        return 0
    if command == "status":
        status = skill_status(Path(args.dest))
        if args.json:
            _print_json(status)
        else:
            print(format_skill_status(status))
        return 0
    if command == "install":
        plan = build_install_plan(Path(args.dest))
        if args.json and (args.dry_run or plan["action"] in {"none", "refuse"}):
            _print_json(plan)
        else:
            print(format_install_plan(plan))
        if args.dry_run:
            return 0
        if plan["action"] == "none":
            return 0
        if plan["action"] == "refuse":
            raise ReachError(BAD_INPUT, f"refusing to install over {plan['state']} target")
        if not args.yes:
            if not sys.stdin.isatty():
                print("confirmation required; rerun with --yes", file=sys.stderr)
                return 2
            answer = input("Proceed with skill install? [y/N] ")
            if answer.strip().lower() not in {"y", "yes"}:
                return 2
        result = apply_install(plan)
        if args.json:
            _print_json(result)
        else:
            print(format_install_result(result))
        return 0
    print("usage: deep-reach skill path|show|status|install", file=sys.stderr)
    return 2
```

- parser 在 `setup` 之后加入：

```python
skill = sub.add_parser("skill", help="install and inspect the agent skill")
skill_sub = skill.add_subparsers(dest="skill_command")
skill.set_defaults(func=cmd_skill)

s_path = skill_sub.add_parser("path")
s_path.add_argument("--json", action="store_true")
s_path.set_defaults(func=cmd_skill)

s_show = skill_sub.add_parser("show")
s_show.add_argument("--json", action="store_true")
s_show.set_defaults(func=cmd_skill)

s_status = skill_sub.add_parser("status")
s_status.add_argument("--dest", required=True)
s_status.add_argument("--json", action="store_true")
s_status.set_defaults(func=cmd_skill)

s_install = skill_sub.add_parser("install")
s_install.add_argument("--dest", required=True)
s_install.add_argument("--dry-run", action="store_true")
s_install.add_argument("--yes", action="store_true")
s_install.add_argument("--json", action="store_true")
s_install.set_defaults(func=cmd_skill)
```

- 导入 `BAD_INPUT`：

```python
from .runtime.result import BAD_INPUT, ReachError, dump, redact_text
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_skill.py -q`  
Expected: PASS.

- [ ] **Step 5: Manual smoke**

Run:

```bash
uv run deep-reach skill path
uv run deep-reach skill show | head -20
uv run deep-reach skill status --dest /tmp/deep-reach-skill-test
```

Expected: path prints the packaged directory; show prints frontmatter; status prints `state: missing`.

- [ ] **Step 6: Commit**

```bash
git add deep_reach/cli.py tests/test_skill.py
git commit -m "feat: add deep-reach skill commands"
```

---

## Task 5: Rewrite SKILL.md triggering and routing

**Files:**
- Modify: `deep_reach/data/skill/SKILL.md`
- Modify: `tests/test_docs_contract.py`

**Interfaces:**
- Produces: skill description/metadata that the docs contract tests pin.
- Consumes: packaged skill path from Task 1.

- [ ] **Step 1: Write the failing docs contract tests**

在 `tests/test_docs_contract.py` 增加：

```python
from deep_reach import __version__

SKILL = ROOT / "deep_reach" / "data" / "skill" / "SKILL.md"


class SkillContractTest(unittest.TestCase):
    def setUp(self):
        self.text = SKILL.read_text(encoding="utf-8")

    def test_skill_version_matches_package(self):
        self.assertIn(f'version: "{__version__}"', self.text)

    def test_skill_routes_instead_of_always_calling(self):
        for phrase in (
            "选择路由",
            "普通公开网页优先用内置工具",
            "粘贴",
            "NEED_UI",
            "deep-reach bsk",
            "channels --json",
            "doctor --json",
        ):
            self.assertIn(phrase, self.text)

    def test_skill_error_table_is_complete(self):
        for code in (
            "UPSTREAM_BROKEN",
            "QUOTA_EXHAUSTED",
            "CONFIG_ERROR",
        ):
            self.assertIn(code, self.text)

    def test_skill_uses_installed_cli(self):
        self.assertNotIn("uv run deep-reach", self.text)

    def test_skill_does_not_mention_removed_roadmap(self):
        self.assertNotIn("roadmap", self.text.lower())

    def test_skill_documents_install_command(self):
        self.assertIn("deep-reach skill install", self.text)
```

注意：`paste` 是英文，skill 正文用中文“粘贴”也可以；测试里的 `paste` 需要正文出现一次，或把测试改为断言“粘贴”。建议测试用 `"粘贴"`，与正文一致。

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_docs_contract.py -q`  
Expected: FAIL on the new assertions.

- [ ] **Step 3: Rewrite the skill frontmatter**

`deep_reach/data/skill/SKILL.md` 开头改为：

```yaml
---
name: deep-reach
description: |
  给 agent 的结构化上网入口：按 P0 官方接口 → P1 公开网页 → P2 第三方引擎 →
  P3 bsk UI 回退降级。重点覆盖产品调研：国内外社媒、Amazon 选品、众筹、专利/版权。
  当用户点名支持的平台、粘贴这些平台的链接、需要评论/字幕/榜单/商品/专利等结构化数据，
  或内置 web search/read 不可用、失败、拿不到正文时使用。
  普通公开网页优先用内置工具；Deep-Reach 补齐结构化数据和登录/反爬场景。
  写操作仅在用户明确要求时执行；付费 API、Amazon 关键词量/流量数据不在范围内。
metadata:
  homepage: https://github.com/wayneace/deep-reach
  version: "0.13.0"
---

> 这里先用当前包版本 `0.13.0`，保证 Task 5 的
> `test_skill_version_matches_package` 通过；Task 6 升版本时再把这里改成 `0.14.0`。
```

- [ ] **Step 4: Rewrite the body sections**

按以下顺序保留/新增：

1. `# Deep-Reach` + 一句定位。
2. `## 选择路由`：设计文档 5.2 的表 + 配套规则。
3. `## 调用前`：说明 channel/action；P3/写操作必须说明并确认；平台名/链接不等于授权。
4. `## 命令`：三组——自动路径、P3 回退、需要 key。每组 3-5 条示例。
5. `## 结果信封`：保留现有 JSON 示例。
6. `## 错误处理`：保留现有表并补 `UPSTREAM_BROKEN`、`QUOTA_EXHAUSTED`、`CONFIG_ERROR`；`NEED_SETUP`/`NEED_LOGIN` 写成设计文档 5.4 的步骤。
7. `## 规则`：保留写操作、不碰凭据、不编造、限速、URL 边界等；增加“不要因为平台名/链接自动安装/登录/写”。
8. `## 能力契约`：指向 `references/capabilities.md`，并写“实际可用性以 `deep-reach channels --json` 为准”。
9. 末尾加“源码仓库内开发时通过 uv 运行同一 CLI；安装版直接用 `deep-reach`”，不要写完整 `uv run deep-reach`。

- [ ] **Step 5: Run the docs contract tests**

Run: `uv run pytest tests/test_docs_contract.py -q`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add deep_reach/data/skill/SKILL.md tests/test_docs_contract.py
git commit -m "docs: route the skill by task instead of always calling"
```

---

## Task 6: Setup summary, version, docs, wheel guard, full verification

**Files:**
- Modify: `deep_reach/runtime/setup.py`
- Modify: `tests/test_setup.py`
- Modify: `scripts/check_wheel.py`
- Modify: `pyproject.toml`
- Modify: `deep_reach/__init__.py`
- Modify: `uv.lock`
- Modify: `PRODUCT.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `tests/test_docs_contract.py`

**Interfaces:**
- Consumes: `deep-reach skill install` from Task 4.
- Produces: release 0.14.0 with packaged skill and wheel guard.

- [ ] **Step 1: Write the failing setup summary test**

在 `tests/test_setup.py` 的 `SetupSummaryTest` 增加：

```python
    def test_summary_mentions_skill_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keys.yaml"
            plan = build_setup_plan(Keys({}, path=path), opencli_version="")
            text = format_setup_summary(plan, [], plan.keys)
        self.assertIn("Skill:", text)
        self.assertIn("deep-reach skill install --dest", text)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_setup.py -q`  
Expected: FAIL because the summary has no Skill section.

- [ ] **Step 3: Add the setup summary lines**

`deep_reach/runtime/setup.py` 的 `format_setup_summary` 末尾增加：

```text
Skill:
  install: deep-reach skill install --dest <your client's skills directory>
  check:   deep-reach skill status --dest <your client's skills directory>
```

- [ ] **Step 4: Add the wheel guard**

`scripts/check_wheel.py` 增加：

```python
SKILL_SUFFIX = "deep_reach/data/skill/SKILL.md"
SKILL_CAPS_SUFFIX = "deep_reach/data/skill/references/capabilities.md"
```

在读取 wheel 时断言两者各恰好一个；失败信息写明缺失路径。
最后一行输出改为：

```python
print(
    f"{wheel}: {len(visible)} visible channels + keys template + skill packaged"
)
```

- [ ] **Step 5: Bump version and docs**

- `pyproject.toml`、`deep_reach/__init__.py` → `0.14.0`
- `deep_reach/data/skill/SKILL.md` 的 `metadata.version` → `"0.14.0"`
- `uv lock` 更新 `uv.lock`
- `PRODUCT.md` 版本 → 0.14.0
- `README.md`：
  - 状态版本 → 0.14.0，测试数用实际 pytest 输出。
  - 增加“Agent skill”小节：
    ```bash
    deep-reach skill path
    deep-reach skill install --dest <skills-dir>
    deep-reach skill status --dest <skills-dir>
    ```
  - 说明安装为 `<skills-dir>/deep-reach/`，不会自动删除旧的 `<skills-dir>/skill/`。
- `CHANGELOG.md` 增加 v0.14.0 条目。
- `tests/test_docs_contract.py` 增加 `test_changelog_has_v0140`。

- [ ] **Step 6: Run the full suite and get the count**

Run: `uv run pytest -q`  
Expected: PASS；记录输出中的 `N passed`，用它更新 README/CHANGELOG 的测试数。

- [ ] **Step 7: Run docs contract again after updating the count**

Run: `uv run pytest tests/test_docs_contract.py -q`  
Expected: PASS.

- [ ] **Step 8: Lint and build**

```bash
uv run ruff check .
uv build
uv run python scripts/check_wheel.py
```

Expected: ruff clean；wheel 检查输出包含 `skill packaged`。

- [ ] **Step 9: Real install into Cherry, without deleting the old skill**

Run:

```bash
uv run deep-reach skill status --dest "$HOME/Library/Application Support/CherryStudio/Data/Skills"
uv run deep-reach skill install --dest "$HOME/Library/Application Support/CherryStudio/Data/Skills" --yes
uv run deep-reach skill status --dest "$HOME/Library/Application Support/CherryStudio/Data/Skills"
test -f "$HOME/Library/Application Support/CherryStudio/Data/Skills/deep-reach/SKILL.md"
test -d "$HOME/Library/Application Support/CherryStudio/Data/Skills/skill"
```

Expected: status 从 `missing` 变为 `current`；`deep-reach/SKILL.md` 存在；旧的 `skill/` 仍然存在。
不要删除旧目录；报告给用户，由用户决定。

- [ ] **Step 10: Commit**

```bash
git add deep_reach/runtime/setup.py tests/test_setup.py scripts/check_wheel.py \
  pyproject.toml deep_reach/__init__.py uv.lock PRODUCT.md README.md CHANGELOG.md \
  tests/test_docs_contract.py
git commit -m "chore: release v0.14.0 with skill entrypoint"
```

---

## Self-Review

**1. Spec coverage**

- 5.1 描述/元数据 → Task 5。
- 5.2 路由表 → Task 5。
- 5.3 命令分组 → Task 5。
- 5.4 错误表/登录边界 → Task 5。
- 5.5 命令风格 → Task 5。
- 5.6 打包位置 → Task 1。
- 5.7 `skill` 命令/状态机/安装 → Task 2、3、4。
- 5.8 setup summary → Task 6。
- 5.9 版本/测试/wheel → Task 2、3、4、5、6。

**2. Step scan**

每个 Step 都有可检查结果：测试失败/通过、文件存在、wheel 内容、status 状态、退出码。
没有“处理边界情况”这类空步骤；边界情况都在 Review Focus 对应的测试里。

**3. Type consistency**

- `skill_status` 返回 dict；`build_install_plan` 返回 `{**status, "action": ...}`；`apply_install` 接收 plan。
- CLI 使用 `skill_dir`、`packaged_version`、`skill_status`、`build_install_plan`、`apply_install`、`format_*`，名称与 Task 2/3 一致。
- `Path` 参数统一；`dest` 是用户传入的 skills 目录，目标固定为 `dest / "deep-reach"`。

**4. Review Focus**

- 父目录不存在 → Task 3 `test_apply_creates_named_dir`（tmp 存在）不足以覆盖父目录不存在；在 Task 3 加一个 `test_apply_creates_missing_parent`，`dest = Path(tmp)/"a"/"b"`，断言安装成功。
- symlink/普通文件 → Task 2 `test_invalid_regular_file` / `test_symlink`，Task 3 `test_apply_refuses_invalid_and_symlink`。
- 自定义文件 → Task 2 `test_modified_extra_file`，Task 3 `test_apply_replaces_and_removes_stale_files`。
- ahead 不降级 → Task 2 `test_ahead`，Task 3 `test_plan_actions`。
- legacy 不删除 → Task 2 `test_legacy_flag`，Task 4 `test_install_yes` 后断言 `<dest>/skill` 仍在（在 Task 4 的 `test_install_yes` 加断言）。
- 非交互无 `--yes` → Task 4 `test_install_non_interactive_requires_yes`。

**5. Proportion**

计划包含 6 个任务、核心测试代码和接口签名；没有把 150 行 SKILL.md 全文抄进计划，
只给出必须固定的 description、路由表和测试断言。实现者可以在这些约束内写正文。

## Execution Handoff

计划已保存。建议 **Native** 执行：6 个任务共享同一个 `skill.py` 和 CLI 接口，
串行实现比每个任务起子代理更快；最后用一次 fresh review 检查整条分支。
