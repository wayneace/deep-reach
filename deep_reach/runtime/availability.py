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
from .keys import Keys

OPENCLI_BIN_ENV = "DEEP_REACH_OPENCLI_BIN"


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
        reason = backend_unavailable_reason(spec, channel, env)
        if reason is None:
            return True, []
        reasons.append(f"{spec.label}: {reason}")
    return False, reasons


def channel_availability(channel: Channel, env: Environment) -> ChannelAvailability:
    available: list[str] = []
    unavailable: dict[str, list[str]] = {}
    for action in channel.actions:
        ok, reasons = action_availability(action, channel, env)
        if ok:
            available.append(action.name)
        else:
            unavailable[action.name] = reasons

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
    )
