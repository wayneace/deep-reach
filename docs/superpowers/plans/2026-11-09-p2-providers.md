# P2 搜索/阅读后端实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 Tavily / Brave / Firecrawl / Bright Data 四个 P2 后端，提供 `web search` 通用搜索，并扩展 `web read` 与 4 个站点阅读动作的降级链。

**Architecture:** 每家一个 `deep_reach/backends/<provider>.py`，复用 `http.fetch_json`（新增可选 `code_map`）；共享 `p2_common.py` 统一超时/状态码映射/参数归一化。`channels.yaml` 只负责编排顺序，注册表继续强制 P0 → P1 → P2。

**Tech Stack:** Python 3.10+、urllib、PyYAML、pytest/unittest、ruff。

**Spec:** `docs/superpowers/specs/2026-11-09-p2-providers-design.md`

## Global Constraints

- 只读；不新增写操作，不绕过登录墙。
- 只使用各 provider 的免费额度/免费 credit；不自动充值，不接付费调用。
- P2 搜索顺序固定：`tavily-search` → `brave-search` → `firecrawl-search` → `brightdata-serp`。
- P2 阅读顺序固定：`jina` → `firecrawl-scrape` → `tavily-extract` → `brightdata-unlocker`。
- Key 路径固定：`search.tavily.api_key`、`search.brave.api_key`、`search.firecrawl.api_key`、`search.brightdata.api_token`、`search.brightdata.serp_zone`、`search.brightdata.unlocker_zone`。
- P2 HTTP 映射：401/403 → `NEED_SETUP`；402/429 → `QUOTA_EXHAUSTED`；404 → `NOT_FOUND`；5xx/网络 → `UPSTREAM_BROKEN`；超时 → `TIMEOUT`。
- 不新增第三方 Python 依赖。
- 不修改 P0/P1 的 `RATE_LIMITED` 终止语义。
- 每个任务结束提交一次；不要 push、tag、merge，除非用户明确要求。

## Review Focus

- **Provider 返回 200 但内容不是 JSON / 是错误页**：必须抛 `UPSTREAM_BROKEN`，不能让 `json.loads` 的异常直接冒泡。测试放在各 provider 的 malformed-response 用例。
- **`limit` 为负数、0、超大值或非数字**：必须 clamp 到 1..20，不能把非法值发给 provider。测试放在 `test_p2_common.py`。
- **空搜索结果**：必须返回 `[]` 并视为成功，不能触发降层。测试放在各 search provider。
- **Bright Data 返回包装体 `{"status_code", "body"}` 或直接 JSON**：两种都要能解析。测试放在 `test_p2_brightdata.py`。
- **Bright Data Unlocker 的 `body` 是 HTML**：必须复用 `html_to_text`，不能把原始 HTML 当正文返回。测试放在 `test_p2_brightdata.py`。

---

### Task 1: HTTP 状态码映射

**Files:**
- Modify: `deep_reach/backends/http.py:235-313`
- Test: `tests/test_p2_http.py`

**Interfaces:**
- Produces:
  - `fetch(url: str, *, timeout: float, headers=None, accept=..., data=None, method=None, code_map: Optional[dict[int, str]] = None) -> Response`
  - `fetch_json(url: str, *, timeout: float, headers=None, params=None, data=None, method=None, code_map: Optional[dict[int, str]] = None) -> Any`

- [ ] **Step 1: Write the failing test**

```python
import io
import unittest
import urllib.error
from unittest import mock

from deep_reach.backends.http import fetch, fetch_json
from deep_reach.runtime.result import NOT_FOUND, NEED_SETUP, QUOTA_EXHAUSTED, ReachError


def http_error(status: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://example.com", status, "err", {}, io.BytesIO(b"denied")
    )


class CodeMapTest(unittest.TestCase):
    def test_code_map_overrides_401(self):
        with mock.patch("deep_reach.backends.http.validate_url"), mock.patch(
            "deep_reach.backends.http._OPENER.open", side_effect=http_error(401)
        ):
            with self.assertRaises(ReachError) as ctx:
                fetch("https://example.com", timeout=1, code_map={401: NEED_SETUP})
        self.assertEqual(ctx.exception.code, NEED_SETUP)

    def test_code_map_overrides_429_for_json(self):
        with mock.patch("deep_reach.backends.http.validate_url"), mock.patch(
            "deep_reach.backends.http._OPENER.open", side_effect=http_error(429)
        ):
            with self.assertRaises(ReachError) as ctx:
                fetch_json(
                    "https://example.com", timeout=1, code_map={429: QUOTA_EXHAUSTED}
                )
        self.assertEqual(ctx.exception.code, QUOTA_EXHAUSTED)

    def test_default_mapping_is_unchanged(self):
        with mock.patch("deep_reach.backends.http.validate_url"), mock.patch(
            "deep_reach.backends.http._OPENER.open", side_effect=http_error(404)
        ):
            with self.assertRaises(ReachError) as ctx:
                fetch("https://example.com", timeout=1)
        self.assertEqual(ctx.exception.code, NOT_FOUND)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p2_http.py -v`
