"""Shared helpers for P2 third-party search and reader backends."""

from __future__ import annotations

from typing import Any

from ..runtime.keys import Keys
from ..runtime.result import NEED_SETUP, QUOTA_EXHAUSTED, ReachError
from .http import fetch_json

P2_CODE_MAP = {
    401: NEED_SETUP,
    402: QUOTA_EXHAUSTED,
    403: NEED_SETUP,
    429: QUOTA_EXHAUSTED,
}


def p2_fetch_json(
    url: str, *, timeout: float, headers=None, params=None, data=None, method=None
) -> Any:
    if data is not None:
        headers = dict(headers or {})
        headers.setdefault("Content-Type", "application/json")
    return fetch_json(
        url,
        timeout=timeout,
        headers=headers,
        params=params,
        data=data,
        method=method,
        code_map=P2_CODE_MAP,
    )


def clamp_limit(value: object, default: int = 10, maximum: int = 20) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(1, min(number, maximum))


def require_key(keys: Keys, path: str, label: str) -> str:
    value = keys.get(path)
    if not value:
        raise ReachError(NEED_SETUP, f"{label} needs {path}")
    return str(value)
