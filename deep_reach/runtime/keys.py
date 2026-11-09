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

from .result import CONFIG_ERROR, ReachError

PLACEHOLDERS = {
    "",
    "changeme",
    "change-me",
    "your_key",
    "your-key",
    "placeholder",
    "...",
    "<...>",
}


def default_keys_path() -> Path:
    override = os.environ.get("DEEP_REACH_KEYS_FILE")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".deep-reach" / "keys.yaml"


class Keys:
    """A read-only view over keys.yaml plus optional environment overrides."""

    def __init__(self, data: Optional[dict] = None, path: Optional[Path] = None):
        self.data = data or {}
        self.path = path

    @classmethod
    def load(cls, path: Optional[str | Path] = None) -> "Keys":
        p = Path(path).expanduser() if path else default_keys_path()
        if not p.exists():
            return cls({}, p)
        try:
            raw = p.read_text(encoding="utf-8")
            data = yaml.safe_load(raw) or {}
            if not isinstance(data, dict):
                raise ValueError("top-level YAML value must be a mapping")
        except ReachError:
            raise
        except Exception as exc:  # noqa: BLE001 - config errors must be explicit
            raise ReachError(CONFIG_ERROR, f"cannot load keys file {p}: {exc}") from exc
        return cls(data, p)

    @staticmethod
    def _env_name(dotted: str) -> str:
        return "DEEP_REACH_" + dotted.upper().replace(".", "_")

    def get(self, dotted: str, default: Any = None) -> Any:
        env_value = os.environ.get(self._env_name(dotted))
        if env_value is not None and str(env_value).strip():
            return str(env_value).strip()

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
