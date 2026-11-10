"""Private filesystem helpers for keys, state, and browser profiles.

All helpers are best-effort: a permission failure never blocks a command.
They only tighten paths the current user owns; a symlink or a file owned by
another user is reported instead of followed.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path


def _owned_by_current_user(path: Path) -> bool:
    try:
        return path.stat().st_uid == os.getuid()
    except (AttributeError, OSError):
        return False


def ensure_private_dir(path: Path) -> str:
    """Create a directory with 0700 and tighten an existing user-owned one."""
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:
        return f"cannot create {path}: {exc}"
    if os.name == "nt":
        return ""
    if path.is_symlink():
        return f"{path} is a symlink; permissions not tightened"
    try:
        info = path.stat()
    except OSError as exc:
        return f"cannot stat {path}: {exc}"
    if info.st_uid != os.getuid():
        return f"{path} is owned by uid {info.st_uid}; permissions not tightened"
    if stat.S_IMODE(info.st_mode) & 0o077:
        try:
            os.chmod(path, 0o700)
        except OSError as exc:
            return f"cannot tighten {path}: {exc}"
    return ""


def tighten_file(path: Path) -> str:
    """Tighten a regular file to 0600 without following symlinks."""
    if os.name == "nt" or not path.exists():
        return ""
    if path.is_symlink():
        return f"{path} is a symlink; target permissions are not enforced"
    try:
        info = path.stat()
    except OSError as exc:
        return f"cannot stat {path}: {exc}"
    if info.st_uid != os.getuid():
        return f"{path} is owned by uid {info.st_uid}; permissions not tightened"
    if stat.S_IMODE(info.st_mode) & 0o077:
        try:
            os.chmod(path, 0o600)
        except OSError as exc:
            return f"cannot tighten {path}: {exc}"
    return ""


def write_target(path: Path) -> Path:
    """Resolve a symlink so atomic writes preserve dotfile setups."""
    if not path.is_symlink():
        return path
    try:
        return path.resolve()
    except (OSError, RuntimeError):
        return path
