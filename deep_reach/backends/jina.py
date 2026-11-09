"""Jina Reader: URL -> Markdown, with optional free key for higher rate limits.

No key: 20 RPM/IP. Free key: 500 RPM. This is a generic reader, not a social
scraper; it cannot bypass login walls.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from typing import Optional

from ..runtime.dispatch import BACKENDS
from ..runtime.result import (
    NEED_SETUP,
    RATE_LIMITED,
    TIMEOUT,
    UPSTREAM_BROKEN,
    ReachError,
    make_item,
)

BASE = "https://r.jina.ai"


class JinaReader:
    def __init__(self, api_key: Optional[str] = None, base: str = BASE):
        self.api_key = api_key
        self.base = base.rstrip("/")

    def read(self, url: str, timeout: float = 30.0) -> str:
        headers = {
            "Accept": "text/plain",
            "User-Agent": "deep-reach/0.2",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(f"{self.base}/{url}", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise ReachError(
                    NEED_SETUP, "Jina Reader rejected the key; check search.jina.api_key"
                ) from exc
            if exc.code == 429:
                raise ReachError(RATE_LIMITED, "Jina Reader rate limit (429)") from exc
            raise ReachError(UPSTREAM_BROKEN, f"Jina Reader HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise ReachError(TIMEOUT, "Jina Reader timed out") from exc
            raise ReachError(UPSTREAM_BROKEN, f"Jina Reader network error: {exc.reason}") from exc


def _target_url(channel_name: str, target: str) -> str:
    if target.startswith(("http://", "https://")):
        return target
    if channel_name == "amazon":
        return f"https://www.amazon.com/dp/{target}"
    raise ReachError(
        NEED_SETUP,
        f"{channel_name} reader fallback needs a full URL, got {target!r}",
    )


def _title_from_markdown(text: str, fallback: str) -> str:
    for line in text.splitlines()[:8]:
        stripped = line.strip()
        if stripped.lower().startswith("title:"):
            value = stripped.split(":", 1)[1].strip()
            if value:
                return value
    return fallback


def register_jina_backend(keys=None) -> JinaReader:
    api_key = None
    if keys is not None:
        api_key = keys.get("search.jina.api_key")
    reader = JinaReader(api_key=api_key)

    def handler(*, action: str, params: dict, timeout: float, spec, channel) -> list[dict]:
        target = str(params.get("target") or params.get("url") or "")
        if not target:
            raise ReachError(NEED_SETUP, "jina backend needs target=<url>")
        url = _target_url(channel.name, target)
        text = reader.read(url, timeout=timeout)
        return [
            make_item(
                source=channel.name,
                category=channel.category,
                platform="web",
                title=_title_from_markdown(text, url),
                url=url,
                text=text,
                backend="jina",
                raw=None,
            )
        ]

    BACKENDS.register("jina", handler)
    return reader
