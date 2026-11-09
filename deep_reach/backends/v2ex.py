"""V2EX P0 backend: the public v1 API (no token, no browser).

V2EX has no official keyword search endpoint. `hot`, `node`, `read` and
`comments` are the supported surface; search is intentionally absent instead of
silently scraping the HTML search page.
"""

from __future__ import annotations

import datetime as _dt
import html
import re
from typing import Optional

from ..channels.base import BackendSpec, Channel
from ..runtime.dispatch import BACKENDS
from ..runtime.result import BAD_INPUT, NOT_FOUND, ReachError, make_item
from .http import fetch_json

API = "https://www.v2ex.com/api"
_TAG_RE = re.compile(r"<[^>]+>")
_TOPIC_ID_RE = re.compile(r"(?:/t/|topic_id=|[?&]id=)(\d+)")
_NODE_URL_RE = re.compile(r"v2ex\.com/go/([\w-]+)")


def _iso(value) -> Optional[str]:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    if timestamp <= 0:
        return None
    moment = _dt.datetime.fromtimestamp(timestamp, _dt.timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _plain(text) -> Optional[str]:
    if text is None:
        return None
    cleaned = html.unescape(_TAG_RE.sub("", str(text))).strip()
    return cleaned or None


def _topic_id(target: str) -> int:
    match = _TOPIC_ID_RE.search(target)
    if match:
        return int(match.group(1))
    if target.strip().isdigit():
        return int(target.strip())
    raise ReachError(BAD_INPUT, f"expected a V2EX topic id or URL, got {target!r}")


def _node_name(target: str) -> str:
    match = _NODE_URL_RE.search(target)
    if match:
        return match.group(1)
    value = target.strip()
    if re.fullmatch(r"[\w-]+", value):
        return value
    raise ReachError(BAD_INPUT, f"expected a V2EX node name or URL, got {target!r}")


def _topic_item(row: dict) -> dict:
    member = row.get("member") or {}
    node = row.get("node") or {}
    return make_item(
        source="v2ex",
        category="dev",
        platform="v2ex",
        title=row.get("title"),
        url=row.get("url") or f"https://www.v2ex.com/t/{row.get('id')}",
        author=member.get("username"),
        published_at=_iso(row.get("created")),
        text=_plain(row.get("content")) or _plain(row.get("content_rendered")),
        metrics={
            "replies": row.get("replies"),
            "node": node.get("name"),
        },
        backend="v2ex-public",
        raw=row,
    )


def _reply_item(row: dict, topic_id: int) -> dict:
    member = row.get("member") or {}
    return make_item(
        source="v2ex",
        category="dev",
        platform="v2ex",
        url=f"https://www.v2ex.com/t/{topic_id}",
        author=member.get("username"),
        published_at=_iso(row.get("created")),
        text=_plain(row.get("content")) or _plain(row.get("content_rendered")),
        parent_id=str(topic_id),
        metrics={"thanks": row.get("thanks")},
        backend="v2ex-public",
        raw=row,
    )


def _hot(params: dict, timeout: float) -> list[dict]:
    limit = min(int(params.get("limit") or 20), 20)
    payload = fetch_json(f"{API}/topics/hot.json", timeout=timeout)
    return [_topic_item(row) for row in payload[:limit]]


def _node(params: dict, timeout: float) -> list[dict]:
    limit = min(int(params.get("limit") or 20), 20)
    payload = fetch_json(
        f"{API}/topics/show.json",
        timeout=timeout,
        params={"node_name": _node_name(str(params["target"]))},
    )
    return [_topic_item(row) for row in payload[:limit]]


def _read(params: dict, timeout: float) -> list[dict]:
    topic_id = _topic_id(str(params["target"]))
    payload = fetch_json(
        f"{API}/topics/show.json", timeout=timeout, params={"id": topic_id}
    )
    if not payload:
        raise ReachError(NOT_FOUND, f"V2EX topic {topic_id} not found")
    return [_topic_item(payload[0])]


def _comments(params: dict, timeout: float) -> list[dict]:
    limit = min(int(params.get("limit") or 20), 100)
    topic_id = _topic_id(str(params["target"]))
    payload = fetch_json(
        f"{API}/replies/show.json", timeout=timeout, params={"topic_id": topic_id}
    )
    return [_reply_item(row, topic_id) for row in payload[:limit]]


def make_v2ex_handler():
    def handler(
        *,
        action: str,
        params: dict,
        timeout: float,
        spec: BackendSpec,
        channel: Channel,
    ) -> list[dict]:
        if action == "hot":
            return _hot(params, timeout)
        if action == "node":
            return _node(params, timeout)
        if action == "read":
            return _read(params, timeout)
        if action == "comments":
            return _comments(params, timeout)
        raise ReachError(BAD_INPUT, f"v2ex-public does not support {action}")

    return handler


def register_v2ex_backend() -> None:
    BACKENDS.register("v2ex-public", make_v2ex_handler())
