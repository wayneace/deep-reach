"""GitHub P0 backend: public REST API, optional token.

Unauthenticated requests work at 60 req/h (search 10 req/min). A token raises
the limit to 5,000 req/h; it is optional and never blocks the channel.
"""

from __future__ import annotations

import re
from typing import Optional

from ..channels.base import BackendSpec, Channel
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

API = "https://api.github.com"
_TOKEN_KEY = "official.github.token"

_URL_RE = re.compile(r"github\.com/([^/\s#?]+)/([^/\s#?]+)")
_SLUG_RE = re.compile(r"^([\w.-]+)/([\w.-]+)$")


def _headers(keys: Keys) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "deep-reach",
    }
    token = keys.get(_TOKEN_KEY)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _call(url: str, *, params: dict, timeout: float, keys: Keys):
    try:
        return fetch_json(
            url, timeout=timeout, headers=_headers(keys), params=params
        )
    except ReachError as exc:
        if exc.code == NOT_FOUND:
            raise
        lowered = exc.message.lower()
        if "rate limit" in lowered or "secondary rate" in lowered:
            raise ReachError(RATE_LIMITED, exc.message) from exc
        if "bad credentials" in lowered or "requires authentication" in lowered:
            raise ReachError(KEY_MISSING, exc.message) from exc
        raise


def _repo_slug(target: str) -> str:
    match = _URL_RE.search(target)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    match = _SLUG_RE.match(target.strip())
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    raise ReachError(
        BAD_INPUT, f"expected owner/repo or a GitHub URL, got {target!r}"
    )


def _repo_item(row: dict) -> dict:
    owner = row.get("owner") or {}
    return make_item(
        source="github",
        category="dev",
        platform="github",
        title=row.get("full_name") or row.get("name"),
        url=row.get("html_url"),
        author=owner.get("login"),
        published_at=row.get("pushed_at") or row.get("updated_at"),
        text=row.get("description"),
        metrics={
            "stars": row.get("stargazers_count"),
            "forks": row.get("forks_count"),
            "open_issues": row.get("open_issues_count"),
            "watchers": row.get("watchers_count"),
        },
        backend="github-api",
        raw=row,
    )


def _issue_item(row: dict, repo: str) -> dict:
    user = row.get("user") or {}
    reactions = row.get("reactions") or {}
    return make_item(
        source="github",
        category="dev",
        platform="github",
        title=row.get("title"),
        url=row.get("html_url"),
        author=user.get("login"),
        published_at=row.get("created_at"),
        text=row.get("body"),
        parent_id=repo,
        metrics={
            "comments": row.get("comments"),
            "reactions": reactions.get("total_count"),
        },
        backend="github-api",
        raw=row,
    )


def _search(params: dict, timeout: float, keys: Keys) -> list[dict]:
    limit = min(int(params.get("limit") or 20), 50)
    payload = _call(
        f"{API}/search/repositories",
        params={
            "q": params["query"],
            "sort": "stars",
            "order": "desc",
            "per_page": limit,
        },
        timeout=timeout,
        keys=keys,
    )
    return [_repo_item(row) for row in (payload.get("items") or [])[:limit]]


def _read(params: dict, timeout: float, keys: Keys) -> list[dict]:
    slug = _repo_slug(str(params["target"]))
    payload = _call(
        f"{API}/repos/{slug}", params={}, timeout=timeout, keys=keys
    )
    return [_repo_item(payload)]


def _issues(params: dict, timeout: float, keys: Keys) -> list[dict]:
    limit = min(int(params.get("limit") or 20), 50)
    slug = _repo_slug(str(params["target"]))
    payload = _call(
        f"{API}/repos/{slug}/issues",
        params={
            "state": "all",
            "sort": "updated",
            "direction": "desc",
            "per_page": limit,
        },
        timeout=timeout,
        keys=keys,
    )
    items = []
    for row in payload[:limit]:
        if not isinstance(row, dict) or "pull_request" in row:
            continue
        items.append(_issue_item(row, slug))
    return items


def make_github_handler(keys: Keys):
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
        if action == "issues":
            return _issues(params, timeout, keys)
        raise ReachError(BAD_INPUT, f"github-api does not support {action}")

    return handler


def register_github_backend(keys: Optional[Keys] = None) -> None:
    BACKENDS.register("github-api", make_github_handler(keys or Keys({})))
