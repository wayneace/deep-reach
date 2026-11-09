"""Bright Data SERP and Web Unlocker P2 backends."""

from __future__ import annotations

import json
import urllib.parse

from ..channels.base import BackendSpec, Channel
from ..runtime.dispatch import BACKENDS
from ..runtime.keys import Keys
from ..runtime.result import BAD_INPUT, UPSTREAM_BROKEN, ReachError, make_item
from .http import html_to_text, validate_url
from .p2_common import clamp_limit, p2_fetch_json, require_key

BASE = "https://api.brightdata.com/request"


def _unwrap(payload: object) -> object:
    if isinstance(payload, dict) and isinstance(payload.get("body"), str):
        try:
            return json.loads(payload["body"])
        except ValueError as exc:
            raise ReachError(
                UPSTREAM_BROKEN, "brightdata returned a non-JSON body"
            ) from exc
    return payload


def _serp_items(payload: object, channel: Channel, spec: BackendSpec) -> list[dict]:
    raw = _unwrap(payload)
    if not isinstance(raw, dict):
        raise ReachError(UPSTREAM_BROKEN, "brightdata SERP returned malformed data")
    organic = raw.get("organic")
    if organic is None:
        organic = raw.get("organic_results")
    if organic is None:
        organic = raw.get("results")
    if not isinstance(organic, list):
        raise ReachError(UPSTREAM_BROKEN, "brightdata SERP returned no organic results")

    items = []
    for entry in organic:
        if not isinstance(entry, dict):
            continue
        url = entry.get("link") or entry.get("url")
        title = entry.get("title")
        text = entry.get("description") or entry.get("snippet")
        if not (url or title):
            continue
        items.append(
            make_item(
                source=channel.name,
                category=channel.category,
                platform="web",
                title=str(title or "").strip() or None,
                url=str(url or "").strip() or None,
                text=str(text or "").strip() or None,
                backend=spec.label,
            )
        )
    return items


def register_brightdata_backends(keys: Keys) -> None:
    def serp(
        *, action: str, params: dict, timeout: float, spec: BackendSpec, channel: Channel
    ) -> list[dict]:
        token = require_key(keys, "search.brightdata.api_token", "brightdata")
        zone = require_key(keys, "search.brightdata.serp_zone", "brightdata SERP")
        query = urllib.parse.quote_plus(str(params["query"]))
        target = f"https://www.google.com/search?q={query}&brd_json=json"
        body = {"zone": zone, "url": target, "format": "raw"}
        payload = p2_fetch_json(
            BASE,
            timeout=timeout,
            headers={"Authorization": f"Bearer {token}"},
            data=json.dumps(body).encode(),
            method="POST",
        )
        return _serp_items(payload, channel, spec)[: clamp_limit(params.get("limit"))]

    def unlocker(
        *, action: str, params: dict, timeout: float, spec: BackendSpec, channel: Channel
    ) -> list[dict]:
        target = str(params.get("target") or params.get("url") or "").strip()
        if not target:
            raise ReachError(BAD_INPUT, "brightdata unlocker needs target=<url>")
        validate_url(target)
        token = require_key(keys, "search.brightdata.api_token", "brightdata")
        zone = require_key(
            keys, "search.brightdata.unlocker_zone", "brightdata Unlocker"
        )
        body = {"zone": zone, "url": target, "format": "raw"}
        payload = p2_fetch_json(
            BASE,
            timeout=timeout,
            headers={"Authorization": f"Bearer {token}"},
            data=json.dumps(body).encode(),
            method="POST",
        )
        if not isinstance(payload, dict):
            raise ReachError(UPSTREAM_BROKEN, "brightdata unlocker returned no body")
        status = payload.get("status_code")
        if isinstance(status, int) and status >= 400:
            raise ReachError(
                UPSTREAM_BROKEN, f"brightdata unlocker target HTTP {status}"
            )
        html = payload.get("body")
        if not isinstance(html, str) or not html.strip():
            raise ReachError(UPSTREAM_BROKEN, "brightdata unlocker returned no body")
        title, text = html_to_text(html)
        if len(text.strip()) < 40:
            raise ReachError(
                UPSTREAM_BROKEN, "page has too little text after unlocking"
            )
        return [
            make_item(
                source=channel.name,
                category=channel.category,
                platform="web",
                title=title or target,
                url=target,
                text=text[:20000],
                backend=spec.label,
            )
        ]

    BACKENDS.register("brightdata-serp", serp)
    BACKENDS.register("brightdata-unlocker", unlocker)
