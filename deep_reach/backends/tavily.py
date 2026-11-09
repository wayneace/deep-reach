"""Tavily P2 search and URL extraction."""

from __future__ import annotations

import json

from ..channels.base import BackendSpec, Channel
from ..runtime.dispatch import BACKENDS
from ..runtime.keys import Keys
from ..runtime.result import BAD_INPUT, UPSTREAM_BROKEN, ReachError, make_item
from .p2_common import clamp_limit, p2_fetch_json, require_key

BASE = "https://api.tavily.com"


def _search_items(payload: dict, channel: Channel, spec: BackendSpec) -> list[dict]:
    results = payload.get("results")
    if not isinstance(results, list):
        raise ReachError(UPSTREAM_BROKEN, "tavily returned no results list")
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
                text=str(result.get("content") or "").strip() or None,
                backend=spec.label,
            )
        )
    return items


def register_tavily_backends(keys: Keys) -> None:
    def search(
        *, action: str, params: dict, timeout: float, spec: BackendSpec, channel: Channel
    ) -> list[dict]:
        key = require_key(keys, "search.tavily.api_key", "tavily")
        body = {
            "query": str(params["query"]),
            "max_results": clamp_limit(params.get("limit")),
            "search_depth": "basic",
            "include_answer": False,
        }
        payload = p2_fetch_json(
            f"{BASE}/search",
            timeout=timeout,
            headers={"Authorization": f"Bearer {key}"},
            data=json.dumps(body).encode(),
            method="POST",
        )
        return _search_items(payload, channel, spec)

    def extract(
        *, action: str, params: dict, timeout: float, spec: BackendSpec, channel: Channel
    ) -> list[dict]:
        target = str(params.get("target") or params.get("url") or "").strip()
        if not target:
            raise ReachError(BAD_INPUT, "tavily extract needs target=<url>")
        key = require_key(keys, "search.tavily.api_key", "tavily")
        payload = p2_fetch_json(
            f"{BASE}/extract",
            timeout=timeout,
            headers={"Authorization": f"Bearer {key}"},
            data=json.dumps({"urls": [target], "format": "markdown"}).encode(),
            method="POST",
        )
        results = payload.get("results")
        if not isinstance(results, list) or not results:
            raise ReachError(UPSTREAM_BROKEN, "tavily extract returned no content")
        first = results[0] if isinstance(results[0], dict) else {}
        text = first.get("raw_content")
        if not text:
            raise ReachError(UPSTREAM_BROKEN, "tavily extract returned no content")
        return [
            make_item(
                source=channel.name,
                category=channel.category,
                platform="web",
                title=str(first.get("title") or target),
                url=str(first.get("url") or target),
                text=str(text),
                backend=spec.label,
            )
        ]

    BACKENDS.register("tavily-search", search)
    BACKENDS.register("tavily-extract", extract)
