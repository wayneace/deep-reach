# P0 加固 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `doctor`/`channels` 的状态反映当前环境，收紧 `web read` 的 URL 输入面，并让 keys 模板随 wheel 发布。

**Architecture:** 新增 `runtime/availability.py` 作为唯一的环境可用性判定；`doctor` 用 OpenCLI 连接态精确判定，`channels` 只做安装检查以保持快速。URL 校验集中在 `backends/http.py:validate_url()`，`jina` 复用。keys 模板移入 `deep_reach/data/` 由 package data 打包。

**Tech Stack:** Python 3.10+ 标准库（`ipaddress`、`socket`、`importlib.resources`）+ PyYAML；pytest/unittest；uv。

**Spec:** `docs/superpowers/specs/2026-11-09-p0-hardening-design.md`

## Global Constraints

- 只使用 Python 标准库；不新增运行时依赖。
- 所有测试离线，不访问网络。
- `status` 字段保留，值改为环境实测；新增 `declared_status` 保存注册表原值。
- 不修改 dispatch 的 P0→P1→P2 降级语义。
- 不合并、不推送；只在本分支 `fix/p0-hardening` 上提交。
- 每个任务结束前运行对应测试；最终运行 `uv run pytest -q` 和 wheel 检查。

## Review Focus

- 域名解析到私有 IP（DNS）时应拒绝，而不是只看字面 host。
- `amazon` 这类混合动作渠道：部分动作可用时是 `degraded`，不是全有或全无。
- `needs_login` 渠道在 OpenCLI 未安装时应显示 `needs_setup`，安装后才显示 `needs_login`。
- 带 key 的渠道在 key 存在后应从 `needs_key` 变为 `ready`。
- 大写 scheme、无 scheme、`file://`、IPv6 回环都必须拒绝。
- 从 wheel 安装后，`keys.example.yaml` 必须真实存在。

---

### Task 1: 环境可用性模型

**Files:**
- Create: `deep_reach/runtime/availability.py`
- Test: `tests/test_availability.py`

**Interfaces:**
- Produces:
  - `Environment(keys: Keys, opencli_installed: bool, browser_connected: bool | None)`
  - `Environment.opencli_available -> bool`
  - `ChannelAvailability(status: str, declared_status: str, runnable: bool, available_actions: tuple[str, ...], unavailable_actions: dict[str, list[str]])`
  - `detect_environment(keys: Keys, *, client=None, probe_browser: bool = False) -> Environment`
  - `environment_from_profile(keys: Keys, profile: dict) -> Environment`
  - `channel_availability(channel: Channel, env: Environment) -> ChannelAvailability`

- [ ] **Step 1: Write the failing tests**

```python
import unittest

from deep_reach.channels.base import Action, BackendSpec, Channel, Param
from deep_reach.runtime.availability import (
    Environment,
    channel_availability,
)
from deep_reach.runtime.keys import Keys


def channel(declared, backends, name="demo"):
    return Channel(
        name=name,
        category="test",
        status=declared,
        actions=(Action(name="search", params=(Param("query"),), backends=tuple(backends)),),
    )


def env(installed=True, connected=None, data=None):
    return Environment(
        keys=Keys(data or {}),
        opencli_installed=installed,
        browser_connected=connected,
    )


class AvailabilityTest(unittest.TestCase):
    def test_ready_channel_is_ready(self):
        result = channel_availability(
            channel("ready", [BackendSpec("http-read", "search", tier="p0")]),
            env(),
        )
        self.assertEqual(result.status, "ready")
        self.assertTrue(result.runnable)
        self.assertEqual(result.available_actions, ("search",))

    def test_missing_opencli_makes_p1_channel_needs_setup(self):
        result = channel_availability(
            channel("ready", [BackendSpec("opencli-demo", "search")]),
            env(installed=False),
        )
        self.assertEqual(result.status, "needs_setup")
        self.assertFalse(result.runnable)

    def test_partial_actions_are_degraded(self):
        ch = Channel(
            name="amazon",
            category="commerce",
            status="ready",
            actions=(
                Action("search", backends=(BackendSpec("opencli-amazon", "search"),)),
                Action(
                    "product",
                    backends=(
                        BackendSpec("opencli-amazon", "product"),
                        BackendSpec("jina", "product", tier="p2"),
                    ),
                ),
            ),
        )
        result = channel_availability(ch, env(installed=False))
        self.assertEqual(result.status, "degraded")
        self.assertTrue(result.runnable)
        self.assertEqual(result.available_actions, ("product",))
        self.assertIn("search", result.unavailable_actions)

    def test_needs_key_becomes_ready_when_key_present(self):
        ch = channel("needs_key", [BackendSpec("demo-api", "search", tier="p0", requires_key=True)])
        ch.key_path = "official.demo.api_key"
        none = channel_availability(ch, env())
        self.assertEqual(none.status, "needs_key")
        full = channel_availability(
            ch, env(data={"official": {"demo": {"api_key": "secret"}}})
        )
        self.assertEqual(full.status, "ready")

    def test_needs_login_needs_setup_without_opencli(self):
        ch = channel("needs_login", [BackendSpec("opencli-demo", "search")])
        self.assertEqual(channel_availability(ch, env(installed=False)).status, "needs_setup")
        self.assertEqual(
            channel_availability(ch, env(installed=True, connected=True)).status,
            "needs_login",
        )

    def test_experimental_stays_experimental_when_available(self):
        result = channel_availability(
            channel("experimental", [BackendSpec("http-read", "search", tier="p0")]),
            env(),
        )
        self.assertEqual(result.status, "experimental")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_availability.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'deep_reach.runtime.availability'`.

