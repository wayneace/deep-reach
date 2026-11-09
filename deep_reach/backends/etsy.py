"""Etsy Open API v3 (P0): active listing search and listing detail.

Needs a free Etsy app key (`x-api-key`). Public listing endpoints do not need
OAuth. The free tier is 10,000 calls/day.
"""

from __future__ import annotations

import datetime as _dt
import re
from typing import Optional

from ..channels.base import BackendSpec, Channel
from ..runtime import quota
from ..runtime.dispatch import BACKENDS
from ..runtime.keys import Keys
from ..runtime.result import (
    BAD_INPUT,
    KEY_MISSING,
    NOT_FOUND,
    RATE_LIMITED,
    ReachError,
    make_item,
)
from .http import fetch_json

API = "https://openapi.etsy.com/v3/application"
_API_KEY = "official.etsy.api_key"


def _iso(value) -> Optional[str]:
    try:
        stamp = int(value)
    except (TypeError, ValueError):
        return None
    if stamp <= 0:
        return None
    return _dt.datetime.fromtimestamp(stamp, _dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _price(value) -> Optional[float]:
    if not isinstance(value, dict):
        return None
    try:
        return round(float(value.get("amount")) / float(value.get("divisor") or 1), 2)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _headers(keys: Keys) -> dict:
    key = keys.get(_API_KEY)
    if not key:
        raise ReachError(KEY_MISSING, f"{_API_KEY} is missing")
    return {"x-api-key": str(key)}


def _map_error(exc: ReachError) -> ReachError:
    lowered = exc.message.lower()
    if (
        "invalid api key" in lowered
        or "invalid_api_key" in lowered
        or "api key not valid" in lowered
    ):
        return ReachError(KEY_MISSING, exc.message)
    if "rate limit" in lowered or "too many requests" in lowered:
        return ReachError(RATE_LIMITED, exc.message)
    return exc


def _listing(row: dict) -> dict:
    price = row.get("price") or {}
    return make_item(
        source="etsy",
        category="commerce",
        platform="etsy",
        title=row.get("title"),
        url=row.get("url")
        or f"https://www.etsy.com/listing/{row.get('listing_id')}",
        published_at=_iso(
            row.get("creation_timestamp") or row.get("created_timestamp")
        ),
        text=row.get("description"),
        metrics={
            "price": _price(price),
            "currency": price.get("currency_code"),
            "views": row.get("views"),
            "favorites": row.get("num_favorers"),
            "shop_id": row.get("shop_id"),
            "tags": row.get("tags"),
        },
        backend="etsy-api",
        raw=row,
    )


def _search(params: dict, timeout: float, keys: Keys) -> list[dict]:
    quota.reserve("etsy-api", "search")
    limit = min(int(params.get("limit") or 20), 100)
    try:
        payload = fetch_json(
            f"{API}/listings/active",
            timeout=timeout,
            headers=_headers(keys),
            params={"keywords": params["query"], "limit": limit},
        )
    except ReachError as exc:
        raise _map_error(exc) from exc
    return [_listing(row) for row in (payload.get("results") or [])[:limit]]


def _listing_id(target: str) -> str:
    match = re.search(r"/listing/(\d+)", target)
    if match:
        return match.group(1)
    value = target.strip()
    if value.isdigit():
        return value
    raise ReachError(BAD_INPUT, f"expected an Etsy listing id or URL, got {target!r}")


def _read(params: dict, timeout: float, keys: Keys) -> list[dict]:
    quota.reserve("etsy-api", "read")
    listing_id = _listing_id(str(params["target"]))
    try:
        row = fetch_json(
            f"{API}/listings/{listing_id}",
            timeout=timeout,
            headers=_headers(keys),
        )
    except ReachError as exc:
        if exc.code == NOT_FOUND:
            raise
        raise _map_error(exc) from exc
    if not row.get("listing_id") and not row.get("title"):
        raise ReachError(NOT_FOUND, f"Etsy listing {listing_id} not found")
    return [_listing(row)]


def make_etsy_handler(keys: Keys):
    def handler(
        *,
        action: str,
        params: dict,
        timeout: float,
        spec: BackendSpec,
        channel: Channel,
    ) -> list[dict]:
        if action == "search":
            return _search(params, timeout, keys)
        if action == "read":
            return _read(params, timeout, keys)
        raise ReachError(BAD_INPUT, f"etsy-api does not support {action}")

    return handler


def register_etsy_backend(keys: Optional[Keys] = None) -> None:
    BACKENDS.register("etsy-api", make_etsy_handler(keys or Keys({})))
