"""EPO Open Patent Services (P0): worldwide patent search.

Needs free OPS credentials (consumer key + secret) from the EPO developer
portal. OPS is the only free official source here that covers US, CN, JP and
EP documents in one query. Free allowance is 4 GB/week, so the channel does not
add a call quota; it relies on 429 and the global rate limits.
"""

from __future__ import annotations

import base64
import re
import urllib.parse
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

AUTH_URL = "https://ops.epo.org/3.2/auth/accesstoken"
SEARCH_URL = "https://ops.epo.org/3.2/rest-services/published-data/search"
_KEY = "official.epo.consumer_key"
_SECRET = "official.epo.consumer_secret"


def _map_error(exc: ReachError) -> ReachError:
    lowered = exc.message.lower()
    if any(
        marker in lowered
        for marker in ("401", "403", "unauthorized", "forbidden", "client identifier")
    ):
        return ReachError(KEY_MISSING, exc.message)
    if "429" in lowered or "rate limit" in lowered or "too many requests" in lowered:
        return ReachError(RATE_LIMITED, exc.message)
    if "400" in lowered or "bad request" in lowered:
        return ReachError(BAD_INPUT, exc.message)
    return exc


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _localized(value) -> Optional[str]:
    items = [item for item in _as_list(value) if isinstance(item, dict)]
    for item in items:
        if str(item.get("@lang") or "").lower().startswith("en") and item.get("$"):
            return str(item["$"])
    for item in items:
        if item.get("$"):
            return str(item["$"])
    return None


def _party_names(parties: dict, group: str, single: str) -> list[str]:
    container = (parties or {}).get(group) or {}
    names = []
    for row in _as_list(container.get(single)):
        if not isinstance(row, dict):
            continue
        name = (row.get("name") or {}).get("$")
        if name:
            names.append(str(name))
    return names


def _date(value) -> Optional[str]:
    if not value:
        return None
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text


def _token(keys: Keys, timeout: float, cache: dict) -> str:
    if cache.get("access_token"):
        return cache["access_token"]
    consumer_key = keys.get(_KEY)
    consumer_secret = keys.get(_SECRET)
    if not (consumer_key and consumer_secret):
        raise ReachError(
            KEY_MISSING, f"{_KEY} and {_SECRET} are both required"
        )
    basic = base64.b64encode(
        f"{consumer_key}:{consumer_secret}".encode("utf-8")
    ).decode("ascii")
    body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode(
        "utf-8"
    )
    try:
        payload = fetch_json(
            AUTH_URL,
            timeout=timeout,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data=body,
            method="POST",
        )
    except ReachError as exc:
        raise _map_error(exc) from exc
    token = payload.get("access_token")
    if not token:
        raise ReachError(UPSTREAM_BROKEN, "EPO OPS token response had no access_token")
    cache["access_token"] = str(token)
    return cache["access_token"]


def _documents(payload: dict) -> tuple[list[dict], int]:
    world = payload.get("ops:world-patent-data") or {}
    search = world.get("ops:biblio-search") or {}
    result = search.get("ops:search-result") or {}
    try:
        total = int(search.get("@total-result-count") or 0)
    except (TypeError, ValueError):
        total = 0
    docs = []
    for wrapper in _as_list(result.get("exchange-documents")):
        if not isinstance(wrapper, dict):
            continue
        for doc in _as_list(wrapper.get("exchange-document")):
            if isinstance(doc, dict):
                docs.append(doc)
    for doc in _as_list(result.get("exchange-document")):
        if isinstance(doc, dict):
            docs.append(doc)
    return docs, total


def _item(doc: dict) -> dict:
    biblio = doc.get("bibliographic-data") or {}
    country = doc.get("@country")
    number = doc.get("@doc-number")
    kind = doc.get("@kind")
    title = _localized(biblio.get("invention-title"))
    dates = []
    publication = biblio.get("publication-reference") or {}
    for document_id in _as_list(publication.get("document-id")):
        if not isinstance(document_id, dict):
            continue
        date = (document_id.get("date") or {}).get("$")
        if date:
            dates.append(str(date))
    published = _date(dates[0]) if dates else None
    parties = biblio.get("parties") or {}
    applicants = _party_names(parties, "applicants", "applicant")
    inventors = _party_names(parties, "inventors", "inventor")
    parts = []
    if applicants:
        parts.append("Applicants: " + ", ".join(applicants))
    if inventors:
        parts.append("Inventors: " + ", ".join(inventors))
    url = (
        f"https://worldwide.espacenet.com/patent/search?q=pn%3D{country}{number}"
        if country and number
        else None
    )
    return make_item(
        source="epo",
        category="patent",
        platform="epo",
        title=title,
        url=url,
        author=applicants[0] if applicants else None,
        published_at=published,
        text="; ".join(parts) or None,
        metrics={
            "country": country,
            "doc_number": number,
            "kind": kind,
            "family_id": doc.get("@family-id"),
            "applicants": applicants,
            "inventors": inventors,
        },
        backend="epo-ops",
        raw=doc,
    )


def _cql(query: str, field: str = "ta") -> str:
    cleaned = query.replace('"', " ").strip()
    return f'{field}="{cleaned}"'


def _search(
    q: str, limit: int, timeout: float, keys: Keys, cache: dict
) -> list[dict]:
    token = _token(keys, timeout, cache)
    try:
        payload = fetch_json(
            SEARCH_URL,
            timeout=timeout,
            headers={"Authorization": f"Bearer {token}"},
            params={"q": q, "Range": f"1-{min(limit, 100)}"},
        )
    except ReachError as exc:
        if exc.code == NOT_FOUND:
            raise
        raise _map_error(exc) from exc
    if payload.get("ops:error") or payload.get("error"):
        message = str(payload.get("ops:error") or payload.get("error"))[:500]
        raise ReachError(UPSTREAM_BROKEN, f"EPO OPS error: {message}")
    docs, _ = _documents(payload)
    return [_item(doc) for doc in docs[:limit]]


def _search_action(params: dict, timeout: float, keys: Keys, cache: dict) -> list[dict]:
    return _search(
        _cql(str(params["query"])),
        int(params.get("limit") or 20),
        timeout,
        keys,
        cache,
    )


def _read_action(params: dict, timeout: float, keys: Keys, cache: dict) -> list[dict]:
    target = re.sub(r"[A-Z]\d?$", "", str(params["target"]).strip().upper())
    items = _search(_cql(target, field="pn"), 1, timeout, keys, cache)
    if not items:
        raise ReachError(NOT_FOUND, f"EPO returned nothing for {params['target']}")
    return items


def make_epo_handler(keys: Keys):
    cache: dict = {}

    def handler(
        *,
        action: str,
        params: dict,
        timeout: float,
        spec: BackendSpec,
        channel: Channel,
    ) -> list[dict]:
        if action == "search":
            return _search_action(params, timeout, keys, cache)
        if action == "read":
            return _read_action(params, timeout, keys, cache)
        raise ReachError(BAD_INPUT, f"epo-ops does not support {action}")

    return handler


def register_epo_backend(keys: Optional[Keys] = None) -> None:
    BACKENDS.register("epo-ops", make_epo_handler(keys or Keys({})))
