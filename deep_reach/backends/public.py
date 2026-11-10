"""P0 backends: public free interfaces, no browser, no third-party reader.

Each handler maps one platform's public endpoint onto the normalized item
shape. A key is optional and only raises quota; a missing key never blocks the
tier, it just makes the backend unavailable (dispatch skips it).
"""

from __future__ import annotations

import datetime as _dt
import html
import re
from typing import Optional

from ..channels.base import BackendSpec, Channel
from ..runtime import quota
from ..runtime.dispatch import BACKENDS
from ..runtime.keys import Keys
from ..runtime.result import (
    BAD_INPUT,
    KEY_MISSING,
    QUOTA_EXHAUSTED,
    UPSTREAM_BROKEN,
    ReachError,
    make_item,
)
from .http import fetch_json

_TAG_RE = re.compile(r"<[^>]+>")
_BV_RE = re.compile(r"(BV[0-9A-Za-z]{10})")
_AV_RE = re.compile(r"(?:^|/|av)(\d{6,})", re.I)
_YT_ID_RE = re.compile(r"^[0-9A-Za-z_-]{11}$")
_YT_URL_RE = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/)([0-9A-Za-z_-]{11})")


def _iso(timestamp) -> Optional[str]:
    try:
        value = int(timestamp)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    moment = _dt.datetime.fromtimestamp(value, _dt.timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _text(value) -> Optional[str]:
    if value is None:
        return None
    cleaned = html.unescape(_TAG_RE.sub("", str(value))).strip()
    return cleaned or None


def _number(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ── Bilibili public web API ──────────────────────────────────


def _bili_headers() -> dict:
    return {"Referer": "https://www.bilibili.com/", "Origin": "https://www.bilibili.com"}


def _bili_payload(payload: dict, action: str) -> dict:
    if payload.get("code") != 0:
        # -412 / -352 are risk control. Falling through to the browser is the
        # intended behaviour, so this is not a final error.
        raise ReachError(
            UPSTREAM_BROKEN,
            f"bilibili {action} api returned code {payload.get('code')}: "
            f"{payload.get('message') or 'unknown'}",
        )
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def _bili_identifier(target: str) -> dict:
    match = _BV_RE.search(target)
    if match:
        return {"bvid": match.group(1)}
    match = _AV_RE.search(target)
    if match:
        return {"aid": match.group(1)}
    if target.isdigit():
        return {"aid": target}
    raise ReachError(BAD_INPUT, f"cannot find a BV/av id in {target!r}")


def _bili_search(params: dict, timeout: float) -> list[dict]:
    limit = min(int(params.get("limit") or 20), 50)
    payload = fetch_json(
        "https://api.bilibili.com/x/web-interface/search/type",
        timeout=timeout,
        headers=_bili_headers(),
        params={
            "search_type": "video",
            "keyword": params["query"],
            "page": params.get("page") or 1,
            "page_size": limit,
        },
    )
    data = _bili_payload(payload, "search")
    rows = data.get("result") or []
    items = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        bvid = row.get("bvid")
        items.append(
            make_item(
                source="bilibili",
                category="social",
                platform="bilibili",
                title=_text(row.get("title")),
                url=f"https://www.bilibili.com/video/{bvid}" if bvid else None,
                author=row.get("author"),
                published_at=_iso(row.get("pubdate")),
                text=_text(row.get("description")),
                metrics={
                    "views": _number(row.get("play")),
                    "danmaku": _number(row.get("video_review")),
                    "favorites": _number(row.get("favorites")),
                    "comments": _number(row.get("review")),
                },
                backend="bilibili-public",
                raw=row,
            )
        )
    return items


def _bili_view(identifier: dict, timeout: float) -> dict:
    payload = fetch_json(
        "https://api.bilibili.com/x/web-interface/view",
        timeout=timeout,
        headers=_bili_headers(),
        params=identifier,
    )
    return _bili_payload(payload, "view")


def _bili_read(params: dict, timeout: float) -> list[dict]:
    data = _bili_view(_bili_identifier(str(params["target"])), timeout)
    stat = data.get("stat") or {}
    owner = data.get("owner") or {}
    bvid = data.get("bvid")
    return [
        make_item(
            source="bilibili",
            category="social",
            platform="bilibili",
            title=_text(data.get("title")),
            url=f"https://www.bilibili.com/video/{bvid}" if bvid else None,
            author=owner.get("name"),
            published_at=_iso(data.get("pubdate")),
            text=_text(data.get("desc")),
            metrics={
                "views": _number(stat.get("view")),
                "danmaku": _number(stat.get("danmaku")),
                "comments": _number(stat.get("reply")),
                "favorites": _number(stat.get("favorite")),
                "coins": _number(stat.get("coin")),
                "likes": _number(stat.get("like")),
                "duration_seconds": _number(data.get("duration")),
            },
            backend="bilibili-public",
            raw=data,
        )
    ]


def _bili_comments(params: dict, timeout: float) -> list[dict]:
    limit = min(int(params.get("limit") or 20), 49)
    view = _bili_view(_bili_identifier(str(params["target"])), timeout)
    aid = view.get("aid")
    if not aid:
        raise ReachError(UPSTREAM_BROKEN, "bilibili view api returned no aid")
    payload = fetch_json(
        "https://api.bilibili.com/x/v2/reply",
        timeout=timeout,
        headers=_bili_headers(),
        params={"type": 1, "oid": aid, "pn": 1, "ps": limit, "sort": 2},
    )
    data = _bili_payload(payload, "comments")
    items = []
    for row in (data.get("replies") or [])[:limit]:
        if not isinstance(row, dict):
            continue
        member = row.get("member") or {}
        content = row.get("content") or {}
        items.append(
            make_item(
                source="bilibili",
                category="social",
                platform="bilibili",
                title=None,
                url=f"https://www.bilibili.com/video/{view.get('bvid')}",
                author=member.get("uname"),
                published_at=_iso(row.get("ctime")),
                text=_text(content.get("message")),
                parent_id=str(row.get("rpid")) if row.get("rpid") else None,
                metrics={"likes": _number(row.get("like"))},
                backend="bilibili-public",
                raw=row,
            )
        )
    return items


def make_bilibili_handler():
    def handler(
        *,
        action: str,
        params: dict,
        timeout: float,
        spec: BackendSpec,
        channel: Channel,
    ) -> list[dict]:
        if action == "search":
            return _bili_search(params, timeout)
        if action == "read":
            return _bili_read(params, timeout)
        if action == "comments":
            return _bili_comments(params, timeout)
        raise ReachError(BAD_INPUT, f"bilibili-public does not support {action}")

    return handler


def register_public_backends(keys: Optional[Keys] = None) -> None:
    BACKENDS.register("bilibili-public", make_bilibili_handler())
    BACKENDS.register("youtube-api", make_youtube_handler(keys or Keys({})))


# ── YouTube Data API v3 (free quota, key required) ───────────


def _youtube_raise(payload: dict, action: str) -> None:
    error = payload.get("error") or {}
    message = error.get("message") or "unknown error"
    reasons = " ".join(
        str(item.get("reason") or "") for item in error.get("errors") or []
    )
    lowered = f"{message} {reasons}".lower()
    if "quota" in lowered:
        raise ReachError(QUOTA_EXHAUSTED, f"youtube {action}: {message}")
    if "keyinvalid" in lowered or "api key not valid" in lowered:
        raise ReachError(KEY_MISSING, f"youtube {action}: {message}")
    raise ReachError(UPSTREAM_BROKEN, f"youtube {action}: {message}")


def _youtube_get(
    url: str,
    params: dict,
    timeout: float,
    action: str,
    headers: Optional[dict] = None,
) -> dict:
    try:
        payload = fetch_json(
            url, timeout=timeout, params=params, headers=headers
        )
    except ReachError as exc:
        lowered = exc.message.lower()
        if "quota" in lowered:
            raise ReachError(QUOTA_EXHAUSTED, exc.message) from exc
        if "keyinvalid" in lowered or "api key not valid" in lowered:
            raise ReachError(KEY_MISSING, exc.message) from exc
        raise
    if payload.get("error"):
        _youtube_raise(payload, action)
    return payload


def _youtube_id(target: str) -> str:
    match = _YT_URL_RE.search(target)
    if match:
        return match.group(1)
    value = target.strip()
    if _YT_ID_RE.match(value):
        return value
    raise ReachError(BAD_INPUT, f"cannot find a YouTube video id in {target!r}")


def _youtube_search(params: dict, timeout: float, keys: Keys) -> list[dict]:
    limit = min(int(params.get("limit") or 20), 50)
    payload = _youtube_get(
        "https://www.googleapis.com/youtube/v3/search",
        {
            "part": "snippet",
            "type": "video",
            "q": params["query"],
            "maxResults": limit,
        },
        timeout,
        "search",
        headers={"X-Goog-Api-Key": str(keys.get("official.youtube.api_key"))},
    )
    items = []
    for row in payload.get("items") or []:
        video_id = (row.get("id") or {}).get("videoId")
        snippet = row.get("snippet") or {}
        items.append(
            make_item(
                source="youtube",
                category="social",
                platform="youtube",
                title=snippet.get("title"),
                url=f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
                author=snippet.get("channelTitle"),
                published_at=snippet.get("publishedAt"),
                text=snippet.get("description"),
                backend="youtube-api",
                raw=row,
            )
        )
    return items


def _youtube_read(params: dict, timeout: float, keys: Keys) -> list[dict]:
    payload = _youtube_get(
        "https://www.googleapis.com/youtube/v3/videos",
        {
            "part": "snippet,statistics,contentDetails",
            "id": _youtube_id(str(params["target"])),
        },
        timeout,
        "read",
        headers={"X-Goog-Api-Key": str(keys.get("official.youtube.api_key"))},
    )
    items = []
    for row in payload.get("items") or []:
        snippet = row.get("snippet") or {}
        statistics = row.get("statistics") or {}
        items.append(
            make_item(
                source="youtube",
                category="social",
                platform="youtube",
                title=snippet.get("title"),
                url=f"https://www.youtube.com/watch?v={row.get('id')}",
                author=snippet.get("channelTitle"),
                published_at=snippet.get("publishedAt"),
                text=snippet.get("description"),
                metrics={
                    "views": _number(statistics.get("viewCount")),
                    "likes": _number(statistics.get("likeCount")),
                    "comments": _number(statistics.get("commentCount")),
                },
                backend="youtube-api",
                raw=row,
            )
        )
    return items


def make_youtube_handler(keys: Keys):
    def handler(
        *,
        action: str,
        params: dict,
        timeout: float,
        spec: BackendSpec,
        channel: Channel,
    ) -> list[dict]:
        if not keys.get("official.youtube.api_key"):
            raise ReachError(KEY_MISSING, "official.youtube.api_key is missing")
        if action == "search":
            quota.reserve("youtube-api", "search")
            return _youtube_search(params, timeout, keys)
        if action == "read":
            quota.reserve("youtube-api", "read")
            return _youtube_read(params, timeout, keys)
        raise ReachError(BAD_INPUT, f"youtube-api does not support {action}")

    return handler