Expected: FAIL with `TypeError: fetch() got an unexpected keyword argument 'code_map'`.

- [ ] **Step 3: Implement `code_map`**

In `fetch`, add the parameter and change the HTTPError branch:

```python
code = (code_map or {}).get(exc.code) or _http_code(exc.code)
```

In `fetch_json`, add the same parameter and pass it through to `fetch`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p2_http.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add deep_reach/backends/http.py tests/test_p2_http.py
git commit -m "feat: allow per-backend HTTP status mapping"
```

---

### Task 2: P2 公共辅助 + Jina 429

**Files:**
- Create: `deep_reach/backends/p2_common.py`
- Modify: `deep_reach/backends/jina.py:43-49`
- Test: `tests/test_p2_common.py`

**Interfaces:**
- Produces:
  - `P2_CODE_MAP: dict[int, str]`
  - `p2_fetch_json(url: str, *, timeout: float, headers=None, params=None, data=None, method=None) -> Any`
  - `clamp_limit(value: object, default: int = 10, maximum: int = 20) -> int`
  - `require_key(keys: Keys, path: str, label: str) -> str`

- [ ] **Step 1: Write the failing tests**

```python
import io
import unittest
import urllib.error
from unittest import mock

from deep_reach.backends.jina import JinaReader
from deep_reach.backends.p2_common import clamp_limit, require_key
from deep_reach.runtime.keys import Keys
from deep_reach.runtime.result import NEED_SETUP, QUOTA_EXHAUSTED, ReachError


class P2CommonTest(unittest.TestCase):
    def test_clamp_limit(self):
        self.assertEqual(clamp_limit(None), 10)
        self.assertEqual(clamp_limit("x"), 10)
        self.assertEqual(clamp_limit(0), 1)
        self.assertEqual(clamp_limit(-3), 1)
        self.assertEqual(clamp_limit("50"), 20)
        self.assertEqual(clamp_limit("5"), 5)

    def test_require_key(self):
        with self.assertRaises(ReachError) as ctx:
            require_key(Keys({}), "search.tavily.api_key", "tavily")
        self.assertEqual(ctx.exception.code, NEED_SETUP)


class JinaRateLimitTest(unittest.TestCase):
    def test_429_is_quota_exhausted(self):
        error = urllib.error.HTTPError(
            "https://r.jina.ai/x", 429, "limited", {}, io.BytesIO(b"")
        )
        with mock.patch(
            "deep_reach.backends.jina.urllib.request.urlopen", side_effect=error
        ):
            with self.assertRaises(ReachError) as ctx:
                JinaReader().read("https://example.com")
        self.assertEqual(ctx.exception.code, QUOTA_EXHAUSTED)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p2_common.py -v`
Expected: FAIL with `ModuleNotFoundError: deep_reach.backends.p2_common`; the Jina test fails with `RATE_LIMITED != QUOTA_EXHAUSTED`.

- [ ] **Step 3: Create `p2_common.py` and change Jina**

`p2_common.py`:

```python
from typing import Any

from ..runtime.keys import Keys
from ..runtime.result import NEED_SETUP, QUOTA_EXHAUSTED, ReachError
from .http import fetch_json

P2_CODE_MAP = {
    401: NEED_SETUP,
    402: QUOTA_EXHAUSTED,
    403: NEED_SETUP,
    429: QUOTA_EXHAUSTED,
}

def p2_fetch_json(
    url: str, *, timeout: float, headers=None, params=None, data=None, method=None
) -> Any:
    return fetch_json(
        url, timeout=timeout, headers=headers, params=params, data=data,
        method=method, code_map=P2_CODE_MAP,
    )

def clamp_limit(value: object, default: int = 10, maximum: int = 20) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(1, min(number, maximum))

def require_key(keys: Keys, path: str, label: str) -> str:
    value = keys.get(path)
    if not value:
        raise ReachError(NEED_SETUP, f"{label} needs {path}")
    return str(value)
```

In `jina.py`, import `QUOTA_EXHAUSTED` and change the 429 branch to raise it.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p2_common.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add deep_reach/backends/p2_common.py deep_reach/backends/jina.py tests/test_p2_common.py
git commit -m "feat: add P2 helpers and make Jina 429 retryable"
```

---

### Task 3: Tavily 搜索与提取

**Files:**
- Create: `deep_reach/backends/tavily.py`
- Test: `tests/test_p2_tavily.py`

