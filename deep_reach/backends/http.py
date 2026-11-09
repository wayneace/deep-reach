"""Direct HTTP: the P0 path for public web pages.

No third-party reader, no browser. Server-rendered pages are read with a plain
GET; pages that need JavaScript fall through to the P2 reader.
"""

from __future__ import annotations

import functools
import gzip
import html
import ipaddress
import json
import os
import re
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass
from typing import Any, Optional

from ..channels.base import BackendSpec, Channel
from ..runtime.dispatch import BACKENDS
from ..runtime.result import (
    BAD_INPUT,
    NOT_FOUND,
    RATE_LIMITED,
    TIMEOUT,
    UPSTREAM_BROKEN,
    ReachError,
    make_item,
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
MAX_BODY = 5_000_000
PRIVATE_URL_ENV = "DEEP_REACH_ALLOW_PRIVATE_URLS"
_TRUTHY = {"1", "true", "yes", "on"}
#: Transparent proxies sometimes resolve public hostnames into these
#: benchmarking ranges. They are not routable on the public internet, so
#: allowing them keeps public reading working behind such proxies without
#: opening loopback, RFC1918, link-local or CGNAT addresses.
_ALLOWED_NON_GLOBAL = (
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("2001:2::/48"),
)


def _allow_private() -> bool:
    return os.environ.get(PRIVATE_URL_ENV, "").strip().lower() in _TRUTHY


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return False
    return True


def _is_public_ip(text: str) -> bool:
    try:
        address = ipaddress.ip_address(str(text).split("%", 1)[0])
    except ValueError:
        return False
    if getattr(address, "ipv4_mapped", None):
        address = address.ipv4_mapped
    if any(address in network for network in _ALLOWED_NON_GLOBAL):
        return True
    return address.is_global


@functools.lru_cache(maxsize=256)
def _host_is_private(host: str) -> bool:
    lowered = host.lower()
    if lowered == "localhost" or lowered.endswith(".localhost"):
        return True
    if _is_ip_literal(host):
        return not _is_public_ip(host)
    try:
        infos = socket.getaddrinfo(host, None)
    except (OSError, UnicodeError):
        # The real request will report a network error; do not turn a DNS
        # failure into a policy failure.
        return False
    return any(not _is_public_ip(info[4][0]) for info in infos)


def validate_url(url: str) -> str:
    """Allow only public http(s) URLs; private addresses need an explicit opt-in."""
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError as exc:
        raise ReachError(BAD_INPUT, f"invalid URL: {exc}") from exc
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ReachError(
            BAD_INPUT,
            f"only http/https URLs are supported, got {scheme or 'no scheme'!r}",
        )
    host = parsed.hostname
    if not host:
        raise ReachError(BAD_INPUT, f"URL has no host: {url!r}")
    if not _is_ip_literal(host):
        try:
            host.encode("idna")
        except UnicodeError as exc:
            raise ReachError(
                BAD_INPUT, f"invalid URL host: {host!r}"
            ) from exc
    if not _allow_private() and _host_is_private(host):
        raise ReachError(
            BAD_INPUT,
            f"refusing to read private or local address {host!r}; "
            f"set {PRIVATE_URL_ENV}=1 to allow it",
        )
    return url

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_DROP_RE = re.compile(r"<(script|style|noscript|svg|template)\b.*?</\1>", re.I | re.S)
_BLOCK_RE = re.compile(
    r"</?(p|div|section|article|main|br|li|tr|h[1-6]|blockquote|pre|td)\b[^>]*>", re.I
)
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"[ \t\r\f\v]+")
_BLANK_RE = re.compile(r"\n{3,}")


def _ssl_context() -> ssl.SSLContext:
    """Use the OS trust store. uv-managed Python ships without a CA bundle."""
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:  # pragma: no cover - fallback for odd environments
        return ssl.create_default_context()


SSL_CONTEXT = _ssl_context()


class _ValidatingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-validate every redirect target, not just the initial URL."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(
    urllib.request.HTTPSHandler(context=SSL_CONTEXT),
    _ValidatingRedirectHandler(),
)


@dataclass
class Response:
    url: str
    status: int
    content_type: str
    text: str


