"""Product Hunt GraphQL API v2 (P0).

Needs a free developer token. `hot` asks for today's posts ordered by votes.
Without a token the channel falls back to the OpenCLI `posts` adapter (latest
launches), which is not the same as the vote-ranked hot list.
"""

from __future__ import annotations

import datetime as _dt
import json
from typing import Optional

from ..channels.base import BackendSpec, Channel
from ..runtime.dispatch import BACKENDS
from ..runtime.keys import Keys
from ..runtime.result import (
    BAD_INPUT,
    KEY_MISSING,
    RATE_LIMITED,
    UPSTREAM_BROKEN,
    ReachError,
    make_item,
)
from .http import fetch_json

API = "https://api.producthunt.com/v2/api/graphql"
_TOKEN_KEY = "official.producthunt.token"

_HOT_QUERY = """
query Hot($first: Int!, $after: DateTime) {
  posts(order: VOTES, postedAfter: $after, first: $first) {
    edges {
      node {
        id
        name
        tagline
        url
        votesCount
        createdAt
      }
    }
  }
}
"""


def _map_error(exc: ReachError) -> ReachError:
    lowered = exc.message.lower()
    if "unauthorized" in lowered or "invalid token" in lowered or "access token" in lowered:
        return ReachError(KEY_MISSING, exc.message)
    if (
        "rate limit" in lowered
        or "ratelimit" in lowered
        or "throttl" in lowered
        or "too many requests" in lowered
        or "429" in lowered
    ):
        return ReachError(RATE_LIMITED, exc.message)
    return exc


def _headers(keys: Keys) -> dict:
    token = keys.get(_TOKEN_KEY)
    if not token:
        raise ReachError(KEY_MISSING, f"{_TOKEN_KEY} is missing")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _node_item(node: dict) -> dict:
    return make_item(
        source="producthunt",
        category="commerce",
        platform="producthunt",
        title=node.get("name"),
        url=node.get("url"),
        published_at=node.get("createdAt"),
        text=node.get("tagline"),
        metrics={"votes": node.get("votesCount")},
        backend="producthunt-api",
        raw=node,
    )


def _hot(params: dict, timeout: float, keys: Keys) -> list[dict]:
    limit = min(int(params.get("limit") or 20), 50)
    midnight = _dt.datetime.now(_dt.timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    body = json.dumps(
        {
            "query": _HOT_QUERY,
            "variables": {
                "first": limit,
                "after": midnight.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        }
    ).encode("utf-8")
    try:
        payload = fetch_json(
            API,
            timeout=timeout,
            headers=_headers(keys),
            data=body,
            method="POST",
        )
    except ReachError as exc:
        raise _map_error(exc) from exc
    if payload.get("errors"):
        message = " ".join(
            str(error.get("message", ""))
            for error in payload["errors"]
            if isinstance(error, dict)
        )
        raise _map_error(
            ReachError(UPSTREAM_BROKEN, f"Product Hunt GraphQL: {message}")
        )
    edges = ((payload.get("data") or {}).get("posts") or {}).get("edges") or []
    return [_node_item(edge["node"]) for edge in edges if edge.get("node")]


def make_producthunt_handler(keys: Keys):
    def handler(
        *,
        action: str,
        params: dict,
        timeout: float,
        spec: BackendSpec,
        channel: Channel,
    ) -> list[dict]:
        if action == "hot":
            return _hot(params, timeout, keys)
        raise ReachError(BAD_INPUT, f"producthunt-api does not support {action}")

    return handler


def register_producthunt_backend(keys: Optional[Keys] = None) -> None:
    BACKENDS.register(
        "producthunt-api", make_producthunt_handler(keys or Keys({}))
    )