**Interfaces:**
- Consumes: `p2_fetch_json`, `clamp_limit`, `require_key` from Task 2.
- Produces: `register_tavily_backends(keys: Keys) -> None`; registers `tavily-search` and `tavily-extract`.

- [ ] **Step 1: Write the failing tests**

```python
import json
import unittest
from unittest import mock

from deep_reach.backends.tavily import register_tavily_backends
from deep_reach.channels.base import BackendSpec, Channel
from deep_reach.runtime.dispatch import BACKENDS
from deep_reach.runtime.keys import Keys
from deep_reach.runtime.result import UPSTREAM_BROKEN, ReachError


def make_channel():
    return Channel(name="web", category="web", actions=())


def spec(label):
    return BackendSpec(label=label, method="search", tier="p2", requires_key=True)


class TavilyTest(unittest.TestCase):
    def tearDown(self):
        BACKENDS.clear()

    def test_search_request_shape_and_items(self):
        captured = {}

        def fake(url, **kwargs):
            captured.update(url=url, **kwargs)
            return {
                "results": [
                    {"title": "Desk", "url": "https://example.com/a", "content": "hello"}
                ]
            }

        register_tavily_backends(Keys({"search": {"tavily": {"api_key": "tvly-test"}}}))
        with mock.patch("deep_reach.backends.tavily.p2_fetch_json", side_effect=fake):
            items = BACKENDS["tavily-search"](
                action="search",
                params={"query": "desk", "limit": 5},
                timeout=5,
                spec=spec("tavily-search"),
                channel=make_channel(),
            )

        self.assertEqual(captured["url"], "https://api.tavily.com/search")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer tvly-test")
        body = json.loads(captured["data"])
        self.assertEqual(body["query"], "desk")
        self.assertEqual(body["max_results"], 5)
        self.assertEqual(items[0]["title"], "Desk")
        self.assertEqual(items[0]["backend"], "tavily-search")

    def test_empty_results_are_success(self):
        register_tavily_backends(Keys({"search": {"tavily": {"api_key": "k"}}}))
        with mock.patch(
            "deep_reach.backends.tavily.p2_fetch_json",
            return_value={"results": []},
        ):
            items = BACKENDS["tavily-search"](
                action="search",
                params={"query": "desk"},
                timeout=5,
                spec=spec("tavily-search"),
                channel=make_channel(),
            )
        self.assertEqual(items, [])

    def test_extract_parses_raw_content(self):
        def fake(url, **kwargs):
            return {
                "results": [{"url": "https://example.com", "raw_content": "# Hello"}]
            }

        register_tavily_backends(Keys({"search": {"tavily": {"api_key": "k"}}}))
        with mock.patch("deep_reach.backends.tavily.p2_fetch_json", side_effect=fake):
            items = BACKENDS["tavily-extract"](
                action="read",
                params={"target": "https://example.com"},
                timeout=5,
                spec=spec("tavily-extract"),
                channel=make_channel(),
            )

        self.assertEqual(items[0]["text"], "# Hello")

    def test_malformed_payload_raises_upstream_broken(self):
        register_tavily_backends(Keys({"search": {"tavily": {"api_key": "k"}}}))
        with mock.patch(
            "deep_reach.backends.tavily.p2_fetch_json", return_value={"unexpected": []}
        ):
            with self.assertRaises(ReachError) as ctx:
                BACKENDS["tavily-search"](
                    action="search",
                    params={"query": "desk"},
                    timeout=5,
                    spec=spec("tavily-search"),
                    channel=make_channel(),
                )
        self.assertEqual(ctx.exception.code, UPSTREAM_BROKEN)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p2_tavily.py -v`
Expected: FAIL with `ModuleNotFoundError: deep_reach.backends.tavily`.

- [ ] **Step 3: Implement `tavily.py`**

Register two handlers:

- `tavily-search`: POST `https://api.tavily.com/search`, Bearer key, body
  `{"query": query, "max_results": clamp_limit(limit), "search_depth": "basic", "include_answer": False}`.
  Parse `results`; each item uses `title`, `url`, `content`.
- `tavily-extract`: POST `https://api.tavily.com/extract`, Bearer key, body
  `{"urls": [target], "format": "markdown"}`. Parse `results[0]["raw_content"]`;
  missing results or content → `UPSTREAM_BROKEN`.

Both use `make_item(source=channel.name, category=channel.category, platform="web", backend=spec.label, ...)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p2_tavily.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add deep_reach/backends/tavily.py tests/test_p2_tavily.py
git commit -m "feat: add Tavily P2 search and extract backends"
```

---

### Task 4: Brave 搜索

**Files:**
- Create: `deep_reach/backends/brave.py`
- Test: `tests/test_p2_brave.py`

**Interfaces:**
- Consumes: `p2_fetch_json`, `clamp_limit`, `require_key`.
- Produces: `register_brave_backend(keys: Keys) -> None`; registers `brave-search`.

