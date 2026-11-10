"""Xueqiu, following Agent-Reach's orchestration.

    quote      Tencent quote  -> Xueqiu v5 quote  -> OpenCLI
    search     Tencent smartbox -> Xueqiu search  -> OpenCLI
    hot        Xueqiu public timeline (session)   -> OpenCLI
    hot_stocks Xueqiu hot stock list (session)

Tencent is the first choice for quotes and lookup because it needs no cookie.
Xueqiu's own API is the fallback and the only source for community data; it
needs `xueqiu.cookie` in keys.yaml, copied from a logged-in browser. The cookie
expires within hours and is never written to state or output.
"""

from __future__ import annotations

import http.cookiejar
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from ..channels.base import BackendSpec, Channel
from ..runtime.dispatch import BACKENDS
from ..runtime.keys import Keys
from ..runtime.result import (
    BAD_INPUT,
    NEED_LOGIN,
    NOT_FOUND,
    RATE_LIMITED,
    TIMEOUT,
    UPSTREAM_BROKEN,
    ReachError,
    make_item,
)
from .http import SSL_CONTEXT, ValidatedRedirectHandler, fetch

COOKIE_KEY = "xueqiu.cookie"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_REFERER = "https://xueqiu.com/"
_LOGIN_HINT = (
    f"Fill {COOKIE_KEY} in ~/.deep-reach/keys.yaml with a Cookie copied from a "
    "logged-in xueqiu.com browser tab; never share a password."
)

_TENCENT_A = re.compile(r"(SH|SZ|BJ)\d{6}")
_TENCENT_HK = re.compile(r"HK\d{1,5}")
_TENCENT_US = re.compile(r"[A-Z][A-Z.\-]{0,9}")


def _tencent_code(symbol: str) -> str:
    value = str(symbol).strip().upper()
    if _TENCENT_A.fullmatch(value):
        return value.lower()
    if re.fullmatch(r"\d{6}", value):
        if value.startswith("920"):
            return "bj" + value
        prefix = "sh" if value[0] in "69" else ("bj" if value[0] in "48" else "sz")
        return prefix + value
    if _TENCENT_HK.fullmatch(value):
        return "hk" + value[2:].zfill(5)
    if re.fullmatch(r"\d{1,5}", value):
        return "hk" + value.zfill(5)
    if _TENCENT_US.fullmatch(value):
        return "us" + value
    raise ReachError(
        BAD_INPUT, "symbol must look like SH600519, 600519, 00700 or AAPL"
    )


def _xueqiu_symbol(code: str) -> str:
    market, body = code[:2].lower(), code[2:]
    if market in ("sh", "sz", "bj"):
        return market.upper() + body
    if market == "hk":
        return body
    return body.split(".")[0].upper()


