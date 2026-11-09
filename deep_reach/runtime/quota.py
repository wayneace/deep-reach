"""Daily free-tier quota ledger for P0 API backends.

Agent-Reach has no quota accounting; it waits for a 429. Deep-Reach adds a
small local ledger because the P0 free tiers are the real constraint:

    YouTube Data API   10,000 units/day   search 100, read 1
    eBay Browse         5,000 calls/day
    Etsy Open API      10,000 calls/day

Calls are counted before they are made, so a failed request still spends the
budget. That is deliberately conservative. When the budget is spent the backend
raises QUOTA_EXHAUSTED, which is retryable, so the P1/P2 path takes over.
"""

from __future__ import annotations

import datetime as _dt

from . import state
from .result import QUOTA_EXHAUSTED, ReachError

LIMITS = {
    "youtube-api": {"daily": 10_000, "costs": {"search": 100, "read": 1}},
    "ebay-api": {"daily": 5_000, "costs": {"search": 1, "read": 1}},
    "etsy-api": {"daily": 10_000, "costs": {"search": 1, "read": 1}},
}


def today() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")


def cost_for(backend: str, action: str) -> int:
    entry = LIMITS.get(backend)
    if not entry:
        return 0
    return int(entry["costs"].get(action, 1))


def reserve(backend: str, action: str) -> None:
    entry = LIMITS.get(backend)
    if not entry:
        return
    limit = int(entry["daily"])
    cost = cost_for(backend, action)
    date = today()

    def change(data: dict) -> tuple[int, bool]:
        ledger = data.setdefault("quota", {})
        day = ledger.setdefault(backend, {})
        for key in list(day):
            if key != date:
                day.pop(key, None)
        used = int(day.get(date, 0))
        if used + cost > limit:
            return used, False
        day[date] = used + cost
        return used + cost, True

    used, ok = state.mutate(change)
    if not ok:
        raise ReachError(
            QUOTA_EXHAUSTED,
            f"{backend}: daily free quota {limit} is exhausted ({used} used)",
            hint="The next tier will be used; the free quota resets at 00:00 UTC.",
        )


def report() -> dict:
    saved = state.load().get("quota", {})
    date = today()
    rows = []
    for backend, entry in LIMITS.items():
        limit = int(entry["daily"])
        used = int(saved.get(backend, {}).get(date, 0))
        rows.append(
            {
                "backend": backend,
                "used": used,
                "limit": limit,
                "remaining": max(0, limit - used),
                "percent": round(min(100.0, used * 100.0 / limit), 1) if limit else 0.0,
            }
        )
    return {"date": date, "backends": rows}
