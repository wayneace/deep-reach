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
