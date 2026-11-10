"""Environment-aware channel availability.

The registry declares intent (level/status). This module answers the narrower
question a user asks before running a command: is there at least one backend
that can run in *this* environment right now?

`doctor` probes the OpenCLI connection for an exact answer. `channels` only
checks whether OpenCLI is installed, so it stays fast; when the binary exists
but the browser is not connected, `channels` is deliberately optimistic and
`doctor` is the precise check.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Optional

from ..channels.base import Action, BackendSpec, Channel
from .keys import Keys, default_keys_path, template_path

OPENCLI_BIN_ENV = "DEEP_REACH_OPENCLI_BIN"
OPENCLI_PACKAGE = "@jackwener/opencli"
OPENCLI_INSTALL_COMMAND = f"npm install -g {OPENCLI_PACKAGE}"
BROWSER_BRIDGE_URL = (
    "https://chromewebstore.google.com/detail/opencli/"
    "ildkmabpimmkaediidaifkhjpohdnifk"
)


def _opencli_installed() -> bool:
    return bool(os.environ.get(OPENCLI_BIN_ENV) or shutil.which("opencli"))


@dataclass(frozen=True)
class Environment:
    keys: Keys
    opencli_installed: bool
    browser_connected: Optional[bool] = None

    @property
    def opencli_available(self) -> bool:
        if self.browser_connected is None:
            return self.opencli_installed
        return bool(self.browser_connected and self.opencli_installed)


@dataclass(frozen=True)
class ChannelAvailability:
    status: str
    declared_status: str
    runnable: bool
    available_actions: tuple[str, ...]
    unavailable_actions: dict[str, list[str]]
    ui_fallback_actions: tuple[str, ...] = ()


def detect_environment(
    keys: Keys, *, client=None, probe_browser: bool = False
) -> Environment:
    """Build an environment view; only `doctor` opts into the browser probe."""
    installed = _opencli_installed()
    connected: Optional[bool] = None
    if probe_browser and client is not None:
        try:
            connected = bool(client.profile_status().get("connected"))
        except Exception:  # noqa: BLE001 - availability must never raise
            connected = False
        installed = installed or bool(connected)
    return Environment(
        keys=keys, opencli_installed=installed, browser_connected=connected
    )


def environment_from_profile(keys: Keys, profile: dict) -> Environment:
    """Build an environment view from an already-collected OpenCLI profile."""
    connected = bool(profile.get("connected"))
    installed = bool(
        connected
        or profile.get("daemon")
        or profile.get("cli_version")
        or _opencli_installed()
    )
    return Environment(
        keys=keys, opencli_installed=installed, browser_connected=connected
    )


def backend_unavailable_reason(
    spec: BackendSpec, channel: Channel, env: Environment
) -> Optional[str]:
    if spec.requires_key:
        key_paths = spec.required_keys(channel)
        if any(not path for path in key_paths):
            return "requires a key but no key path is configured"
        missing = [path for path in key_paths if path and not env.keys.has(path)]
        if missing:
            return f"{', '.join(missing)} missing"
    if spec.label.startswith("opencli-") and not env.opencli_available:
        if not env.opencli_installed:
            return "OpenCLI is not installed"
        return "OpenCLI browser is not connected"
    return None


def action_availability(
    action: Action, channel: Channel, env: Environment
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    for spec in action.backends:
        if action.requires == "login" and not spec.supports_login:
            reasons.append(f"{spec.label}: does not support login")
            continue
        reason = backend_unavailable_reason(spec, channel, env)
        if reason is None:
            return True, []
        reasons.append(f"{spec.label}: {reason}")
    return False, reasons


def channel_availability(channel: Channel, env: Environment) -> ChannelAvailability:
    available: list[str] = []
    unavailable: dict[str, list[str]] = {}
    ui_fallback: list[str] = []
    for action in channel.actions:
        ok, reasons = action_availability(action, channel, env)
        if ok:
            available.append(action.name)
        else:
            unavailable[action.name] = reasons
            if action.ui_fallback:
                ui_fallback.append(action.name)

    all_ok = bool(channel.actions) and not unavailable
    any_ok = bool(available)
    declared = channel.status

    if declared == "planned":
        status = "planned"
    elif declared == "needs_key":
        status = "ready" if all_ok else "needs_key"
    elif declared == "needs_login":
        # OpenCLI connectivity is detectable; per-site login state is not.
        status = "needs_login" if env.opencli_available else "needs_setup"
    elif declared == "experimental":
        status = "experimental" if all_ok else ("degraded" if any_ok else "needs_setup")
    else:
        status = "ready" if all_ok else ("degraded" if any_ok else "needs_setup")

    return ChannelAvailability(
        status=status,
        declared_status=declared,
        runnable=any_ok,
        available_actions=tuple(available),
        unavailable_actions=unavailable,
        ui_fallback_actions=tuple(ui_fallback),
    )


RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


def channel_risk(channel: Channel) -> str:
    """The highest declared risk across the channel's actions and backends."""
    risks = [action.risk for action in channel.actions if action.risk]
    risks.extend(
        backend.risk
        for action in channel.actions
        for backend in action.backends
        if backend.risk
    )
    if not risks:
        return "low"
    return max(risks, key=lambda risk: RISK_ORDER.get(risk, 0))


