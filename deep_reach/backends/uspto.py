"""USPTO Open Data Portal (P0): patent application search.

PatentsView migrated to ODP on 2026-03-20. Its search and APIs were paused as
part of the transition; patentsview.org/apis and api.patentsview.org redirect to
USPTO's transition guide, and search.patentsview.org no longer resolves. ODP is
the official successor and is being expanded (Office Action search, etc.).

Needs a free USPTO API key from https://account.uspto.gov/api-manager/.
The ODP search endpoint accepts a Lucene-like query: boolean operators,
wildcards and exact phrases. No daily call quota is published, so the channel
relies on 429 plus the global rate limits.
"""

from __future__ import annotations

from typing import Optional

from ..channels.base import BackendSpec, Channel
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

API = "https://api.uspto.gov"
_PATH = "/api/v1/patent/applications/search"
_KEY = "official.uspto.odp_api_key"


def _map_error(exc: ReachError) -> ReachError:
    lowered = exc.message.lower()
    if any(
        marker in lowered
        for marker in ("401", "403", "unauthorized", "forbidden", "api key")
    ):
        return ReachError(KEY_MISSING, exc.message)
    if "429" in lowered or "rate limit" in lowered or "too many requests" in lowered:
        return ReachError(RATE_LIMITED, exc.message)
    if "400" in lowered or "bad request" in lowered:
        return ReachError(BAD_INPUT, exc.message)
    return exc


def _date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text


def _item(row: dict) -> dict:
    meta = row.get("applicationMetaData") or {}
    application_number = row.get("applicationNumberText")
    patent_number = meta.get("patentNumber")
    if patent_number:
        url = f"https://patents.google.com/patent/US{patent_number}"
    elif application_number:
        url = f"https://patentcenter.uspto.gov/applications/{application_number}"
    else:
        url = None
    return make_item(
        source="uspto",
        category="patent",
        platform="uspto",
        title=meta.get("inventionTitle"),
        url=url,
        author=meta.get("firstApplicantName") or meta.get("firstInventorName"),
        published_at=_date(
            meta.get("grantDate")
            or meta.get("earliestPublicationDate")
            or meta.get("filingDate")
        ),
        text=meta.get("applicationStatusDescriptionText"),
        metrics={
            "application_number": application_number,
            "patent_number": patent_number,
            "filing_date": _date(meta.get("filingDate")),
            "grant_date": _date(meta.get("grantDate")),
            "status": meta.get("applicationStatusDescriptionText"),
            "status_date": _date(meta.get("applicationStatusDate")),
        },
        backend="uspto-odp",
        raw=row,
    )


def _query(
    q: str,
    limit: int,
    timeout: float,
    keys: Keys,
) -> list[dict]:
    key = keys.get(_KEY)
    if not key:
        raise ReachError(KEY_MISSING, f"{_KEY} is missing")
    try:
        payload = fetch_json(
            f"{API}{_PATH}",
            timeout=timeout,
            headers={"X-API-Key": str(key)},
            params={"q": q, "limit": min(limit, 50), "offset": 0},
        )
    except ReachError as exc:
        if exc.code == NOT_FOUND:
            raise
        raise _map_error(exc) from exc
    rows = payload.get("patentFileWrapperDataBag") or []
    return [_item(row) for row in rows[:limit] if isinstance(row, dict)]


def _search(params: dict, timeout: float, keys: Keys) -> list[dict]:
    return _query(str(params["query"]), int(params.get("limit") or 20), timeout, keys)


def _read(params: dict, timeout: float, keys: Keys) -> list[dict]:
    target = str(params["target"]).strip()
    items = _query(target, 5, timeout, keys)
    if not items:
        raise ReachError(NOT_FOUND, f"USPTO returned nothing for {target}")
    return items[:1]


def make_uspto_handler(keys: Keys):
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
        raise ReachError(BAD_INPUT, f"uspto-odp does not support {action}")

    return handler


def register_uspto_backend(keys: Optional[Keys] = None) -> None:
    BACKENDS.register("uspto-odp", make_uspto_handler(keys or Keys({})))