- [ ] **Step 1: Write the failing tests**

```python
import unittest
from unittest import mock

from deep_reach.backends.brave import register_brave_backend
from deep_reach.channels.base import BackendSpec, Channel
from deep_reach.runtime.dispatch import BACKENDS
from deep_reach.runtime.keys import Keys
from deep_reach.runtime.result import UPSTREAM_BROKEN, ReachError


class BraveTest(unittest.TestCase):
    def tearDown(self):
        BACKENDS.clear()

    def test_search_request_shape_and_items(self):
        captured = {}

        def fake(url, **kwargs):
            captured.update(url=url, **kwargs)
            return {
                "web": {
                    "results": [
                        {"title": "Desk", "url": "https://example.com", "description": "hi"}
                    ]
                }
            }

        register_brave_backend(Keys({"search": {"brave": {"api_key": "brave-key"}}}))
        with mock.patch("deep_reach.backends.brave.p2_fetch_json", side_effect=fake):
            items = BACKENDS["brave-search"](
                action="search",
                params={"query": "desk", "limit": 5},
                timeout=5,
                spec=BackendSpec("brave-search", "search", tier="p2", requires_key=True),
                channel=Channel(name="web", category="web", actions=()),
            )

        self.assertEqual(captured["url"], "https://api.search.brave.com/res/v1/web/search")
        self.assertEqual(captured["headers"]["X-Subscription-Token"], "brave-key")
        self.assertEqual(captured["params"], {"q": "desk", "count": 5})
        self.assertEqual(items[0]["title"], "Desk")

    def test_missing_web_results_raises(self):
        register_brave_backend(Keys({"search": {"brave": {"api_key": "k"}}}))
        with mock.patch("deep_reach.backends.brave.p2_fetch_json", return_value={}):
            with self.assertRaises(ReachError) as ctx:
                BACKENDS["brave-search"](
                    action="search",
                    params={"query": "desk"},
                    timeout=5,
                    spec=BackendSpec("brave-search", "search", tier="p2", requires_key=True),
                    channel=Channel(name="web", category="web", actions=()),
                )
        self.assertEqual(ctx.exception.code, UPSTREAM_BROKEN)

    def test_empty_results_are_success(self):
        register_brave_backend(Keys({"search": {"brave": {"api_key": "k"}}}))
        with mock.patch(
            "deep_reach.backends.brave.p2_fetch_json",
            return_value={"web": {"results": []}},
        ):
            items = BACKENDS["brave-search"](
                action="search",
                params={"query": "desk"},
                timeout=5,
                spec=BackendSpec("brave-search", "search", tier="p2", requires_key=True),
                channel=Channel(name="web", category="web", actions=()),
            )
        self.assertEqual(items, [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p2_brave.py -v`
Expected: FAIL with `ModuleNotFoundError: deep_reach.backends.brave`.

- [ ] **Step 3: Implement `brave.py`**

`brave-search`: GET `https://api.search.brave.com/res/v1/web/search`, header
`X-Subscription-Token`, params `{"q": query, "count": clamp_limit(limit)}`.
Parse `web.results`; each item uses `title`, `url`, `description`. Missing or
non-dict `web` → `UPSTREAM_BROKEN`; empty `results` → `[]`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p2_brave.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add deep_reach/backends/brave.py tests/test_p2_brave.py
git commit -m "feat: add Brave Search P2 backend"
```

---

### Task 5: Firecrawl 搜索与抓取

**Files:**
- Create: `deep_reach/backends/firecrawl.py`
- Test: `tests/test_p2_firecrawl.py`

**Interfaces:**
- Consumes: `p2_fetch_json`, `clamp_limit`, `require_key`.
- Produces: `register_firecrawl_backends(keys: Keys) -> None`; registers `firecrawl-search` and `firecrawl-scrape`.

- [ ] **Step 1: Write the failing tests**

```python
import json
import unittest
from unittest import mock

from deep_reach.backends.firecrawl import register_firecrawl_backends
from deep_reach.channels.base import BackendSpec, Channel
from deep_reach.runtime.dispatch import BACKENDS
from deep_reach.runtime.keys import Keys
from deep_reach.runtime.result import UPSTREAM_BROKEN, ReachError