- [ ] **Step 3: Implement `deep_reach/runtime/availability.py`**

Implementation notes:
- `_opencli_installed()` returns `bool(os.environ.get("DEEP_REACH_OPENCLI_BIN") or shutil.which("opencli"))`.
- `Environment.opencli_available`: if `browser_connected is None`, return `opencli_installed`; otherwise return `browser_connected and opencli_installed`.
- `environment_from_profile`: `connected = bool(profile.get("connected"))`; `installed = bool(connected or profile.get("daemon") or profile.get("cli_version") or _opencli_installed())`.
- `backend_unavailable_reason(spec, channel, env)`:
  - key path = `spec.key or channel.key_path`.
  - if `spec.requires_key` and no key path → `"requires a key but no key path is configured"`.
  - if `spec.requires_key` and not `env.keys.has(key_path)` → `f"{key_path} is missing"`.
  - if `spec.label.startswith("opencli-")` and not `env.opencli_available` → `"OpenCLI is not installed"` or `"OpenCLI browser is not connected"`.
  - else `None`.
- `action_availability` returns `(True, [])` on the first usable backend; otherwise `(False, reasons)`.
- `channel_availability` status mapping exactly as the spec.
- `runnable = bool(available_actions)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_availability.py -q`
Expected: PASS (`6 passed`).

- [ ] **Step 5: Commit**

```bash
git add deep_reach/runtime/availability.py tests/test_availability.py
git commit -m "feat: add environment-aware channel availability"
```

---

### Task 2: doctor / channels 使用环境状态

**Files:**
- Modify: `deep_reach/runtime/doctor.py`
- Modify: `deep_reach/cli.py`
- Test: `tests/test_doctor.py`

**Interfaces:**
- Consumes: `Environment`, `environment_from_profile`, `detect_environment`, `channel_availability` from Task 1.
- Produces:
  - doctor row fields: `status` (effective), `declared_status`, `runnable`, `available_actions`, `unavailable_actions`.
  - doctor summary fields: `needs_setup`, `runnable`.
  - `channels --json` rows gain the same four fields.

- [ ] **Step 1: Write the failing tests**

Extend `tests/test_doctor.py`:

```python
class FakeClient:
    def __init__(self, connected=True):
        self.connected = connected

    def version(self):
        return "2.0.3"

    def profile_status(self):
        if not self.connected:
            return {"connected": False, "error": "opencli is not installed"}
        return {
            "connected": True,
            "context_id": "test-context",
            "extension_version": "1.0.26",
        }


class DoctorEnvironmentTest(unittest.TestCase):
    def test_missing_opencli_marks_channels_needs_setup(self):
        from unittest import mock

        with mock.patch("deep_reach.runtime.availability.shutil.which", return_value=None):
            report = build_doctor_report(load_registry(), Keys({}), client=FakeClient(connected=False))
        rows = {row["name"]: row for row in report["channels"]}
        self.assertEqual(rows["youtube"]["status"], "needs_setup")
        self.assertEqual(rows["weibo"]["status"], "needs_setup")
        self.assertEqual(rows["amazon"]["status"], "degraded")
        self.assertEqual(rows["x"]["status"], "needs_setup")
        self.assertEqual(rows["ebay"]["status"], "needs_key")
        self.assertEqual(rows["bilibili"]["status"], "degraded")
        self.assertEqual(rows["github"]["status"], "ready")
        self.assertEqual(rows["youtube"]["declared_status"], "ready")
        self.assertEqual(report["summary"]["needs_setup"], 8)
        self.assertEqual(report["summary"]["runnable"], 9)
```

