"""Backend pauses and channel cooldowns, persisted across CLI processes.

A failed backend is skipped for a short window instead of being retried by the
next command; a confirmed rate limit cools the whole channel for an hour.
Everything is best-effort: an unreadable state file never blocks a query.
"""

from __future__ import annotations

import hashlib
from typing import Optional

from ..channels.base import Channel
from . import state
from .result import NEED_SETUP, RATE_LIMITED, TIMEOUT, UPSTREAM_BROKEN, ReachError

BACKEND_PAUSE_SECONDS = {TIMEOUT: 60, UPSTREAM_BROKEN: 120, NEED_SETUP: 60}
RATE_LIMIT_SECONDS = 3600


def fingerprint(channel: Channel) -> str:
    """Invalidate saved health when the channel's backend chain changes."""
    parts = [channel.name]
    for action in channel.actions:
        parts.append(action.name)
        parts.extend(f"{backend.label}:{backend.tier}" for backend in action.backends)
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def cooldown(channel_name: str) -> Optional[dict]:
    saved = state.load().get("cooldowns", {}).get(channel_name)
    if not isinstance(saved, dict):
        return None
    left = RATE_LIMIT_SECONDS - state.age_seconds(saved.get("at"))
    if saved.get("code") == RATE_LIMITED and left > 0:
        return {
            "code": RATE_LIMITED,
            "message": saved.get("message") or "rate limited",
            "retry_after_seconds": max(1, int(left)),
        }
    return None


def backend_pause(
    channel_name: str, action: str, backend: str, fingerprint_value: str
) -> Optional[dict]:
    saved = (
        state.load()
        .get("backend_health", {})
        .get(channel_name, {})
        .get(action, {})
        .get(backend)
    )
    if not isinstance(saved, dict):
        return None
    if saved.get("fingerprint") != fingerprint_value:
        return None
    ttl = BACKEND_PAUSE_SECONDS.get(saved.get("code"), 0)
    left = ttl - state.age_seconds(saved.get("at"))
    if left <= 0:
        return None
    return {
        "code": saved.get("code"),
        "message": f"{backend} is paused after {saved.get('code')}; retry later",
        "retry_after_seconds": max(1, int(left)),
    }


def remember(
    channel_name: str,
    action: str,
    backend: str,
    error: ReachError,
    fingerprint_value: str,
) -> None:
    stamp = state.now()

    def change(saved: dict) -> None:
        health = (
            saved.setdefault("backend_health", {})
            .setdefault(channel_name, {})
            .setdefault(action, {})
        )
        if error.code in BACKEND_PAUSE_SECONDS:
            health[backend] = {
                "code": error.code,
                "at": stamp,
                "fingerprint": fingerprint_value,
            }
        if error.code == RATE_LIMITED:
            saved.setdefault("cooldowns", {})[channel_name] = {
                "code": RATE_LIMITED,
                "message": "platform reported a rate limit",
                "at": stamp,
            }

    try:
        state.mutate(change)
    except (OSError, ReachError):
        pass


def clear_backend(channel_name: str, action: str, backend: str) -> None:
    """Drop a saved pause after a success, without writing on the common path."""
    saved = (
        state.load()
        .get("backend_health", {})
        .get(channel_name, {})
        .get(action, {})
    )
    if backend not in saved:
        return

    def change(data: dict) -> None:
        (
            data.get("backend_health", {})
            .get(channel_name, {})
            .get(action, {})
            .pop(backend, None)
        )

    try:
        state.mutate(change)
    except (OSError, ReachError):
        pass


def report() -> dict:
    saved = state.load()
    cooldowns = []
    for name, item in saved.get("cooldowns", {}).items():
        if not isinstance(item, dict):
            continue
        left = RATE_LIMIT_SECONDS - state.age_seconds(item.get("at"))
        if left > 0:
            cooldowns.append(
                {
                    "channel": name,
                    "code": item.get("code"),
                    "message": item.get("message"),
                    "retry_after_seconds": max(1, int(left)),
                }
            )
    paused = []
    for channel_name, actions in saved.get("backend_health", {}).items():
        if not isinstance(actions, dict):
            continue
        for action, backends in actions.items():
            if not isinstance(backends, dict):
                continue
            for label, item in backends.items():
                if not isinstance(item, dict):
                    continue
                ttl = BACKEND_PAUSE_SECONDS.get(item.get("code"), 0)
                left = ttl - state.age_seconds(item.get("at"))
                if left > 0:
                    paused.append(
                        {
                            "channel": channel_name,
                            "action": action,
                            "backend": label,
                            "code": item.get("code"),
                            "retry_after_seconds": max(1, int(left)),
                        }
                    )
    requests_last_minute = {}
    for channel_name, stamps in saved.get("request_log", {}).items():
        if not isinstance(stamps, list):
            continue
        count = sum(1 for stamp in stamps if state.age_seconds(stamp) < 60)
        if count:
            requests_last_minute[channel_name] = count
    return {
        "path": str(state.state_path()),
        "cooldowns": cooldowns,
        "paused_backends": paused,
        "request_starts": saved.get("request_starts", {}),
        "requests_last_minute": requests_last_minute,
    }
