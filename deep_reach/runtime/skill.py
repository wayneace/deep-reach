from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from importlib import resources
from pathlib import Path
from typing import Optional

import yaml

from .result import BAD_INPUT, CONFIG_ERROR, ReachError

SKILL_NAME = "deep-reach"
SKILL_PACKAGE = "deep_reach.data"
SKILL_REL = "deep-reach"


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
    if not isinstance(data, dict):
        return None
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        return None
    version = metadata.get("version")
    return str(version).strip() if version else None


def _is_legacy_deep_reach(root: Path) -> bool:
    path = root / "SKILL.md"
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return re.search(r"(?m)^name:\s*deep-reach\s*$", text) is not None


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
    dest = Path(dest).expanduser()
    if dest.exists() and not dest.is_dir():
        raise ReachError(
            BAD_INPUT, f"skills directory is not a directory: {dest}"
        )
    try:
        return _skill_status(dest)
    except OSError as exc:
        raise ReachError(
            CONFIG_ERROR, f"cannot inspect skill at {dest}: {exc}"
        ) from exc


def _skill_status(dest: Path) -> dict:
    target = installed_skill_dir(dest)
    legacy = dest / "skill"
    packaged = skill_dir()
    packaged_files = _skill_files(packaged)
    version = packaged_version()
    result = {
        "ok": True,
        "target": str(target),
        "state": "missing",
        "installed_version": None,
        "packaged_version": version,
        "legacy": _is_legacy_deep_reach(legacy),
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
    installed_version = read_skill_version(target)
    result["installed_version"] = installed_version
    installed_tuple = _version_tuple(installed_version)
    packaged_tuple = _version_tuple(version)
    if (
        installed_tuple is not None
        and packaged_tuple is not None
        and installed_tuple > packaged_tuple
    ):
        result["state"] = "ahead"
        return result
    installed_files = _skill_files(target)
    missing = sorted(set(packaged_files) - set(installed_files))
    if "SKILL.md" not in installed_files or missing:
        result["state"] = "incomplete"
        result["diff"] = missing[:20]
        result["diff_count"] = len(missing)
        return result
    if installed_tuple is None or packaged_tuple is None:
        result["state"] = "modified"
        diff = _diff_files(packaged_files, installed_files)
        result["diff"] = diff[:20]
        result["diff_count"] = len(diff)
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
    try:
        parent.mkdir(parents=True, exist_ok=True)
        temp = Path(tempfile.mkdtemp(prefix=".deep-reach-skill-", dir=str(parent)))
    except OSError as exc:
        raise ReachError(
            CONFIG_ERROR, f"cannot prepare install at {parent}: {exc}"
        ) from exc
    backup = parent / f".deep-reach-skill-backup-{os.getpid()}"
    try:
        staged = temp / "skill"
        try:
            shutil.copytree(skill_dir(), staged)
        except OSError as exc:
            raise ReachError(
                CONFIG_ERROR, f"cannot stage skill: {exc}"
            ) from exc
        if target.exists() or target.is_symlink():
            if backup.exists():
                shutil.rmtree(backup)
            try:
                os.replace(target, backup)
            except OSError as exc:
                raise ReachError(
                    CONFIG_ERROR, f"cannot move old skill aside: {exc}"
                ) from exc
        try:
            os.replace(staged, target)
        except Exception as exc:
            if backup.exists():
                try:
                    os.replace(backup, target)
                except OSError:
                    pass
            if isinstance(exc, OSError):
                raise ReachError(
                    CONFIG_ERROR, f"cannot install skill at {target}: {exc}"
                ) from exc
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