def _number(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _quote_time(value: str) -> Optional[str]:
    import datetime as _dt

    match = re.fullmatch(r"(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", value.strip())
    if not match:
        return None
    year, month, day, hour, minute, second = (int(part) for part in match.groups())
    try:
        moment = _dt.datetime(
            year,
            month,
            day,
            hour,
            minute,
            second,
            tzinfo=_dt.timezone(_dt.timedelta(hours=8)),
        )
    except ValueError:
        return None
    return moment.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class _Session:
    """Cookie-aware opener. Injects xueqiu.cookie or picks up acw_tc."""

    def __init__(self, keys: Keys):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
            urllib.request.HTTPSHandler(context=SSL_CONTEXT),
            ValidatedRedirectHandler(),
        )
        self._cookie = keys.get(COOKIE_KEY)
        self._initialized = False

    def _inject(self) -> None:
        if not self._cookie:
            return
        for pair in str(self._cookie).split(";"):
            pair = pair.strip()
            if "=" not in pair:
                continue
            name, _, value = pair.partition("=")
            self.jar.set_cookie(
                http.cookiejar.Cookie(
                    version=0,
                    name=name.strip(),
                    value=value.strip(),
                    port=None,
                    port_specified=False,
                    domain=".xueqiu.com",
                    domain_specified=True,
                    domain_initial_dot=True,
                    path="/",
                    path_specified=True,
                    secure=True,
                    expires=None,
                    discard=True,
                    comment=None,
                    comment_url=None,
                    rest={},
                )
            )

    def has_login(self) -> bool:
        return any(cookie.name == "xq_a_token" for cookie in self.jar)

    def _ensure(self, timeout: float) -> None:
        if self._initialized:
            return
        self._inject()
        if not self.has_login():
            # Public quote/search sometimes work with only the anti-DDoS cookie.
            request = urllib.request.Request(
                _REFERER, headers={"User-Agent": _UA}
            )
            try:
                with self.opener.open(request, timeout=min(max(timeout, 0.1), 10)) as response:
                    response.read(2048)
            except Exception:  # noqa: BLE001 - the real request reports the failure
                pass
        self._initialized = True

    def get_json(self, url: str, timeout: float):
        self._ensure(timeout)
        request = urllib.request.Request(
            url, headers={"User-Agent": _UA, "Referer": _REFERER}
        )
        try:
            with self.opener.open(request, timeout=max(0.1, timeout)) as response:
                raw = response.read(5_000_000)
        except urllib.error.HTTPError as exc:
            body = exc.read()[:500].decode("utf-8", errors="replace")
            code = _error_code(body)
            if exc.code == 401 or code == "400016":
                raise ReachError(
                    NEED_LOGIN, "Xueqiu requires a logged-in session", hint=_LOGIN_HINT
                ) from exc
            if exc.code == 429:
                raise ReachError(RATE_LIMITED, "Xueqiu rate limited this request") from exc
            if exc.code == 404:
                raise ReachError(NOT_FOUND, "Xueqiu returned 404") from exc
            raise ReachError(
                UPSTREAM_BROKEN, f"Xueqiu HTTP {exc.code}: {body}"
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ReachError(TIMEOUT, f"Xueqiu request failed: {exc}") from exc
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError as exc:
            raise ReachError(UPSTREAM_BROKEN, "Xueqiu returned unreadable JSON") from exc


def _error_code(body: str) -> str:
    try:
        return str(json.loads(body).get("error_code", ""))
    except (TypeError, ValueError):
        return ""


def _require_login(session: _Session) -> None:
    if not session.has_login():
        raise ReachError(
            NEED_LOGIN, "Xueqiu community data needs a session cookie", hint=_LOGIN_HINT
        )


# ── Tencent: quote and lookup, no cookie ─────────────────────


def _tencent_quote(params: dict, timeout: float) -> list[dict]:
    code = _tencent_code(str(params["target"]))
    response = fetch(f"https://qt.gtimg.cn/q={code}", timeout=timeout, accept="text/plain")
    match = re.search(r'="([^"]*)"', response.text)
    if not match:
        raise ReachError(UPSTREAM_BROKEN, "Tencent quote returned an unknown format")
    fields = match.group(1).split("~")
    if len(fields) < 35:
        raise ReachError(NOT_FOUND, f"no quote for {params['target']}")
    name = fields[1] or code
    xueqiu_symbol = _xueqiu_symbol(code)
    price = _number(fields[3])
    change = _number(fields[31]) if len(fields) > 31 else None
    percent = _number(fields[32]) if len(fields) > 32 else None
    return [
        make_item(
            source="xueqiu",
            category="social",
            platform="tencent-quote",
            title=f"{name} {xueqiu_symbol}",
            url=f"https://xueqiu.com/S/{xueqiu_symbol}",
            published_at=_quote_time(fields[30]) if len(fields) > 30 else None,
            text=f"{name} {price if price is not None else '-'} "
            f"({percent if percent is not None else '-'}%)",
            metrics={
                "price": price,
                "previous_close": _number(fields[4]),
                "open": _number(fields[5]),
                "high": _number(fields[33]),
                "low": _number(fields[34]),
                "change": change,
                "change_percent": percent,
                "volume": _number(fields[36]) if len(fields) > 36 else None,
                "amount_wan": _number(fields[37]) if len(fields) > 37 else None,
                "turnover_percent": _number(fields[38]) if len(fields) > 38 else None,
                "pe": _number(fields[39]) if len(fields) > 39 else None,
            },
            backend="tencent-quote",
            raw={"symbol": code, "fields": fields},
        )
    ]


def _parse_smartbox(text: str) -> list[dict]:
    match = re.search(r'="([^"]*)"', text)
    if not match or match.group(1) in ("", "N"):
        return []
    try:
        payload = json.loads(f'"{match.group(1)}"')
    except ValueError:
        return []
    rows = []
    for entry in payload.split("^"):
        parts = entry.split("~")
        if len(parts) < 3 or not parts[0] or not parts[1]:
            continue
        rows.append(
            {
                "market": parts[0].lower(),
                "code": parts[1],
                "name": parts[2],
                "type": parts[4] if len(parts) > 4 else None,
            }
        )
    return rows


def _tencent_search(params: dict, timeout: float) -> list[dict]:
    limit = min(int(params.get("limit") or 5), 20)
    query = urllib.parse.quote(str(params["query"]))
    response = fetch(
        f"https://smartbox.gtimg.cn/s3/?v=2&q={query}&t=all",
        timeout=timeout,
        accept="text/plain",
    )
    items = []
    for row in _parse_smartbox(response.text)[:limit]:
        xueqiu_symbol = _xueqiu_symbol(row["market"] + row["code"])
        items.append(
            make_item(
                source="xueqiu",
                category="social",
                platform="tencent-search",
                title=f"{row['name']} ({xueqiu_symbol})",
                url=f"https://xueqiu.com/S/{xueqiu_symbol}",
                text=row["name"],
                metrics={"type": row["type"]},
                backend="tencent-search",
                raw=row,
            )
        )
    return items


# ── Xueqiu API: fallback and community data ──────────────────


def _api_quote(session: _Session, params: dict, timeout: float) -> list[dict]:
    symbol = _xueqiu_symbol(_tencent_code(str(params["target"])))
    payload = session.get_json(
        "https://stock.xueqiu.com/v5/stock/quote.json"
        f"?symbol={urllib.parse.quote(symbol)}&extend=detail",
        timeout,
    )
    quote = (payload.get("data") or {}).get("quote")
    if not quote:
        raise ReachError(NOT_FOUND, f"no Xueqiu quote for {params['target']}")
    return [
        make_item(
            source="xueqiu",
            category="social",
            platform="xueqiu",
            title=f"{quote.get('name')} ({quote.get('symbol')})",
            url=f"https://xueqiu.com/S/{quote.get('symbol')}",
            published_at=quote.get("timestamp"),
            text=f"{quote.get('name')} {quote.get('current')} ({quote.get('percent')}%)",
            metrics={
                "price": quote.get("current"),
                "change": quote.get("chg"),
                "change_percent": quote.get("percent"),
                "open": quote.get("open"),
                "high": quote.get("high"),
                "low": quote.get("low"),
                "previous_close": quote.get("last_close"),
                "volume": quote.get("volume"),
                "amount": quote.get("amount"),
                "pe_ttm": quote.get("pe_ttm"),
                "market_capital": quote.get("market_capital"),
                "turnover_percent": quote.get("turnover_rate"),
            },
            backend="xueqiu-api",
            raw=quote,
        )
    ]


def _api_search(session: _Session, params: dict, timeout: float) -> list[dict]:
    limit = min(int(params.get("limit") or 10), 20)
    payload = session.get_json(
        "https://xueqiu.com/stock/search.json"
        f"?code={urllib.parse.quote(str(params['query']))}&size={limit}",
        timeout,
    )
    items = []
    for row in (payload.get("stocks") or [])[:limit]:
        items.append(
            make_item(
                source="xueqiu",
                category="social",
                platform="xueqiu",
                title=f"{row.get('name')} ({row.get('code')})",
                url=f"https://xueqiu.com/S/{row.get('code')}",
                text=row.get("name"),
                backend="xueqiu-api",
                raw=row,
            )
        )
    return items


def _parse_hot_posts(payload: dict, limit: int) -> list[dict]:
    items = []
    for entry in (payload.get("list") or [])[:limit]:
        try:
            post = json.loads(entry["data"]) if isinstance(entry.get("data"), str) else {}
        except (json.JSONDecodeError, KeyError):
            post = {}
        user = post.get("user") or {}
        text = re.sub(r"<[^>]+>", "", str(post.get("text") or post.get("description") or ""))
        target = post.get("target") or ""
        items.append(
            make_item(
                source="xueqiu",
                category="social",
                platform="xueqiu",
                title=post.get("title") or (text[:60] or None),
                url=f"https://xueqiu.com{target}" if target else None,
                author=user.get("screen_name"),
                text=text[:2000],
                metrics={"likes": post.get("like_count")},
                backend="xueqiu-api",
                raw=post,
            )
        )
    return items


def _api_hot(session: _Session, params: dict, timeout: float) -> list[dict]:
    _require_login(session)
    limit = min(int(params.get("limit") or 10), 50)
    payload = session.get_json(
        "https://xueqiu.com/v4/statuses/public_timeline_by_category.json"
        f"?since_id=-1&max_id=-1&count={limit}&category=-1",
        timeout,
    )
    return _parse_hot_posts(payload, limit)


def _api_hot_stocks(session: _Session, params: dict, timeout: float) -> list[dict]:
    _require_login(session)
    limit = min(int(params.get("limit") or 10), 50)
    payload = session.get_json(
        "https://stock.xueqiu.com/v5/stock/hot_stock/list.json"
        f"?size={limit}&type=10",
        timeout,
    )
    rows = ((payload.get("data") or {}).get("items") or [])[:limit]
    items = []
    for row in rows:
        symbol = row.get("code") or row.get("symbol")
        items.append(
            make_item(
                source="xueqiu",
                category="social",
                platform="xueqiu",
                title=f"{row.get('name')} ({symbol})",
                url=f"https://xueqiu.com/S/{symbol}" if symbol else None,
                text=f"{row.get('name')} {row.get('current')} ({row.get('percent')}%)",
                metrics={
                    "price": row.get("current"),
                    "change_percent": row.get("percent"),
                },
                backend="xueqiu-api",
                raw=row,
            )
        )
    return items


def make_xueqiu_handler(keys: Keys):
    session = _Session(keys)

    def handler(
        *,
        action: str,
        params: dict,
        timeout: float,
        spec: BackendSpec,
        channel: Channel,
    ) -> list[dict]:
        if spec.label == "tencent-quote":
            if action != "quote":
                raise ReachError(BAD_INPUT, f"tencent-quote does not support {action}")
            return _tencent_quote(params, timeout)
        if spec.label == "tencent-search":
            if action != "search":
                raise ReachError(BAD_INPUT, f"tencent-search does not support {action}")
            return _tencent_search(params, timeout)
        if spec.label == "xueqiu-api":
            if action == "quote":
                return _api_quote(session, params, timeout)
            if action == "search":
                return _api_search(session, params, timeout)
            if action == "hot":
                return _api_hot(session, params, timeout)
            if action == "hot_stocks":
                return _api_hot_stocks(session, params, timeout)
            raise ReachError(BAD_INPUT, f"xueqiu-api does not support {action}")
        raise ReachError(BAD_INPUT, f"unknown Xueqiu backend {spec.label}")

    return handler


def register_xueqiu_backends(keys: Optional[Keys] = None) -> None:
    handler = make_xueqiu_handler(keys or Keys({}))
    for label in ("tencent-quote", "tencent-search", "xueqiu-api"):
        BACKENDS.register(label, handler)
