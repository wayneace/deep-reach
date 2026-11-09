"""Brave Search P2 backend."""

from __future__ import annotations

from ..channels.base import BackendSpec, Channel
from ..runtime.dispatch import BACKENDS
from ..runtime.keys import Keys
from ..runtime.result import UPSTREAM_BROKEN, ReachError, make_item
from .p2_common import clamp_limit, p2_fetch_json, require_key

BASE = "https://api.search.brave.com/res/v1/web/search"


def register_brave_backend(keys: Keys) -> None:
    def search(
        *, action: str, params: dict, timeout: float, spec: BackendSpec, channel: Channel
    ) -> list[dict]:
        key = require_key(keys, "search.brave.api_key", "brave")
        payload = p2_fetch_json(
            BASE,
            timeout=timeout,
            headers={"X-Subscription-Token": key, "Accept": "application/json"},
            params={
                "q": str(params["query"]),
                "count": clamp_limit(params.get("limit")),
            },
        )
        web = payload.get("web")
        if not isinstance(web, dict):
            raise ReachError(UPSTREAM_BROKEN, "brave returned no web results")
        results = web.get("results") or []
        if not isinstance(results, list):
            raise ReachError(UPSTREAM_BROKEN, "brave returned malformed results")
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
                    text=str(result.get("description") or "").strip() or None,
                    backend=spec.label,
                )
            )
        return items

    BACKENDS.register("brave-search", search)