> 计数依据（opencli 未安装、无 key）：ready = web/github/v2ex；degraded = bilibili/xueqiu/amazon；needs_setup = youtube/weibo/x/reddit/xiaohongshu/zhihu/douyin/producthunt；needs_key = ebay/etsy/uspto/epo；experimental = kickstarter/cnipa/copyright；runnable = 3+3+3 = 9。

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_doctor.py -q`
Expected: FAIL because `status` is still the static registry value and fields are missing.

- [ ] **Step 3: Update `doctor.py`**

- Import `environment_from_profile`, `channel_availability`.
- Replace `_channel_status` with `channel_availability`.
- Build rows with `status`, `declared_status`, `runnable`, `available_actions`, `unavailable_actions`.
- `_next_action(channel, status, availability)`:
  - `needs_setup`: `安装/启用 OpenCLI Browser Bridge，然后运行 deep-reach doctor` plus `；{channel.next_action}` if present.
  - `degraded`: `部分动作当前不可用（...）；运行 deep-reach doctor 查看原因`.
  - otherwise `channel.next_action` or the existing fallback.
- Summary counts: add `needs_setup` and `runnable`.
- Text summary: add `degraded`, `needs_setup`, `runnable`.

- [ ] **Step 4: Update `cli.py` `cmd_channels`**

- Load keys with `_load_keys()` and return `CONFIG_ERROR` on failure.
- `env = detect_environment(keys)`.
- For each channel, compute `availability = channel_availability(channel, env)`.
- JSON rows: `status`, `declared_status`, `runnable`, `available_actions`, `unavailable_actions`.
- Text rows use `availability.status`.
- Add footer: `Status is environment-aware; run deep-reach doctor for browser/key details.`

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_doctor.py tests/test_product_contract.py tests/test_channels_no_key.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add deep_reach/runtime/doctor.py deep_reach/cli.py tests/test_doctor.py
git commit -m "feat: report environment-aware channel status"
```

---

### Task 3: URL 输入防护

**Files:**
- Modify: `deep_reach/backends/http.py`
- Modify: `deep_reach/backends/jina.py`
- Test: `tests/test_url_guard.py`

**Interfaces:**
- Produces: `validate_url(url: str) -> str` in `deep_reach/backends/http.py`.
- `fetch()` calls `validate_url(url)` before building the request.
- `jina._target_url()` calls `validate_url()` on the final http(s) URL.

- [ ] **Step 1: Write the failing tests**

```python
import os
import unittest
from unittest import mock

from deep_reach.backends.http import validate_url
from deep_reach.runtime.result import BAD_INPUT, ReachError


class UrlGuardTest(unittest.TestCase):
    def assert_blocked(self, url):
        with self.assertRaises(ReachError) as ctx:
            validate_url(url)
        self.assertEqual(ctx.exception.code, BAD_INPUT)

    def test_rejects_non_http_schemes(self):
        self.assert_blocked("file:///etc/passwd")
        self.assert_blocked("ftp://example.com/file")
        self.assert_blocked("example.com/no-scheme")

    def test_rejects_private_and_local_ip_literals(self):
        for url in (
            "http://127.0.0.1:8080/",
            "http://10.0.0.5/",
            "http://192.168.1.10/",
            "http://169.254.169.254/latest/meta-data/",
            "http://[::1]/",
            "http://0.0.0.0/",
        ):
            self.assert_blocked(url)

    def test_rejects_localhost_names(self):
        self.assert_blocked("http://localhost:3000/")
        self.assert_blocked("http://api.localhost/")

    def test_allows_public_https(self):
        with mock.patch(
            "deep_reach.backends.http.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("93.184.216.34", 0))],
        ):
            self.assertEqual(validate_url("https://example.com/a?b=1"), "https://example.com/a?b=1")

    def test_env_override_allows_private_but_not_file(self):
        with mock.patch.dict(os.environ, {"DEEP_REACH_ALLOW_PRIVATE_URLS": "1"}):
            self.assertEqual(validate_url("http://127.0.0.1:8080/"), "http://127.0.0.1:8080/")
            self.assert_blocked("file:///etc/passwd")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_url_guard.py -q`
Expected: FAIL with `ImportError` or because `validate_url` does not exist.

- [ ] **Step 3: Implement `validate_url` in `http.py`**