def _bsk_hint(actions: tuple[str, ...], env: Optional[Environment]) -> str:
    profile = "main"
    if env is not None:
        profile = str(env.keys.get("browser.bsk_profile") or "main")
    return (
        f"可用 `deep-reach bsk ...` 回退（{', '.join(actions)}；"
        f"profile: {profile}，高风险；bsk 全能力可用，写操作需确认）"
    )


def next_action_for(
    channel: Channel,
    availability: ChannelAvailability,
    env: Optional[Environment] = None,
) -> str:
    """The most actionable next step for the channel's effective status."""
    status = availability.status
    ui_actions = availability.ui_fallback_actions
    ui_hint = _bsk_hint(ui_actions, env) if ui_actions else ""

    if status == "needs_setup":
        has_auto = any(action.backends for action in channel.actions)
        if ui_actions and not has_auto:
            return ui_hint
        if env is not None and not env.opencli_installed:
            base = (
                f"安装 OpenCLI（`{OPENCLI_INSTALL_COMMAND}`），"
                "然后运行 `deep-reach doctor`"
            )
        else:
            base = (
                "安装/启用 OpenCLI Browser Bridge 扩展"
                f"（{BROWSER_BRIDGE_URL}），然后运行 `deep-reach doctor`"
            )
        if channel.next_action:
            base = f"{base}；安装后：{channel.next_action}"
        return f"{base}；{ui_hint}" if ui_hint else base

    if status == "degraded":
        names = ", ".join(availability.unavailable_actions)
        reasons = " ".join(
            reason
            for items in availability.unavailable_actions.values()
            for reason in items
        )
        if env is not None and "missing" in reasons:
            path = env.keys.path or default_keys_path()
            base = (
                f"部分动作当前不可用（{names}）；缺 key 的写入 {path}"
                f"（模板：{template_path()}）；运行 `deep-reach doctor` 查看原因"
            )
        else:
            base = f"部分动作当前不可用（{names}）；运行 `deep-reach doctor` 查看原因"
        return f"{base}；{ui_hint}" if ui_hint else base

    if status == "needs_key":
        path = (
            env.keys.path
            if env is not None and env.keys.path
            else default_keys_path()
        )
        detail = channel.next_action or f"填写 {channel.key_path or '对应 key'}"
        base = f"{detail}；写入 {path}（模板：{template_path()}）"
        return f"{base}；{ui_hint}" if ui_hint else base

    if status == "needs_login":
        base = (
            channel.next_action
            or f"在 Deep-Reach 专用 Chrome profile 登录 {channel.name} 后重试"
        )
        return f"{base}；{ui_hint}" if ui_hint else base

    if channel.next_action:
        return channel.next_action
    if status == "experimental":
        return "该渠道可能不稳定；失败时稍后重试"
    return "-"
