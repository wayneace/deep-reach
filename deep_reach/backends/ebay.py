"""eBay Browse API (P0): public item search and item detail.

Needs a free eBay developer app: client_id + client_secret. The OAuth token is
fetched with the client-credentials grant and cached for one CLI process.
"""

from __future__ import annotations

import base64
import re
import urllib.parse
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
    UPSTREAM_BROKEN,
    ReachError,
    make_item,
)
from .http import fetch_json

API = "https://api.ebay.com"
_CLIENT_ID = "official.ebay.client_id"
_CLIENT_SECRET = "official.ebay.client_secret"
_MARKETPLACE = "official.ebay.marketplace"


def _number(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _map_error(exc: ReachError) -> ReachError:
    lowered = exc.message.lower()
    if "invalid_client" in lowered or "invalid client" in lowered or "unauthorized" in lowered:
        return ReachError(KEY_MISSING, exc.message)
    if "rate limit" in lowered or "too many requests" in lowered:
        return ReachError(RATE_LIMITED, exc.message)
    return exc


def _access_token(keys: Keys, timeout: float, cache: dict) -> str:
    if cache.get("access_token"):
        return cache["access_token"]
    client_id = keys.get(_CLIENT_ID)
    client_secret = keys.get(_CLIENT_SECRET)
    if not (client_id and client_secret):
        raise ReachError(
            KEY_MISSING,
            f"{_CLIENT_ID} and {_CLIENT_SECRET} are both required",
        )
    basic = base64.b64encode(
        f"{client_id}:{client_secret}".encode("utf-8")
    ).decode("ascii")
    body = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope",
        }
    ).encode("utf-8")
    try:
        payload = fetch_json(
            f"{API}/identity/v2/oauth2/token",
            timeout=timeout,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data=body,
            method="POST",
        )
    except ReachError as exc:
        raise _map_error(exc) from exc
    token = payload.get("access_token")
    if not token:
        raise ReachError(UPSTREAM_BROKEN, "eBay token response had no access_token")
    cache["access_token"] = str(token)
    return cache["access_token"]


def _headers(token: str, keys: Keys) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": keys.get(_MARKETPLACE) or "EBAY_US",
    }


def _item_summary(row: dict) -> dict:
    price = row.get("price") or {}
    seller = row.get("seller") or {}
    image = row.get("image") or {}
    location = row.get("itemLocation") or {}
    return make_item(
        source="ebay",
        category="commerce",
        platform="ebay",
        title=row.get("title"),
        url=row.get("itemWebUrl"),
        author=seller.get("username"),
        published_at=row.get("itemCreationDate"),
        text=row.get("shortDescription") or row.get("condition"),
        metrics={
            "price": _number(price.get("value")),
            "currency": price.get("currency"),
            "condition": row.get("condition"),
            "country": location.get("country"),
            "image": image.get("imageUrl"),
            "buying_options": row.get("buyingOptions"),
        },
        backend="ebay-api",
        raw=row,
    )


def _search(params: dict, timeout: float, keys: Keys, cache: dict) -> list[dict]:
    quota.reserve("ebay-api", "search")
    token = _access_token(keys, timeout, cache)
    limit = min(int(params.get("limit") or 20), 200)
    try:
        payload = fetch_json(
            f"{API}/buy/browse/v1/item_summary/search",
            timeout=timeout,
            headers=_headers(token, keys),
            params={"q": params["query"], "limit": limit},
        )
    except ReachError as exc:
        raise _map_error(exc) from exc
    return [_item_summary(row) for row in (payload.get("itemSummaries") or [])[:limit]]


def _item_ref(target: str) -> tuple[str, bool]:
    value = target.strip()
    match = re.search(r"/itm/(?:[^/?#]+/)?(\d{6,})", value)
    if match:
        return match.group(1), True
    if re.fullmatch(r"\d{6,}", value):
        return value, True
    if "|" in value:
        return value, False
    raise ReachError(BAD_INPUT, f"expected an eBay item id or URL, got {target!r}")


def _read(params: dict, timeout: float, keys: Keys, cache: dict) -> list[dict]:
    quota.reserve("ebay-api", "read")
    token = _access_token(keys, timeout, cache)
    item_id, legacy = _item_ref(str(params["target"]))
    if legacy:
        url = f"{API}/buy/browse/v1/item/get_item_by_legacy_id"
        query = {"legacy_item_id": item_id}
    else:
        url = f"{API}/buy/browse/v1/item/{urllib.parse.quote(item_id, safe='')}"
        query = {}
    try:
        row = fetch_json(
            url,
            timeout=timeout,
            headers=_headers(token, keys),
            params=query,
        )
    except ReachError as exc:
        if exc.code == NOT_FOUND:
            raise
        raise _map_error(exc) from exc
    if not row.get("itemId") and not row.get("title"):
        raise ReachError(NOT_FOUND, f"eBay item {item_id} not found")
    item = _item_summary(row)
    item["text"] = row.get("description") or item["text"]
    return [item]


def make_ebay_handler(keys: Keys):
    cache: dict = {}

    def handler(
        *,
        action: str,
        params: dict,
        timeout: float,
        spec: BackendSpec,
        channel: Channel,
    ) -> list[dict]:
        if action == "search":
            return _search(params, timeout, keys, cache)
        if action == "read":
            return _read(params, timeout, keys, cache)
        raise ReachError(BAD_INPUT, f"ebay-api does not support {action}")

    return handler


def register_ebay_backend(keys: Optional[Keys] = None) -> None:
    BACKENDS.register("ebay-api", make_ebay_handler(keys or Keys({})))