def _decode(raw: bytes, charset: Optional[str]) -> str:
    candidates = [charset, "utf-8", "gb18030"]
    for encoding in candidates:
        if not encoding:
            continue
        try:
            return raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def _http_code(status: int) -> str:
    if status == 404:
        return NOT_FOUND
    if status == 429:
        return RATE_LIMITED
    return UPSTREAM_BROKEN


def fetch(
    url: str,
    *,
    timeout: float,
    headers: Optional[dict] = None,
    accept: str = "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    data: Optional[bytes] = None,
    method: Optional[str] = None,
) -> Response:
    validate_url(url)
    request_headers = {
        "User-Agent": USER_AGENT,
        "Accept": accept,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
    }
    request_headers.update(headers or {})
    request = urllib.request.Request(
        url,
        data=data,
        headers=request_headers,
        method=method or ("POST" if data is not None else "GET"),
    )
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            raw = response.read(MAX_BODY)
            encoding = (response.headers.get("Content-Encoding") or "").lower()
            if "gzip" in encoding:
                raw = gzip.decompress(raw)
            elif "deflate" in encoding:
                raw = zlib.decompress(raw, -zlib.MAX_WBITS)
            content_type = response.headers.get("Content-Type") or ""
            charset = response.headers.get_content_charset()
            return Response(
                url=response.geturl(),
                status=response.status,
                content_type=content_type,
                text=_decode(raw, charset),
            )
    except urllib.error.HTTPError as exc:
        body = exc.read()[:300].decode("utf-8", errors="replace")
        raise ReachError(
            _http_code(exc.code), f"HTTP {exc.code} from {url}: {body}"
        ) from exc
    except urllib.error.URLError as exc:
        reason = str(exc.reason)
        code = TIMEOUT if "timed out" in reason.lower() else UPSTREAM_BROKEN
        raise ReachError(code, f"cannot reach {url}: {reason}") from exc
    except TimeoutError as exc:
        raise ReachError(TIMEOUT, f"request timed out: {url}") from exc


def fetch_json(
    url: str,
    *,
    timeout: float,
    headers: Optional[dict] = None,
    params: Optional[dict] = None,
    data: Optional[bytes] = None,
    method: Optional[str] = None,
) -> Any:
    if params:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{urllib.parse.urlencode(params)}"
    response = fetch(
        url,
        timeout=timeout,
        headers=headers,
        accept="application/json",
        data=data,
        method=method,
    )
    try:
        payload = json.loads(response.text)
    except ValueError as exc:
        raise ReachError(UPSTREAM_BROKEN, f"{url} did not return JSON") from exc
    if not isinstance(payload, (dict, list)):
        raise ReachError(
            UPSTREAM_BROKEN, f"{url} returned an unexpected JSON payload"
        )
    return payload


def html_to_text(raw: str) -> tuple[Optional[str], str]:
    title = None
    match = _TITLE_RE.search(raw)
    if match:
        title = html.unescape(_TAG_RE.sub("", match.group(1))).strip() or None
    body = _DROP_RE.sub(" ", raw)
    body = _BLOCK_RE.sub("\n", body)
    body = _TAG_RE.sub(" ", body)
    body = html.unescape(body)
    body = _SPACE_RE.sub(" ", body)
    body = "\n".join(line.strip() for line in body.splitlines())
    body = _BLANK_RE.sub("\n\n", body).strip()
    return title, body


def make_http_read_handler():
    def handler(
        *,
        action: str,
        params: dict,
        timeout: float,
        spec: BackendSpec,
        channel: Channel,
    ) -> list[dict]:
        target = str(params["target"])
        response = fetch(target, timeout=timeout)
        content_type = response.content_type.lower()
        if "json" in content_type:
            title, body = target, response.text
        elif "html" in content_type or "xml" in content_type:
            title, body = html_to_text(response.text)
            if len(body) < 40:
                raise ReachError(
                    UPSTREAM_BROKEN,
                    "page has too little static text; a renderer is required",
                )
        else:
            title, body = target, response.text
        return [
            make_item(
                source=channel.name,
                category=channel.category,
                platform="web",
                title=title or target,
                url=response.url,
                text=body[:20000],
                backend=spec.label,
            )
        ]

    return handler


def register_http_backends() -> None:
    BACKENDS.register("http-read", make_http_read_handler())