class FirecrawlTest(unittest.TestCase):
    def tearDown(self):
        BACKENDS.clear()

    def test_search_request_shape(self):
        captured = {}

        def fake(url, **kwargs):
            captured.update(url=url, **kwargs)
            return {"success": True, "data": [{"title": "T", "url": "https://x", "description": "D"}]}

        register_firecrawl_backends(Keys({"search": {"firecrawl": {"api_key": "fc"}}}))
        with mock.patch("deep_reach.backends.firecrawl.p2_fetch_json", side_effect=fake):
            items = BACKENDS["firecrawl-search"](
                action="search",
                params={"query": "desk", "limit": 5},
                timeout=5,
                spec=BackendSpec("firecrawl-search", "search", tier="p2", requires_key=True),
                channel=Channel(name="web", category="web", actions=()),
            )

        self.assertEqual(captured["url"], "https://api.firecrawl.dev/v2/search")
        body = json.loads(captured["data"])
        self.assertEqual(body, {"query": "desk", "limit": 5})
        self.assertEqual(items[0]["title"], "T")

    def test_empty_search_is_success(self):
        register_firecrawl_backends(Keys({"search": {"firecrawl": {"api_key": "fc"}}}))
        with mock.patch(
            "deep_reach.backends.firecrawl.p2_fetch_json",
            return_value={"success": True, "data": []},
        ):
            items = BACKENDS["firecrawl-search"](
                action="search",
                params={"query": "desk"},
                timeout=5,
                spec=BackendSpec("firecrawl-search", "search", tier="p2", requires_key=True),
                channel=Channel(name="web", category="web", actions=()),
            )
        self.assertEqual(items, [])

    def test_scrape_parses_markdown(self):
        def fake(url, **kwargs):
            return {
                "success": True,
                "data": {"markdown": "# Hello", "metadata": {"title": "Example"}},
            }

        register_firecrawl_backends(Keys({"search": {"firecrawl": {"api_key": "fc"}}}))
        with mock.patch("deep_reach.backends.firecrawl.p2_fetch_json", side_effect=fake):
            items = BACKENDS["firecrawl-scrape"](
                action="read",
                params={"target": "https://example.com"},
                timeout=5,
                spec=BackendSpec("firecrawl-scrape", "read", tier="p2", requires_key=True),
                channel=Channel(name="web", category="web", actions=()),
            )

        self.assertEqual(items[0]["title"], "Example")
        self.assertEqual(items[0]["text"], "# Hello")

    def test_failed_scrape_raises(self):
        register_firecrawl_backends(Keys({"search": {"firecrawl": {"api_key": "fc"}}}))
        with mock.patch(
            "deep_reach.backends.firecrawl.p2_fetch_json",
            return_value={"success": False, "error": "blocked"},
        ):
            with self.assertRaises(ReachError) as ctx:
                BACKENDS["firecrawl-scrape"](
                    action="read",
                    params={"target": "https://example.com"},
                    timeout=5,
                    spec=BackendSpec("firecrawl-scrape", "read", tier="p2", requires_key=True),
                    channel=Channel(name="web", category="web", actions=()),
                )
        self.assertEqual(ctx.exception.code, UPSTREAM_BROKEN)

    def test_search_without_data_raises(self):
        register_firecrawl_backends(Keys({"search": {"firecrawl": {"api_key": "fc"}}}))
        with mock.patch(
            "deep_reach.backends.firecrawl.p2_fetch_json",
            return_value={"success": True},
        ):
            with self.assertRaises(ReachError) as ctx:
                BACKENDS["firecrawl-search"](
                    action="search",
                    params={"query": "desk"},
                    timeout=5,
                    spec=BackendSpec("firecrawl-search", "search", tier="p2", requires_key=True),
                    channel=Channel(name="web", category="web", actions=()),
                )
        self.assertEqual(ctx.exception.code, UPSTREAM_BROKEN)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p2_firecrawl.py -v`
Expected: FAIL with `ModuleNotFoundError: deep_reach.backends.firecrawl`.

- [ ] **Step 3: Implement `firecrawl.py`**

- Base `https://api.firecrawl.dev/v2`.
- `firecrawl-search`: POST `/search`, Bearer, body `{"query": query, "limit": clamp_limit(limit)}`.
  Parse `data` list; each item uses `title`, `url`, `description` or `markdown`.
- `firecrawl-scrape`: POST `/scrape`, Bearer, body
  `{"url": target, "formats": ["markdown"]}`. Parse `data.markdown`;
  `metadata.title` for title. `success` false or no markdown → `UPSTREAM_BROKEN`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p2_firecrawl.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add deep_reach/backends/firecrawl.py tests/test_p2_firecrawl.py
git commit -m "feat: add Firecrawl P2 search and scrape backends"
```

---

### Task 6: Bright Data SERP 与 Web Unlocker

**Files:**
- Create: `deep_reach/backends/brightdata.py`
- Test: `tests/test_p2_brightdata.py`

**Interfaces:**
- Consumes: `p2_fetch_json`, `clamp_limit`, `require_key`, `http.html_to_text`, `http.validate_url`.
- Produces: `register_brightdata_backends(keys: Keys) -> None`; registers `brightdata-serp` and `brightdata-unlocker`.

- [ ] **Step 1: Write the failing tests**

```python
import json
import unittest
from unittest import mock

