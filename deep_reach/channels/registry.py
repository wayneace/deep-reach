"""Curated channel registry.

The registry is the product surface: it declares which channels are actually
available, their level, status, capabilities, and ordered backends.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

from .base import TIER_ORDER, Action, BackendSpec, Channel, Param

_BUILTIN: dict[str, Any] = {
    "channels": {
        "bilibili": {
            "level": "default",
            "status": "ready",
            "category": "social",
            "description": "B站搜索、视频、字幕、评论",
            "actions": {
                "search": {
                    "params": ["query", "limit"],
                    "backends": [
                        {"label": "bilibili-public"},
                        {"label": "opencli-bilibili", "site": "bilibili", "command": "search", "args": ["{query}"], "limit": True},
                    ],
                }
            },
        },
        "web": {
            "level": "default",
            "status": "ready",
            "category": "web",
            "description": "通用网页阅读",
            "key": "search.jina.api_key",
            "actions": {
                "read": {
                    "params": ["target"],
                    "backends": [{"label": "jina"}],
                }
            },
        },
    }
}


@dataclass
class Registry:
    channels: dict[str, Channel]
    planned: dict[str, Channel]
    source_path: Optional[Path] = None

    @property
    def visible(self) -> dict[str, Channel]:
        return self.channels

    def get(self, name: str) -> Optional[Channel]:
        return self.channels.get(name) or self.planned.get(name)

    def all(self) -> dict[str, Channel]:
        merged = dict(self.channels)
        merged.update(self.planned)
        return merged


def _channels_path() -> Optional[Path]:
    override = os.environ.get("DEEP_REACH_CHANNELS_FILE")
    if override:
        return Path(override).expanduser()
    user = Path.home() / ".deep-reach" / "channels.yaml"
    if user.exists():
        return user
    packaged = Path(__file__).resolve().parent.parent / "data" / "channels.yaml"
    if packaged.exists():
        return packaged
    # Legacy source checkout path; kept so older working trees keep working.
    legacy = Path(__file__).resolve().parents[2] / "config" / "channels.yaml"
    if legacy.exists():
        return legacy
    return None


def _param(name: str) -> Param:
    if name == "limit":
        return Param(name, required=False, type=int, default=20)
    if name == "page":
        return Param(name, required=False, type=int, default=1)
    return Param(name)


def _backend(value: Any, action_name: str) -> BackendSpec:
    if isinstance(value, str):
        return BackendSpec(label=value, method=action_name)
    if isinstance(value, dict):
        label = str(value["label"])
        tier = str(value.get("tier", "p1")).lower()
        if tier not in TIER_ORDER:
            raise ValueError(
                f"backend {label!r}: unknown tier {tier!r}; use one of p0, p1, p2"
            )
        key = value.get("key")
        raw_keys = value.get("keys")
        if raw_keys is None:
            keys: tuple[str, ...] = ()
        elif isinstance(raw_keys, str):
            keys = (raw_keys,)
        elif isinstance(raw_keys, (list, tuple)):
            keys = tuple(str(item) for item in raw_keys)
        else:
            raise ValueError(
                f"backend {label!r}: keys must be a string or a list of strings"
            )
        options = {
            field: val
            for field, val in value.items()
            if field not in {"label", "method", "requires_key", "tier", "key", "keys"}
        }
        return BackendSpec(
            label=label,
            method=str(value.get("method") or action_name),
            requires_key=bool(value.get("requires_key", False)),
            key=str(key) if key else None,
            tier=tier,
            options=options,
            keys=keys,
        )
    raise ValueError(f"invalid backend entry: {value!r}")


def _parse(data: dict) -> Registry:
    visible: dict[str, Channel] = {}
    planned: dict[str, Channel] = {}
    for name, spec in (data.get("channels") or {}).items():
        channel_name = str(name)
        actions: list[Action] = []
        for action_name, action_spec in (spec.get("actions") or {}).items():
            params = tuple(_param(p) for p in action_spec.get("params", []))
            backends = tuple(
                sorted(
                    (_backend(b, action_name) for b in action_spec.get("backends", [])),
                    key=lambda backend: TIER_ORDER[backend.tier],
                )
            )
            actions.append(
                Action(
                    name=action_name,
                    params=params,
                    backends=backends,
                    timeout=float(action_spec.get("timeout", 30.0)),
                    requires=str(action_spec.get("requires", "none")),
                    description=str(action_spec.get("description", "")),
                )
            )
        channel = Channel(
            name=channel_name,
            category=str(spec.get("category", "unknown")),
            description=str(spec.get("description", "")),
            actions=tuple(actions),
            key_path=spec.get("key"),
            requires_key=bool(spec.get("requires_key", False)),
            level=str(spec.get("level", "optional")),
            status=str(spec.get("status", "ready")),
            limits=str(spec.get("limits", "")),
            not_supported=tuple(spec.get("not_supported") or ()),
            next_action=str(spec.get("next_action", "")),
        )
        if channel.level == "planned":
            planned[channel_name] = channel
        else:
            visible[channel_name] = channel
    return Registry(channels=visible, planned=planned)


def load_registry() -> Registry:
    path = _channels_path()
    if path is None:
        return _parse(_BUILTIN)
    from ..runtime.result import CONFIG_ERROR, ReachError

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError("top level must be a mapping")
        registry = _parse(data)
    except ReachError:
        raise
    except Exception as exc:  # noqa: BLE001 - registry errors must be explicit
        raise ReachError(CONFIG_ERROR, f"cannot load channels file {path}: {exc}") from exc
    registry.source_path = path
    return registry


def load_channels() -> dict[str, Channel]:
    """Backward-compatible helper: all channels, including planned."""
    return load_registry().all()
