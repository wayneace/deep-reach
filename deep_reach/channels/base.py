"""Channel / Action / Backend definitions.

A Channel is a platform. An Action is a verb on that platform. Backends belong
to one of three automatic tiers and are tried in tier order:

    P0  official interface: official API free tier, public JSON endpoint, or
        an official CLI. Optional key / OAuth.
    P1  public web: direct HTTP, Jina Reader, and public OpenCLI commands.
    P2  third-party search / crawl engine (Tavily, Brave, Firecrawl, Bright
        Data). Optional key / quota.

P3 is not a backend tier: actions with ``ui_fallback`` return ``NEED_UI`` and
hand off to ``deep-reach bsk``. Inside one tier the authored order is kept;
the registry sorts p0 -> p1 -> p2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

TIERS = ("p0", "p1", "p2", "p3")
TIER_ORDER = {tier: index for index, tier in enumerate(TIERS)}

#: p3 is a fallback handoff, not an executable backend tier.
BACKEND_TIERS = ("p0", "p1", "p2")
RISK_LEVELS = ("low", "medium", "high")

TIER_LABELS = {
    "p0": "官方接口（官方 API 免费层 / 公开 JSON / 官方 CLI）",
    "p1": "公开网页（http-read / Jina / OpenCLI 公开命令）",
    "p2": "第三方搜索/采集引擎（Tavily / Brave / Firecrawl / Bright Data）",
    "p3": "bsk UI 回退（agent 驱动，非自动 backend）",
}

TIER_ACCESS = {
    "p0": "none / key / oauth",
    "p1": "none / optional key",
    "p2": "key / quota",
    "p3": "public / login（bsk 全能力，含写操作）",
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
    keys: tuple[str, ...] = ()
    supports_login: bool = False
    risk: str = "low"

    def required_keys(self, channel: "Channel") -> tuple[Optional[str], ...]:
        """Every key path this backend needs; falls back to the legacy single key."""
        return self.keys or ((self.key or channel.key_path),)


@dataclass(frozen=True)
class Action:
    name: str
    params: tuple[Param, ...] = ()
    backends: tuple[BackendSpec, ...] = ()
    public_web: tuple[str, ...] = ()
    timeout: float = 30.0
    requires: str = "none"  # none | login | key
    description: str = ""
    ui_fallback: bool = False
    risk: str = ""

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
    level: str = "optional"  # default | optional | experimental
    status: str = "ready"  # ready | needs_login | needs_key | experimental
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
