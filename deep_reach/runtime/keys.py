"""Key loading with graceful degradation.

All keys are optional. A missing file, a missing key, or a placeholder value
never stops the process; callers use `has()` to decide whether a keyed backend
is available and fall back to the next backend.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

from .result import (
    CONFIG_ERROR,
    PLACEHOLDER_VALUES,
    ReachError,
    is_secret_path,
    register_secret,
)
from .secure_paths import ensure_private_dir, tighten_file

PLACEHOLDERS = PLACEHOLDER_VALUES


def _register_secrets(node: Any, prefix: str = "") -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            _register_secrets(value, name)
    elif is_secret_path(prefix):
        register_secret(node)


def default_keys_path() -> Path:
    override = os.environ.get("DEEP_REACH_KEYS_FILE")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".deep-reach" / "keys.yaml"


def template_path() -> Path:
    """Absolute path to the packaged keys template."""
    from importlib import resources

    return Path(str(resources.files("deep_reach.data").joinpath("keys.example.yaml")))


class Keys:
    """An immutable view over keys.yaml plus optional environment overrides."""

    def __init__(self, data: Optional[dict] = None, path: Optional[Path] = None):
        self.data = data or {}
        self.path = path
        self.permission_note = ""
        _register_secrets(self.data)

    @classmethod
    def load(cls, path: Optional[str | Path] = None) -> "Keys":
        p = Path(path).expanduser() if path else default_keys_path()
        notes = [tighten_file(p)]
        if p.parent == Path.home() / ".deep-reach":
            notes.append(ensure_private_dir(p.parent))
        note = "; ".join(item for item in notes if item)
        if not p.exists():
            keys = cls({}, p)
            keys.permission_note = note
            return keys
        try:
            raw = p.read_text(encoding="utf-8")
            data = yaml.safe_load(raw) or {}
            if not isinstance(data, dict):
                raise ValueError("top-level YAML value must be a mapping")
        except ReachError:
            raise
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
            where = (
                f" at line {mark.line + 1}, column {mark.column + 1}"
                if mark is not None
                else ""
            )
            raise ReachError(
                CONFIG_ERROR, f"cannot load keys file {p}: invalid YAML{where}"
            ) from None
        except Exception as exc:  # noqa: BLE001 - config errors must be explicit
            raise ReachError(CONFIG_ERROR, f"cannot load keys file {p}: {exc}") from exc
        keys = cls(data, p)
        keys.permission_note = note
        return keys

    @staticmethod
    def _env_name(dotted: str) -> str:
        return "DEEP_REACH_" + dotted.upper().replace(".", "_")

    def get(self, dotted: str, default: Any = None) -> Any:
        env_value = os.environ.get(self._env_name(dotted))
        if env_value is not None and str(env_value).strip():
            value = str(env_value).strip()
            if is_secret_path(dotted):
                register_secret(value)
            return value

        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return default if node is None else node

    def has(self, dotted: str) -> bool:
        value = self.get(dotted)
        if isinstance(value, str):
            return value.strip().lower() not in PLACEHOLDERS
        return value not in (None, "", [], {})

    def status(self, dotted: str) -> str:
        return "set" if self.has(dotted) else "missing"

    def describe(self, paths: Iterable[str]) -> list[dict]:
        return [{"key": p, "status": self.status(p)} for p in paths]
