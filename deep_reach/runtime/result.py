"""Unified result envelope and error codes for the agent-facing CLI.

Every command prints exactly one JSON object:

    {schema_version, ok, channel, action, backend, items, meta, error}

Agents branch on `ok` and `error.code`; they should never need to parse
upstream output.
"""

from __future__ import annotations

import datetime as _dt
import json
from typing import Any, Optional

SCHEMA_VERSION = 1

# Error codes
NEED_SETUP = "NEED_SETUP"
NEED_LOGIN = "NEED_LOGIN"
UPSTREAM_BROKEN = "UPSTREAM_BROKEN"
TIMEOUT = "TIMEOUT"
RATE_LIMITED = "RATE_LIMITED"
PLATFORM_BLOCKED = "PLATFORM_BLOCKED"
NOT_FOUND = "NOT_FOUND"
BAD_INPUT = "BAD_INPUT"
KEY_MISSING = "KEY_MISSING"
QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
SOURCE_DISABLED = "SOURCE_DISABLED"
CONFIG_ERROR = "CONFIG_ERROR"
WRITE_BLOCKED = "WRITE_BLOCKED"
BUSY = "BUSY"

#: Codes where trying another backend cannot help. RATE_LIMITED and BUSY are
#: final on purpose, matching Agent-Reach: a platform rate limit or a full
#: browser queue stops the channel instead of switching backends.
#:
#: NEED_LOGIN and QUOTA_EXHAUSTED are deliberately NOT final: in the P0/P1/P2
#: model they describe one credential path, not the platform. A P0 cookie may
#: be missing while P1 already has a logged-in browser, and a P0 free-tier
#: quota may be spent while P1 still works.
FINAL_CODES = frozenset(
    {
        NOT_FOUND,
        BAD_INPUT,
        PLATFORM_BLOCKED,
        RATE_LIMITED,
        BUSY,
        SOURCE_DISABLED,
        WRITE_BLOCKED,
    }
)

#: Codes that allow trying the next backend.
RETRYABLE_CODES = frozenset(
    {
        NEED_SETUP,
        UPSTREAM_BROKEN,
        TIMEOUT,
        KEY_MISSING,
        NEED_LOGIN,
        QUOTA_EXHAUSTED,
    }
)

#: When every backend fails, report the most actionable failure, not the last
#: one. Logging in or waiting for a rate limit is more useful than "broken".
ERROR_PRIORITY = (
    PLATFORM_BLOCKED,
    NEED_LOGIN,
    RATE_LIMITED,
    QUOTA_EXHAUSTED,
    BUSY,
    TIMEOUT,
    UPSTREAM_BROKEN,
    NEED_SETUP,
    KEY_MISSING,
    NOT_FOUND,
    SOURCE_DISABLED,
)

DEFAULT_HINTS = {
    NEED_SETUP: "Run `deep-reach doctor` to see what is missing.",
    NEED_LOGIN: "Log in through the OpenCLI dedicated browser; never share a password.",
    UPSTREAM_BROKEN: "Try the next backend or retry later.",
    TIMEOUT: "Retry later; do not loop.",
    RATE_LIMITED: "Respect the retry window; do not switch accounts.",
    PLATFORM_BLOCKED: "Stop automation and resolve the verification manually.",
    NOT_FOUND: "Check the link or id.",
    BAD_INPUT: "Run `deep-reach channels` to see valid usage.",
    KEY_MISSING: "This source is degraded; configure the key or use the fallback.",
    QUOTA_EXHAUSTED: "Free-tier quota is exhausted; the fallback will be used.",
    SOURCE_DISABLED: "No backend is available for this source.",
    CONFIG_ERROR: "Fix the configuration file and retry.",
    WRITE_BLOCKED: "Deep-Reach is read-only; this command is blocked.",
    BUSY: "Another Deep-Reach query is using the shared browser; retry in a minute.",
}

_MAX_MESSAGE_CHARS = 500


class ReachError(Exception):
    """A failure with a unified code."""

    def __init__(self, code: str, message: str, hint: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint


def _clean(text: object) -> str:
    return str(text).strip()[:_MAX_MESSAGE_CHARS]


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_item(
    *,
    source: Optional[str] = None,
    category: Optional[str] = None,
    platform: Optional[str] = None,
    title: Optional[str] = None,
    url: Optional[str] = None,
    author: Optional[str] = None,
    published_at: Optional[str] = None,
    text: Optional[str] = None,
    parent_id: Optional[str] = None,
    metrics: Optional[dict] = None,
    backend: Optional[str] = None,
    raw: Any = None,
) -> dict:
    """One normalized document. Missing fields are null; `raw` keeps upstream data."""
    return {
        "source": source,
        "category": category,
        "platform": platform,
        "title": title or None,
        "url": url or None,
        "author": author or None,
        "published_at": published_at or None,
        "text": text or None,
        "parent_id": parent_id,
        "metrics": metrics or {},
        "backend": backend,
        "fetched_at": now_iso(),
        "raw": raw,
    }


def envelope(
    *,
    channel: Optional[str],
    action: Optional[str],
    backend: Optional[str] = None,
    tier: Optional[str] = None,
    items: Optional[list] = None,
    elapsed_ms: int = 0,
    attempts: Optional[list] = None,
    error: Optional[ReachError] = None,
) -> dict:
    attempts = list(attempts or [])
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": error is None,
        "channel": channel,
        "action": action,
        "backend": backend if error is None else None,
        "tier": tier if error is None else None,
        "items": list(items or []) if error is None else [],
        "meta": {
            "elapsed_ms": elapsed_ms,
            "attempts": attempts,
            "degraded": any(a.get("result") != "ok" for a in attempts),
        },
        "error": None
        if error is None
        else {
            "code": error.code,
            "message": _clean(error.message),
            "hint": error.hint or DEFAULT_HINTS.get(error.code, ""),
        },
    }


def dump(data: dict, pretty: bool = False) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2 if pretty else None)