- Imports: `ipaddress`, `socket`, `lru_cache`, `os`.
- `PRIVATE_URL_ENV = "DEEP_REACH_ALLOW_PRIVATE_URLS"`.
- `_allow_private()`: truthy values `1/true/yes/on`.
- `_is_public_ip(text)`: strip `%scope`, parse with `ipaddress.ip_address`, return `.is_global`.
- `_host_is_private(host)` with `@lru_cache(maxsize=256)`:
  - lower; `localhost` / `*.localhost` → True.
  - if host parses as an IP → `not _is_public_ip(host)`.
  - else `socket.getaddrinfo(host, None)`; on `OSError` return False (let the request fail naturally); return True if any resolved address is non-global.
- `validate_url(url)`:
  - `urlparse`; scheme must be `http`/`https` → else `ReachError(BAD_INPUT, ...)`.
  - hostname required.
  - if not allowed private and `_host_is_private(hostname)` → `ReachError(BAD_INPUT, ...)`.
  - return url.
- Call `validate_url(url)` at the top of `fetch()`.
- In `jina._target_url`, import `validate_url` and return `validate_url(target)` for http(s), and `validate_url(f"https://www.amazon.com/dp/{target}")` for Amazon.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_url_guard.py -q`
Expected: PASS (`5 passed`).

- [ ] **Step 5: Commit**

```bash
git add deep_reach/backends/http.py deep_reach/backends/jina.py tests/test_url_guard.py
git commit -m "fix: reject non-http and private URLs in web readers"
```

---

### Task 4: keys 模板随包发布

**Files:**
- Move: `config/keys.example.yaml` → `deep_reach/data/keys.example.yaml`
- Modify: `MANIFEST.in`
- Modify: `deep_reach/cli.py`
- Modify: `README.md`
- Modify: `scripts/check_wheel.py`
- Test: `tests/test_keys.py`

**Interfaces:**
- `deep_reach.data` package contains `keys.example.yaml`.
- `cmd_setup` prints the packaged template path and uses it in the next-step hint.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_keys.py`:

```python
class PackagedTemplateTest(unittest.TestCase):
    def test_keys_template_is_packaged(self):
        from importlib import resources

        template = resources.files("deep_reach.data").joinpath("keys.example.yaml")
        self.assertTrue(template.is_file())
        text = template.read_text(encoding="utf-8")
        self.assertIn("official:", text)
        self.assertIn("xueqiu:", text)
        self.assertIn("browser:", text)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_keys.py -q`
Expected: FAIL because `deep_reach/data/keys.example.yaml` does not exist yet.

- [ ] **Step 3: Move the template and update packaging**

```bash
git mv config/keys.example.yaml deep_reach/data/keys.example.yaml
```

Update `MANIFEST.in`:

```text
include LICENSE
include NOTICE
include README.md
include CHANGELOG.md
recursive-include deep_reach/data *.yaml
recursive-include skill *.md
recursive-include tests *.py
recursive-include scripts *.py
```

Update `scripts/check_wheel.py`:
- Add `KEYS_TEMPLATE_SUFFIX = "deep_reach/data/keys.example.yaml"`.
- Inside the `ZipFile` block, assert exactly one match and `yaml.safe_load` it.
- Print `21 visible + 7 planned channels + keys template packaged`.

Update `cli.cmd_setup`:
- `from importlib import resources`.
- `template = resources.files("deep_reach.data").joinpath("keys.example.yaml")`.
- Add a `("template", str(template), "ok" if template.is_file() else "missing")` check.
- Change the final hint to `Next: copy {template} to {keys.path} (all keys optional).`

Update `README.md`:
- `config/keys.example.yaml` → `deep_reach/data/keys.example.yaml` (both occurrences).
- Add `deep-reach setup` prints the packaged template path.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_keys.py -q`
Expected: PASS.

Run: `uv build --wheel >/dev/null && uv run python scripts/check_wheel.py`
Expected: PASS with `keys template packaged`.

- [ ] **Step 5: Commit**

```bash
git add deep_reach/data/keys.example.yaml config/keys.example.yaml MANIFEST.in deep_reach/cli.py README.md scripts/check_wheel.py tests/test_keys.py
git commit -m "chore: package the keys template in the wheel"
```

---

### Task 5: EPO Range 回归测试

**Files:**
- Modify: `deep_reach/backends/epo.py`
- Test: `tests/test_wave2.py`

**Interfaces:**
- No behavior change. `_search(q, limit, timeout, keys, cache)` keeps sending `Range` in `params`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_wave2.py`:

