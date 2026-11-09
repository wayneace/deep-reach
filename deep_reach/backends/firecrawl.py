"""Firecrawl P2 search and page scraping (v2 API)."""

from __future__ import annotations

import json

from ..channels.base import BackendSpec, Channel
from ..runtime.dispatch import BACKENDS
from ..runtime.keys import Keys
from ..runtime.result import BAD_INPUT, UPSTREAM_BROKEN, ReachError, make_item
from .p2_common import clamp_limit, p2_fetch_json, require_key

BASE = "https://api.firecrawl.dev/v2"


def _search_items(payload: dict, channel: Channel, spec: BackendSpec) -> list[dict]:
    if payload.get("success") is False:
        raise ReachError(
            UPSTREAM_BROKEN,
            f"firecrawl search failed: {payload.get('error') or 'unknown error'}",
        )
    data = payload.get("data")
    if isinstance(data, dict):
        results = data.get("web") or []
    elif isinstance(data, list):
        # Older v1 response shape.
        results = data
    else:
        raise ReachError(UPSTREAM_BROKEN, "firecrawl returned no search data")
    if not isinstance(results, list):
        raise ReachError(UPSTREAM_BROKEN, "firecrawl returned malformed search data")
    items = []
    for result in results:
        if not isinstance(result, dict):
            continue
        items.append(
            make_item(
                source=channel.name,
                category=channel.category,
                platform="web",
                title=str(result.get("title") or "").strip() or None,
                url=str(result.get("url") or "").strip() or None,
                text=str(
                    result.get("description") or result.get("markdown") or ""
                ).strip()
                or None,
                backend=spec.label,
            )
        )
    return items


def register_firecrawl_backends(keys: Keys) -> None:
    def search(
        *, action: str, params: dict, timeout: float, spec: BackendSpec, channel: Channel
    ) -> list[dict]:
        key = require_key(keys, "search.firecrawl.api_key", "firecrawl")
        body = {
            "query": str(params["query"]),
            "limit": clamp_limit(params.get("limit")),
        }
        payload = p2_fetch_json(
            f"{BASE}/search",
            timeout=timeout,
            headers={"Authorization": f"Bearer {key}"},
            data=json.dumps(body).encode(),
            method="POST",
        )
        return _search_items(payload, channel, spec)

    def scrape(
        *, action: str, params: dict, timeout: float, spec: BackendSpec, channel: Channel
    ) -> list[dict]:
        target = str(params.get("target") or params.get("url") or "").strip()
        if not target:
            raise ReachError(BAD_INPUT, "firecrawl scrape needs target=<url>")
        key = require_key(keys, "search.firecrawl.api_key", "firecrawl")
        payload = p2_fetch_json(
            f"{BASE}/scrape",
            timeout=timeout,
            headers={"Authorization": f"Bearer {key}"},
            data=json.dumps({"url": target, "formats": ["markdown"]}).encode(),
            method="POST",
        )
        if payload.get("success") is False:
            raise ReachError(
                UPSTREAM_BROKEN,
                f"firecrawl scrape failed: {payload.get('error') or 'unknown error'}",
            )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ReachError(UPSTREAM_BROKEN, "firecrawl returned no scrape data")
        text = data.get("markdown") or data.get("content")
        if not text:
            raise ReachError(UPSTREAM_BROKEN, "firecrawl returned no markdown")
        metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        return [
            make_item(
                source=channel.name,
                category=channel.category,
                platform="web",
                title=str(metadata.get("title") or target),
                url=str(metadata.get("sourceURL") or target),
                text=str(text),
                backend=spec.label,
            )
        ]

    BACKENDS.register("firecrawl-search", search)
    BACKENDS.register("firecrawl-scrape", scrape)