from deep_reach.backends.brightdata import register_brightdata_backends
from deep_reach.channels.base import BackendSpec, Channel
from deep_reach.runtime.dispatch import BACKENDS
from deep_reach.runtime.keys import Keys
from deep_reach.runtime.result import BAD_INPUT, NEED_SETUP, UPSTREAM_BROKEN, ReachError

KEYS = Keys(
    {
        "search": {
            "brightdata": {
                "api_token": "bd-token",
                "serp_zone": "serp1",
                "unlocker_zone": "unlocker1",
            }
        }
    }
)


def channel():
    return Channel(name="web", category="web", actions=())


def spec(label):
    return BackendSpec(label, "search", tier="p2", requires_key=True)


class BrightDataTest(unittest.TestCase):
    def tearDown(self):
        BACKENDS.clear()

    def test_serp_request_shape_and_organic_items(self):
        captured = {}

        def fake(url, **kwargs):
            captured.update(url=url, **kwargs)
            return {"organic": [{"title": "T", "link": "https://x", "description": "D"}]}

        register_brightdata_backends(KEYS)
        with mock.patch("deep_reach.backends.brightdata.p2_fetch_json", side_effect=fake):
            items = BACKENDS["brightdata-serp"](
                action="search",
                params={"query": "desk organizer", "limit": 5},
                timeout=5,
                spec=spec("brightdata-serp"),
                channel=channel(),
            )

        self.assertEqual(captured["url"], "https://api.brightdata.com/request")
        body = json.loads(captured["data"])
        self.assertEqual(body["zone"], "serp1")
        self.assertEqual(body["format"], "raw")
        self.assertIn("brd_json=json", body["url"])
        self.assertEqual(items[0]["url"], "https://x")

    def test_serp_accepts_wrapped_body(self):
        wrapped = json.dumps({"organic": [{"title": "T", "link": "https://x"}]})

        def fake(url, **kwargs):
            return {"status_code": 200, "body": wrapped}

        register_brightdata_backends(KEYS)
        with mock.patch("deep_reach.backends.brightdata.p2_fetch_json", side_effect=fake):
            items = BACKENDS["brightdata-serp"](
                action="search",
                params={"query": "desk"},
                timeout=5,
                spec=spec("brightdata-serp"),
                channel=channel(),
            )
        self.assertEqual(items[0]["url"], "https://x")

    def test_serp_without_organic_raises(self):
        register_brightdata_backends(KEYS)
        with mock.patch(
            "deep_reach.backends.brightdata.p2_fetch_json",
            return_value={"unexpected": []},
        ):
            with self.assertRaises(ReachError) as ctx:
                BACKENDS["brightdata-serp"](
                    action="search",
                    params={"query": "desk"},
                    timeout=5,
                    spec=spec("brightdata-serp"),
                    channel=channel(),
                )
        self.assertEqual(ctx.exception.code, UPSTREAM_BROKEN)

    def test_empty_organic_is_success(self):
        register_brightdata_backends(KEYS)
        with mock.patch(
            "deep_reach.backends.brightdata.p2_fetch_json",
            return_value={"organic": []},
        ):
            items = BACKENDS["brightdata-serp"](
                action="search",
                params={"query": "desk"},
                timeout=5,
                spec=spec("brightdata-serp"),
                channel=channel(),
            )
        self.assertEqual(items, [])

    def test_unlocker_converts_html(self):
        def fake(url, **kwargs):
            return {
                "status_code": 200,
                "body": (
                    "<html><head><title>Hello</title></head><body>"
                    "<p>World content here. This page was unlocked successfully.</p>"
                    "</body></html>"
                ),
            }

        register_brightdata_backends(KEYS)
        with mock.patch("deep_reach.backends.brightdata.p2_fetch_json", side_effect=fake):
            items = BACKENDS["brightdata-unlocker"](
                action="read",
                params={"target": "https://example.com"},
                timeout=5,
                spec=spec("brightdata-unlocker"),
                channel=channel(),
            )

        self.assertEqual(items[0]["title"], "Hello")
        self.assertIn("World content here", items[0]["text"])

    def test_unlocker_rejects_private_url(self):
        register_brightdata_backends(KEYS)
        with self.assertRaises(ReachError) as ctx:
            BACKENDS["brightdata-unlocker"](
                action="read",
                params={"target": "http://127.0.0.1/"},
                timeout=5,
                spec=spec("brightdata-unlocker"),
                channel=channel(),
            )
        self.assertEqual(ctx.exception.code, BAD_INPUT)

    def test_missing_zone_raises_need_setup(self):
        register_brightdata_backends(Keys({"search": {"brightdata": {"api_token": "t"}}}))
        with self.assertRaises(ReachError) as ctx:
            BACKENDS["brightdata-serp"](
                action="search",
                params={"query": "desk"},
                timeout=5,
                spec=spec("brightdata-serp"),
                channel=channel(),
            )
        self.assertEqual(ctx.exception.code, NEED_SETUP)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p2_brightdata.py -v`
Expected: FAIL with `ModuleNotFoundError: deep_reach.backends.brightdata`.

- [ ] **Step 3: Implement `brightdata.py`**

- Endpoint: `https://api.brightdata.com/request`, Bearer `api_token`.
- `brightdata-serp`:
  - Keys: `search.brightdata.api_token`, `search.brightdata.serp_zone`.
  - Body: `{"zone": serp_zone, "url": "https://www.google.com/search?q=<quote_plus>&brd_json=json", "format": "raw"}`.
  - Unwrap `{"status_code", "body"}` if present; parse `organic` /
    `organic_results` / `results`; each entry uses `title`, `link`/`url`,
    `description`/`snippet`. Empty list → `[]`; missing organic key → `UPSTREAM_BROKEN`.
