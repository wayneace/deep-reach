"""Direct HTTP: the P0 path for public web pages.

No third-party reader, no browser. Server-rendered pages are read with a plain
GET; pages that need JavaScript fall through to the P2 reader.
"""

from __future__ import annotations

import functools
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
    sanitize_url,
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
MAX_BODY = 5_000_000
MAX_DECOMPRESSED = 10_000_000
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


_SENSITIVE_HEADER_RE = re.compile(
    r"(authorization|cookie|token|secret|key|auth)", re.IGNORECASE
)
_SENSITIVE_REDIRECT_QUERY_RE = re.compile(
    r"^(key|api[_-]?key|token|access_token|secret|password|cookie|"
    r"auth|signature|sig)$",
    re.IGNORECASE,
)


def _origin(url: str) -> tuple[str, str, Optional[int]]:
    parts = urllib.parse.urlsplit(url)
    scheme = parts.scheme.lower()
    default_port = 443 if scheme == "https" else 80 if scheme == "http" else None
    return (scheme, (parts.hostname or "").lower(), parts.port or default_port)


def _strip_sensitive_headers(headers: dict) -> dict:
    return {
        name: value
        for name, value in headers.items()
        if not _SENSITIVE_HEADER_RE.search(name)
    }


def _strip_sensitive_query(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    pairs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    kept = [
        (name, value)
        for name, value in pairs
        if not _SENSITIVE_REDIRECT_QUERY_RE.match(name)
    ]
    if len(kept) == len(pairs):
        return url
    return urllib.parse.urlunsplit(
        parts._replace(query=urllib.parse.urlencode(kept, doseq=True))
    )


class ValidatedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Validate redirects and strip credentials when the origin changes."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            urllib.parse.urlsplit(newurl).port
        except ValueError:
            raise ReachError(
                BAD_INPUT, f"invalid redirect URL: {sanitize_url(newurl)}"
            ) from None
        validate_url(newurl)
        request = super().redirect_request(req, fp, code, msg, headers, newurl)
        if request is None:
            return None
        if _origin(req.full_url) != _origin(newurl):
            request.headers = _strip_sensitive_headers(request.headers)
            request.full_url = _strip_sensitive_query(request.full_url)
        return request


# Compatibility alias for callers/tests that used the private name.
_ValidatingRedirectHandler = ValidatedRedirectHandler

_OPENER = urllib.request.build_opener(
    urllib.request.HTTPSHandler(context=SSL_CONTEXT),
    ValidatedRedirectHandler(),
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


def _decompress_member(raw: bytes, wbits: int, limit: int) -> tuple[bytes, bytes]:
    """Decompress one gzip/deflate member and return (output, trailing bytes)."""
    decompressor = zlib.decompressobj(wbits)
    try:
        output = decompressor.decompress(raw, limit)
    except zlib.error as exc:
        raise ReachError(
            UPSTREAM_BROKEN, f"cannot decompress response: {exc}"
        ) from exc
    if decompressor.unconsumed_tail:
        raise ReachError(
            UPSTREAM_BROKEN, "response is too large after decompression"
        )
    if not decompressor.eof:
        raise ReachError(UPSTREAM_BROKEN, "response is truncated")
    return output, decompressor.unused_data


def _decompress(raw: bytes, encoding: str) -> bytes:
    """Decompress gzip/deflate with a hard output cap across all members."""
    encoding = (encoding or "").lower()
    if "deflate" in encoding:
        try:
            output, _ = _decompress_member(raw, zlib.MAX_WBITS, MAX_DECOMPRESSED)
        except ReachError:
            output, _ = _decompress_member(raw, -zlib.MAX_WBITS, MAX_DECOMPRESSED)
        return output
    if "gzip" not in encoding:
        return raw

    chunks: list[bytes] = []
    remaining = raw
    total = 0
    while remaining:
        if total >= MAX_DECOMPRESSED:
            raise ReachError(
                UPSTREAM_BROKEN, "response is too large after decompression"
            )
        chunk, remaining = _decompress_member(
            remaining, 16 + zlib.MAX_WBITS, MAX_DECOMPRESSED - total
        )
        total += len(chunk)
        chunks.append(chunk)
    return b"".join(chunks)


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
    code_map: Optional[dict[int, str]] = None,
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
            raw = _decompress(
                raw, response.headers.get("Content-Encoding") or ""
            )
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
        code = (code_map or {}).get(exc.code) or _http_code(exc.code)
        raise ReachError(
            code, f"HTTP {exc.code} from {sanitize_url(url)}: {body}"
        ) from exc
    except urllib.error.URLError as exc:
        reason = str(exc.reason)
        code = TIMEOUT if "timed out" in reason.lower() else UPSTREAM_BROKEN
        raise ReachError(code, f"cannot reach {sanitize_url(url)}: {reason}") from exc
    except TimeoutError as exc:
        raise ReachError(TIMEOUT, f"request timed out: {sanitize_url(url)}") from exc


def fetch_json(
    url: str,
    *,
    timeout: float,
    headers: Optional[dict] = None,
    params: Optional[dict] = None,
    data: Optional[bytes] = None,
    method: Optional[str] = None,
    code_map: Optional[dict[int, str]] = None,
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
        code_map=code_map,
    )
    try:
        payload = json.loads(response.text)
    except ValueError as exc:
        raise ReachError(
            UPSTREAM_BROKEN, f"{sanitize_url(url)} did not return JSON"
        ) from exc
    if not isinstance(payload, (dict, list)):
        raise ReachError(
            UPSTREAM_BROKEN,
            f"{sanitize_url(url)} returned an unexpected JSON payload",
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
