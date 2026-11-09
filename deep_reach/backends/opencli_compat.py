"""Normalize OpenCLI output and errors.

OpenCLI 2.x commands return a single JSON object:

    {"ok": true, "data": ...}
    {"ok": false, "error": {"code": "...", "message": "...", "hint": "..."}}

Error codes differ by adapter, so map them into Deep-Reach codes.
"""

from __future__ import annotations

import datetime as _dt
import json
from typing import Any, Optional

from ..runtime.result import (
    BAD_INPUT,
    NEED_LOGIN,
    NOT_FOUND,
    PLATFORM_BLOCKED,
    RATE_LIMITED,
    TIMEOUT,
    UPSTREAM_BROKEN,
    WRITE_BLOCKED,
    ReachError,
    make_item,
)


def parse_envelope(text: str) -> dict:
    """Parse one JSON object, tolerating Node warnings before it."""
    start = text.find("{")
    if start < 0:
        raise ReachError(UPSTREAM_BROKEN, f"opencli returned no JSON: {text[:300]}")
    try:
        payload = json.loads(text[start:])
    except json.JSONDecodeError as exc:
        raise ReachError(
            UPSTREAM_BROKEN, f"opencli returned invalid JSON: {exc}: {text[:300]}"
        ) from exc
    if not isinstance(payload, dict):
        raise ReachError(UPSTREAM_BROKEN, "opencli returned a non-object JSON value")
    return payload


def classify_opencli_error(payload: dict, fallback: str = "") -> ReachError:
    err = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    code = str(err.get("code") or "").upper()
    message = str(err.get("message") or fallback or "opencli failed")[:500]
    hint = str(err.get("hint") or err.get("help") or "") or None
    low = message.lower()

    if code in {"WRITE_BLOCKED"}:
        return ReachError(WRITE_BLOCKED, message, hint)
    if code in {"RATE_LIMITED", "RATE_LIMIT"} or "http 429" in low or "too many requests" in low:
        return ReachError(RATE_LIMITED, message, hint)
    if code in {"CAPTCHA_REQUIRED", "ACCOUNT_RISK", "PLATFORM_BLOCKED"} or any(
        word in low
        for word in ("captcha", "验证码", "安全验证", "环境异常", "browser environment", "风控")
    ):
        return ReachError(PLATFORM_BLOCKED, message, hint)
    if code in {"NOT_FOUND"} or "http 404" in low:
        return ReachError(NOT_FOUND, message, hint)
    if code in {"BAD_INPUT", "INVALID_ARGUMENT"}:
        return ReachError(BAD_INPUT, message, hint)
    if code in {"TIMEOUT"} or "timeout" in low:
        return ReachError(TIMEOUT, message, hint)
    if any(word in low for word in ("login", "log in", "sign in", "登录")) or "AUTH" in code:
        return ReachError(NEED_LOGIN, message, hint)
    return ReachError(UPSTREAM_BROKEN, message, hint)


def unix_to_iso(value: Any) -> Optional[str]:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return _dt.datetime.fromtimestamp(seconds, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dict_name(value: Any) -> Optional[str]:
    if isinstance(value, dict):
        for key in ("name", "nickname", "username", "screen_name", "id"):
            if value.get(key):
                return str(value[key])
        return None
    return str(value) if value not in (None, "") else None


def _first(row: dict, *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _metrics(row: dict) -> dict:
    aliases = {
        "likes": ("likes", "like_count", "likeCount", "favorite_count", "attitudes_count"),
        "comments": ("comments", "comment_count", "commentCount", "reply_count"),
        "shares": ("shares", "share_count", "shareCount", "reposts", "repost_count"),
        "views": ("views", "view_count", "viewCount", "play_count", "plays"),
        "favorites": ("favorites", "favorite_count", "collect_count"),
        "danmaku": ("danmaku", "danmaku_count"),
        "rating": ("rating", "rating_value"),
        "reviews": ("reviews", "review_count", "reviewCount"),
        "price": ("price", "price_value"),
        "heat": ("hot_value", "heat", "heat_score"),
    }
    out = {}
    for name, keys in aliases.items():
        value = _first(row, *keys)
        if value is not None:
            out[name] = value
    return out


def _published(row: dict) -> Optional[str]:
    value = _first(
        row,
        "published_at",
        "published",
        "created_at",
        "createdAt",
        "time",
        "date",
        "publish_time",
        "timestamp",
        "pubdate_ts",
        "pubdate",
        "created_utc",
        "created",
    )
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return unix_to_iso(value)
    text = str(value).strip()
    return None if text.lower() in {"", "none", "null"} else text


def extract_rows(data: Any) -> list[dict]:
    """Pull rows out of the common OpenCLI data shapes."""
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if not isinstance(data, dict):
        return []

    rows: list[dict] = []
    for key in ("note", "post", "video", "tweet", "thread", "item", "product"):
        value = data.get(key)
        if isinstance(value, dict):
            rows.append(value)
    for key in (
        "items",
        "results",
        "data",
        "posts",
        "videos",
        "notes",
        "comments",
        "tweets",
        "threads",
        "rows",
        "list",
        "replies",
    ):
        value = data.get(key)
        if isinstance(value, list):
            rows.extend(row for row in value if isinstance(row, dict))
    if rows:
        return rows
    return [data]


def opencli_items(
    data: Any,
    *,
    source: str,
    category: str,
    platform: str,
    backend: str,
) -> list[dict]:
    items = []
    for row in extract_rows(data):
        author = _first(
            row,
            "author",
            "user",
            "username",
            "nickname",
            "screen_name",
            "owner",
            "channel",
            "channel_name",
            "uploader",
            "creator",
        )
        url = _first(
            row,
            "url",
            "link",
            "note_url",
            "share_url",
            "web_url",
            "product_url",
            "canonical_url",
            "permalink",
        )
        if platform == "amazon" and row.get("asin"):
            url = f"https://www.amazon.com/dp/{row['asin']}"
        items.append(
            make_item(
                source=source,
                category=category,
                platform=platform,
                title=_first(row, "title", "name", "word", "topic", "keyword"),
                url=url,
                author=_dict_name(author),
                published_at=_published(row),
                text=_first(
                    row,
                    "text",
                    "content",
                    "desc",
                    "description",
                    "body",
                    "excerpt",
                    "full_text",
                ),
                parent_id=_first(row, "parent_id", "parent", "reply_to", "in_reply_to_id"),
                metrics=_metrics(row),
                backend=backend,
                raw=row,
            )
        )
    return items