- `brightdata-unlocker`:
  - Keys: `search.brightdata.api_token`, `search.brightdata.unlocker_zone`.
  - `validate_url(target)` first.
  - Body: `{"zone": unlocker_zone, "url": target, "format": "raw"}`.
  - Read `body`; if `status_code` >= 400 → `UPSTREAM_BROKEN`.
  - `html_to_text(body)`; body shorter than 40 chars → `UPSTREAM_BROKEN`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p2_brightdata.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add deep_reach/backends/brightdata.py tests/test_p2_brightdata.py
git commit -m "feat: add Bright Data SERP and Web Unlocker P2 backends"
```

---

### Task 7: 注册 `web search` 并接入 CLI

**Files:**
- Modify: `deep_reach/data/channels.yaml:209-226`
- Modify: `deep_reach/cli.py:22-33,70-84`
- Modify: `deep_reach/data/keys.example.yaml`
- Modify: `tests/test_product_contract.py`
- Test: `tests/test_p2_registry.py`

**Interfaces:**
- Consumes: `register_tavily_backends`, `register_brave_backend`,
  `register_firecrawl_backends`, `register_brightdata_backends` from Tasks 3-6.
- Produces: `web search` action; all four backends registered by `_register_backends`.

- [ ] **Step 1: Write the failing tests**

```python
import unittest

from deep_reach.channels import load_registry
from deep_reach.cli import build_parser
from deep_reach.runtime.availability import Environment, channel_availability
from deep_reach.runtime.keys import Keys


class P2RegistryTest(unittest.TestCase):
    def test_web_search_backends_in_order(self):
        action = load_registry().visible["web"].action("search")
        self.assertEqual(
            [b.label for b in action.backends],
            ["tavily-search", "brave-search", "firecrawl-search", "brightdata-serp"],
        )
        self.assertTrue(all(b.tier == "p2" for b in action.backends))
        self.assertTrue(all(b.requires_key for b in action.backends))

    def test_web_search_parser(self):
        args = build_parser(load_registry()).parse_args(
            ["web", "search", "desk", "--limit", "5"]
        )
        self.assertEqual(args.channel_name, "web")
        self.assertEqual(args.action_name, "search")
        self.assertEqual(args.query, "desk")
        self.assertEqual(args.limit, 5)

    def test_web_search_needs_key_without_keys(self):
        channel = load_registry().visible["web"]
        env = Environment(keys=Keys({}), opencli_installed=False)
        result = channel_availability(channel, env)
        self.assertIn("search", result.unavailable_actions)
        self.assertIn("read", result.available_actions)

    def test_web_search_ready_with_one_key(self):
        channel = load_registry().visible["web"]
        keys = Keys({"search": {"tavily": {"api_key": "tvly-test"}}})
        env = Environment(keys=keys, opencli_installed=False)
        result = channel_availability(channel, env)
        self.assertIn("search", result.available_actions)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p2_registry.py -v`
Expected: FAIL with `KeyError: 'search'` or `AttributeError: 'NoneType'`.

- [ ] **Step 3: Wire the action and registration**

Add to `channels.yaml` under `web.actions`:

```yaml
      search:
        description: 通用网页搜索
        requires: key
        params: [query, limit]
        backends:
          - {label: tavily-search, tier: p2, requires_key: true, key: search.tavily.api_key}
          - {label: brave-search, tier: p2, requires_key: true, key: search.brave.api_key}
          - {label: firecrawl-search, tier: p2, requires_key: true, key: search.firecrawl.api_key}
          - {label: brightdata-serp, tier: p2, requires_key: true, keys: [search.brightdata.api_token, search.brightdata.serp_zone]}
