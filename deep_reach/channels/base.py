"""Channel / Action / Backend definitions.

A Channel is a platform. An Action is a verb on that platform. Backends belong
to one of three tiers and are tried in tier order:

    P0  platform-native free interface: official API free tier, public JSON
        endpoint, or a native CLI. Optional key, optional login.
    P1  OpenCLI browser bridge: reuses the login already present in the
        connected Chrome profile. Optional login.
    P2  third-party reader / collection service (Jina, Firecrawl, Bright Data).
        Optional key.

Inside one tier the authored order is kept. The registry sorts backends by
tier, so the YAML author cannot accidentally put P2 ahead of P0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

TIERS = ("p0", "p1", "p2")
TIER_ORDER = {tier: index for index, tier in enumerate(TIERS)}

TIER_LABELS = {
    "p0": "原生免费接口（官方 API 免费层 / 公开 JSON / CLI）",
    "p1": "OpenCLI 浏览器桥（复用登录态）",
    "p2": "第三方阅读/采集服务（Jina / Firecrawl / Bright Data）",
}

TIER_ACCESS = {
    "p0": "可选 key / 可选登录",
    "p1": "可选登录",
    "p2": "可选 key",
}


@dataclass(frozen=True)
class Param:
    name: str
    required: bool = True
    type: type = str
    default: Any = None


@dataclass(frozen=True)
class BackendSpec:
    label: str
    method: str
    requires_key: bool = False
    key: Optional[str] = None
    tier: str = "p1"
    options: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Action:
    name: str
    params: tuple[Param, ...] = ()
    backends: tuple[BackendSpec, ...] = ()
    public_web: tuple[str, ...] = ()
    timeout: float = 30.0
    requires: str = "none"  # none | login | key
    description: str = ""

    @property
    def tiers(self) -> tuple[str, ...]:
        seen: list[str] = []
        for backend in self.backends:
            if backend.tier not in seen:
                seen.append(backend.tier)
        return tuple(sorted(seen, key=lambda tier: TIER_ORDER.get(tier, 99)))


@dataclass
class Channel:
    name: str
    category: str
    actions: tuple[Action, ...]
    key_path: Optional[str] = None
    requires_key: bool = False
    description: str = ""
    level: str = "optional"  # default | optional | experimental | planned
    status: str = "ready"  # ready | needs_login | needs_key | experimental | planned
    limits: str = ""
    not_supported: tuple[str, ...] = ()
    next_action: str = ""

    def action(self, name: str) -> Optional[Action]:
        return next((a for a in self.actions if a.name == name), None)

    @property
    def backend_labels(self) -> list[str]:
        seen: list[str] = []
        for action in self.actions:
            for backend in action.backends:
                if backend.label not in seen:
                    seen.append(backend.label)
        return seen

    @property
    def tiers(self) -> tuple[str, ...]:
        seen: list[str] = []
        for action in self.actions:
            for tier in action.tiers:
                if tier not in seen:
                    seen.append(tier)
        return tuple(sorted(seen, key=lambda tier: TIER_ORDER.get(tier, 99)))