```python
from unittest import mock

from deep_reach.backends.epo import _search
from deep_reach.runtime.keys import Keys


class EpoRequestTest(unittest.TestCase):
    def test_search_sends_range_as_query_parameter(self):
        captured = {}

        def fake_fetch_json(url, **kwargs):
            captured["url"] = url
            captured["kwargs"] = kwargs
            return EPO_PAYLOAD

        keys = Keys(
            {
                "official": {
                    "epo": {"consumer_key": "key", "consumer_secret": "secret"}
                }
            }
        )
        with mock.patch("deep_reach.backends.epo.fetch_json", side_effect=fake_fetch_json):
            items = _search('ta="desk organizer"', 5, 10.0, keys, {"access_token": "token"})

        self.assertEqual(len(items), 1)
        self.assertEqual(captured["kwargs"]["params"]["Range"], "1-5")
        self.assertNotIn("Range", captured["kwargs"].get("headers", {}))
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `uv run pytest tests/test_wave2.py::EpoRequestTest -q`
Expected: PASS on current code (the current query-parameter form is correct). If it passes, that is the point: this is a regression lock, not a behavior change. Note it in the commit message.

- [ ] **Step 3: Add the explanatory comment**

In `deep_reach/backends/epo.py` `_search`, add:

```python
# EPO OPS takes Range as a URL parameter ("&Range=xx-xx"), not a header.
# Official FAQ: https://www.epo.org/.../how-many-results-are
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_wave2.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deep_reach/backends/epo.py tests/test_wave2.py
git commit -m "test: lock the EPO OPS Range query parameter"
```

---

### Task 6: 文档与全量验证

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `README.md`
- Modify: `skill/SKILL.md`
- Verify: full test suite + wheel

- [ ] **Step 1: Update CHANGELOG**

Add at the top:

```markdown
## Unreleased

- `doctor` / `channels` 的 `status` 改为环境实测值（`ready` / `degraded` / `needs_setup` / `needs_login` / `needs_key` / `experimental`）；新增 `declared_status`、`runnable`、`available_actions`、`unavailable_actions`。
- `web read` / `http-read` 只允许 http/https，并默认拒绝 localhost、回环、私有/链路本地/保留地址；`DEEP_REACH_ALLOW_PRIVATE_URLS=1` 可显式放行私有地址。
- `keys.example.yaml` 移入 `deep_reach/data/` 并随 wheel 打包；`deep-reach setup` 打印包内模板路径。
- EPO OPS 的 `Range` 确认是 URL 参数，新增请求形状回归测试。
```

- [ ] **Step 2: Update README / SKILL wording**

- `channels` 描述从“默认只显示可用的渠道”改为“默认显示已实现渠道；当前环境是否可运行见每行 status，精确检查用 doctor”。
- 边界 section 增加：`web read` 默认只访问 http/https 公网地址；`DEEP_REACH_ALLOW_PRIVATE_URLS=1` 可放行私有地址。
- `skill/SKILL.md` 的 `channels` 行同步为“已实现渠道”。

- [ ] **Step 3: Run full verification**

Run: `uv run pytest -q`
Expected: all tests pass (85 + 新增，约 100).

Run: `uv build --wheel >/dev/null && uv run python scripts/check_wheel.py`
Expected: PASS with channels + keys template.

Run: `uv run deep-reach channels | head -40`
Expected: `youtube`/`weibo` 显示 `needs_setup`；`amazon`/`bilibili`/`xueqiu` 显示 `degraded`（opencli-only 动作不可用）；`github`/`v2ex`/`web` 保持 `ready`。

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md README.md skill/SKILL.md
git commit -m "docs: describe environment-aware status and URL policy"
```

---

## Self-Review

- **Spec coverage:** status → Task 1/2; URL guard → Task 3; keys template → Task 4; EPO → Task 5; changelog/docs → Task 6. All covered.
- **Step scan:** each task has a failing test, implementation, pass check, commit. Task 5 intentionally may pass immediately because the behavior is already correct; it is a regression lock.
- **Type consistency:** `ChannelAvailability` fields used in doctor/channels match Task 1; `Environment` constructor used in tests matches Task 1.
- **Review focus:** each line has an owning test: DNS/private → Task 3 tests; mixed actions → Task 1 `test_partial_actions_are_degraded`; needs_login → Task 1; key present → Task 1; scheme edge → Task 3; wheel template → Task 4.
- **Proportion:** plan is longer than the spec by design (it carries exact tests), but contains no full implementation bodies beyond small decision snippets.