```

Update `web.description` to `通用网页搜索与阅读`, and `web.next_action` to mention
the four search keys.

In `cli.py`, import and register the four providers in `_register_backends`.

In `keys.example.yaml`, fill the existing `search` block with the new keys and
free-tier comments (Tavily 1,000 credits/月; Firecrawl 1,000 credits/月; Brave
$5/月 credit + attribution; Bright Data 5,000 credits/月 + two zones).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p2_registry.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add deep_reach/data/channels.yaml deep_reach/cli.py deep_reach/data/keys.example.yaml tests/test_p2_registry.py
git commit -m "feat: expose web search through P2 providers"
```

---

### Task 8: 扩展阅读链

**Files:**
- Modify: `deep_reach/data/channels.yaml` (`web.read`, `amazon.product`,
  `kickstarter.read`, `cnipa.read`, `copyright.read`)
- Test: `tests/test_p2_registry.py`

**Interfaces:**
- Consumes: backend labels from Tasks 3-6.
- Produces: P2 reader chains on the five read actions.

- [ ] **Step 1: Write the failing test**

```python
    def test_read_actions_have_full_p2_chain(self):
        registry = load_registry()
        expected = ["firecrawl-scrape", "tavily-extract", "brightdata-unlocker"]
        targets = [
            ("web", "read"),
            ("amazon", "product"),
            ("kickstarter", "read"),
            ("cnipa", "read"),
            ("copyright", "read"),
        ]
        for channel_name, action_name in targets:
            labels = [
                b.label
                for b in registry.visible[channel_name].action(action_name).backends
            ]
            self.assertEqual(labels[-3:], expected, (channel_name, action_name))
            self.assertIn("jina", labels)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p2_registry.py::P2RegistryTest::test_read_actions_have_full_p2_chain -v`
Expected: FAIL with an assertion mismatch.

- [ ] **Step 3: Append the reader backends**

For each read action, append after `jina`:

```yaml
          - {label: firecrawl-scrape, tier: p2, requires_key: true, key: search.firecrawl.api_key}
          - {label: tavily-extract, tier: p2, requires_key: true, key: search.tavily.api_key}
          - {label: brightdata-unlocker, tier: p2, requires_key: true, keys: [search.brightdata.api_token, search.brightdata.unlocker_zone]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p2_registry.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add deep_reach/data/channels.yaml tests/test_p2_registry.py
git commit -m "feat: extend P2 reader fallbacks on web and site reads"
```

---

### Task 9: 文档、版本与全量验证

**Files:**
- Modify: `README.md`
- Modify: `PRODUCT.md`
- Modify: `skill/references/capabilities.md`
- Modify: `deep_reach/channels/base.py` (`TIER_LABELS`)
- Modify: `CHANGELOG.md`
- Modify: `pyproject.toml`, `deep_reach/__init__.py`, `uv.lock`
- Test: existing suite + docs checks

**Interfaces:**
- Consumes: all previous tasks.
- Produces: documented v0.10.0 with verified wheel.

- [ ] **Step 1: Update docs**

- README P2 table: add `tavily` / `brave` / `firecrawl` / `brightdata` and the
  `web search` action; update the architecture tree; update key instructions
  with free-tier notes and Brave attribution.
- PRODUCT: P2 backend list, free-tier boundary wording.
- `capabilities.md`: add `web search` row; update `web read` P2 description.
- `TIER_LABELS["p2"]`: `第三方阅读/采集服务（Jina / Tavily / Brave / Firecrawl / Bright Data）`.
- CHANGELOG: add an Unreleased section describing the feature.

- [ ] **Step 2: Bump version**

Set `version = "0.10.0"` in `pyproject.toml` and `__version__ = "0.10.0"` in
`deep_reach/__init__.py`; run `uv lock`.

- [ ] **Step 3: Run the full verification**

Run:

```bash
uv run pytest -q
uv run ruff check .
rm -rf dist
uv build
uv run python scripts/check_wheel.py
uv run deep-reach doctor
uv run deep-reach tiers
```

`rm -rf dist` avoids `check_wheel.py` picking an older wheel by lexical sort
(`0.9.3` sorts after `0.10.0`).

Expected: all tests pass; ruff clean; wheel contains the new backends and data;
`tiers` shows P2 coverage on `web`, `amazon`, `kickstarter`, `cnipa`, `copyright`.

- [ ] **Step 4: Commit**

```bash
git add README.md PRODUCT.md skill/references/capabilities.md \
  deep_reach/channels/base.py CHANGELOG.md pyproject.toml deep_reach/__init__.py uv.lock
git commit -m "docs: document P2 providers and bump to 0.10.0"
```

- [ ] **Step 5: Stop before release**

Do not tag, push, or publish a GitHub Release. Report the test/ruff/wheel evidence
and ask the user whether to release v0.10.0.
