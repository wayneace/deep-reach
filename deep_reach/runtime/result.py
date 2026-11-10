"""Unified result envelope and error codes for the agent-facing CLI.

Every command prints exactly one JSON object:

    {schema_version, ok, channel, action, backend, items, meta, error}

Agents branch on `ok` and `error.code`; they should never need to parse
upstream output.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import urllib.parse
from typing import Any, Optional

SCHEMA_VERSION = 1

PLACEHOLDER_VALUES = frozenset(
    {
        "",
        "changeme",
        "change-me",
        "your_key",
        "your-key",
        "placeholder",
        "...",
        "<...>",
    }
)

_SECRET_VALUES: set[str] = set()
_SECRET_PATH_RE = re.compile(
    r"(?:^|[._])(?:api[_-]?key|apikey|api[_-]?token|token|secret|"
    r"client[_-]?secret|consumer[_-]?key|consumer[_-]?secret|password|"
    r"passwd|cookie|access[_-]?key|private[_-]?key|credentials?)$",
    re.IGNORECASE,
)
_SENSITIVE_QUERY_RE = re.compile(
    r"^(key|api[_-]?key|apikey|token|access[_-]?token|secret|password|"
    r"passwd|cookie|auth|signature|sig)$",
    re.IGNORECASE,
)


def is_secret_path(dotted: str) -> bool:
    return bool(_SECRET_PATH_RE.search(dotted))


def register_secret(value: object) -> None:
    if value is None:
        return
    text = str(value).strip()
    if len(text) < 6 or text.lower() in PLACEHOLDER_VALUES:
        return
    _SECRET_VALUES.add(text)


def clear_secrets() -> None:
    _SECRET_VALUES.clear()


def redact_text(text: object) -> str:
    result = str(text)
    for secret in sorted(_SECRET_VALUES, key=len, reverse=True):
        if secret in result:
            result = result.replace(secret, "[redacted]")
    return result


def redact_obj(value: object) -> object:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {
            redact_text(key) if isinstance(key, str) else key: redact_obj(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_obj(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_obj(item) for item in value)
    return value


def sanitize_url(url: str) -> str:
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return redact_text(url)
    if not parts.query:
        return url
    pairs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    cleaned = [
        (name, "[redacted]") if _SENSITIVE_QUERY_RE.match(name) else (name, value)
        for name, value in pairs
    ]
    if cleaned == pairs:
        return url
    return urllib.parse.urlunsplit(
        parts._replace(query=urllib.parse.urlencode(cleaned, doseq=True))
    )

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
NEED_UI = "NEED_UI"
POLICY_BLOCKED = "POLICY_BLOCKED"

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
        NEED_UI,
        POLICY_BLOCKED,
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
    POLICY_BLOCKED,
    NEED_LOGIN,
    NEED_UI,
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

#: The policy attached to a NEED_UI handoff. bsk may use all of its
#: capabilities, including writes; only direct internal-API access is forbidden.
BSK_UI_POLICY = {
    "bsk": "all capabilities, including writes",
    "forbid": [
        "direct fetch/XHR to site internal APIs",
        "debug replay",
        "network calls inside evaluate",
    ],
    "warn": ["debug rule_add", "destructive write actions"],
}

DEFAULT_HINTS = {
    NEED_SETUP: "Run `deep-reach doctor` to see what is missing.",
    NEED_LOGIN: "Log in through the OpenCLI dedicated browser; never share a password.",
    UPSTREAM_BROKEN: "Try the next backend or retry later.",
    TIMEOUT: "Retry later; do not loop.",
    RATE_LIMITED: "Respect the retry window; do not switch accounts.",
    PLATFORM_BLOCKED: "Stop automation and resolve the verification manually.",
    NOT_FOUND: "Check the link or id.",
    BAD_INPUT: "Run `deep-reach channels` to see valid usage.",
    KEY_MISSING: (
        "Run `deep-reach doctor` to see where to add the key; "
        "or use the fallback."
    ),
    QUOTA_EXHAUSTED: "Free-tier quota is exhausted; the fallback will be used.",
    SOURCE_DISABLED: "No backend is available for this source.",
    CONFIG_ERROR: "Fix the configuration file and retry.",
    WRITE_BLOCKED: "This backend does not support this write action.",
    BUSY: "Another Deep-Reach query is using the shared browser; retry in a minute.",
    NEED_UI: (
        "No automatic backend can complete this action. Use `deep-reach bsk ...` "
        "(guarded); bsk may use all capabilities, including writes. Do not fetch "
        "site internal APIs directly; confirm user intent before destructive writes."
    ),
    POLICY_BLOCKED: (
        "The bsk guard blocked a direct internal-API call. Use observe/click/"
        "extract/network reads instead of fetch/XHR or debug replay."
    ),
}

_MAX_MESSAGE_CHARS = 500


class ReachError(Exception):
    """A failure with a unified code."""

    def __init__(self, code: str, message: str, hint: Optional[str] = None):
        self.code = code
        self.message = redact_text(message)
        self.hint = redact_text(hint) if hint else hint
        super().__init__(self.message)


def _clean(text: object) -> str:
    return redact_text(str(text).strip()[:_MAX_MESSAGE_CHARS])


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
    extra_meta: Optional[dict] = None,
) -> dict:
    attempts = list(attempts or [])
    meta = {
        "elapsed_ms": elapsed_ms,
        "attempts": attempts,
        "degraded": any(a.get("result") != "ok" for a in attempts),
    }
    if extra_meta:
        meta.update(extra_meta)
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": error is None,
        "channel": channel,
        "action": action,
        "backend": backend if error is None else None,
        "tier": tier,
        "items": list(items or []) if error is None else [],
        "meta": meta,
        "error": None
        if error is None
        else {
            "code": error.code,
            "message": _clean(error.message),
            "hint": error.hint or DEFAULT_HINTS.get(error.code, ""),
        },
    }


def dump(data: dict, pretty: bool = False) -> str:
    return json.dumps(redact_obj(data), ensure_ascii=False, indent=2 if pretty else None)
