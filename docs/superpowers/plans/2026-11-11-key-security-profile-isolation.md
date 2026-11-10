# Key Security + Dedicated OpenCLI Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every Deep-Reach-controlled key leak and make OpenCLI run only against an explicitly bound dedicated Chrome profile.

**Architecture:** Add small runtime helpers for private paths, child-process environments, and secret redaction; harden HTTP redirects and key transport; then replace OpenCLI's `auto` profile detection with a strict explicit contextId and thread that state through availability, doctor, and CLI output.

**Tech Stack:** Python 3.10+, `urllib`, `PyYAML`, `unittest`, `pytest`, `ruff`, `uv`.

**Spec:** `docs/superpowers/specs/2026-11-11-key-security-profile-isolation-design.md`

## Global Constraints

- The only authoritative OpenCLI profile setting is `browser.opencli_profile`.
- `auto` and an empty value both mean **not configured**; OpenCLI must not run.
- OpenCLI always runs with `OPENCLI_WINDOW=background`; there is no true headless mode in Browser Bridge.
- `~/.deep-reach` and `~/.deep-reach/chrome-profile` are `0700`; `keys.yaml` is `0600` on POSIX.
- Never `chmod` the parent of a custom `DEEP_REACH_KEYS_FILE`; only the canonical `~/.deep-reach` directory.
- Redaction happens before JSON serialization and in every text formatter.
- No new runtime dependencies.
- bsk keeps its current-profile behavior; only its child environment is sanitized.
- Existing tests must keep passing; final suite must be green with no output claims without a command run.

## Review Focus

- A key echoed inside an HTTP error body or a successful item under `--text` must not reach stdout/stderr.
- A secret containing quotes, backslashes, newlines, or control characters must still be redacted after JSON escaping.
- A cross-origin redirect must not receive `Authorization`, `X-Subscription-Token`, `X-Goog-Api-Key`, or `Cookie`, including on POST redirects.
- `opencli_profile: auto`, empty, malformed, or env-only configuration must produce the same decision in `channels`, `doctor`, and the actual client.
- `deep-reach profile launch` must find Chrome on this macOS machine, or the documented migration flow is a dead end.

---

### Task 1: Private paths and keys-file hardening

**Files:**
- Create: `deep_reach/runtime/secure_paths.py`
- Modify: `deep_reach/runtime/keys.py`
- Modify: `deep_reach/runtime/state.py`
- Modify: `deep_reach/runtime/limits.py`
- Test: `tests/test_keys.py`, `tests/test_secure_paths.py`

**Interfaces:**
- Produces:
  - `ensure_private_dir(path: Path) -> str` — returns `""` on success, otherwise a human-readable note.
  - `tighten_file(path: Path) -> str` — returns `""` on success, otherwise a note.
  - `write_target(path: Path) -> Path` — resolves a symlink for atomic writes.
- Consumes: `ReachError`, `CONFIG_ERROR` from `runtime.result`.

- [ ] **Step 1: Write failing permission and YAML-error tests**

Create `tests/test_secure_paths.py`:

```python
import os
import tempfile
import unittest
from pathlib import Path

from deep_reach.runtime.secure_paths import ensure_private_dir, tighten_file


class SecurePathsTest(unittest.TestCase):
    def test_ensure_private_dir_tightens_existing_directory(self):
        if os.name == "nt":
            self.skipTest("POSIX permissions only")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "private"
            path.mkdir(mode=0o755)
            ensure_private_dir(path)
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)

    def test_tighten_file_skips_symlink(self):
        if os.name == "nt":
            self.skipTest("POSIX permissions only")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target.yaml"
            target.write_text("x", encoding="utf-8")
            link = Path(tmp) / "keys.yaml"
            link.symlink_to(target)
            note = tighten_file(link)
            self.assertIn("symlink", note)
            self.assertNotEqual(target.stat().st_mode & 0o777, 0o600)
```

Add to `tests/test_keys.py`:

```python
def test_load_tightens_keys_file_to_600(self):
    if os.name == "nt":
        self.skipTest("POSIX permissions only")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "keys.yaml"
        path.write_text("official:\n  github:\n    token: abc12345\n", encoding="utf-8")
        os.chmod(path, 0o644)
        keys = Keys.load(path)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertIn("keys.yaml", str(keys.path))

def test_yaml_error_does_not_echo_secret(self):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "keys.yaml"
        path.write_text(
            'official:\n  github:\n    token: "ghp_SECRETVALUE" [\n',
            encoding="utf-8",
        )
        with self.assertRaises(ReachError) as ctx:
            Keys.load(path)
        self.assertNotIn("ghp_SECRETVALUE", ctx.exception.message)
        self.assertIn("invalid YAML", ctx.exception.message)
        self.assertIn("line 3", ctx.exception.message)
```

- [ ] **Step 2: Run them and verify failure**

Run: `uv run pytest tests/test_keys.py tests/test_secure_paths.py -k 'tightens or yaml_error or symlink' -v`
Expected: FAIL because `secure_paths` does not exist, `Keys.load` does not
chmod, and the YAML parser message is echoed.

- [ ] **Step 3: Implement `secure_paths.py` and wire `Keys.load`**

`secure_paths.py` behavior:

- `ensure_private_dir`: `mkdir(mode=0o700, parents=True, exist_ok=True)`; on POSIX, if not a symlink and owned by `os.getuid()`, `chmod 0700` when group/other bits are set.
- `tighten_file`: no-op on Windows or missing file; skip symlinks and files owned by another uid with a note; otherwise `chmod 0600` when group/other bits are set.
- `write_target`: return `path.resolve()` when `path.is_symlink()`, else `path`.

`Keys.load`:

- After resolving `p`, call `tighten_file(p)` before reading.
- If `p.parent == Path.home() / ".deep-reach"`, call `ensure_private_dir(p.parent)`; never touch a custom override parent.
- Store `self.permission_note` (or `""`) on the returned `Keys`.
- `state.save` and `limits._lock_path` call `ensure_private_dir` on the canonical `~/.deep-reach` root before creating `state.json` or `locks/`; skip for custom override parents.
- Catch `yaml.YAMLError` before the generic `Exception` branch:

```python
except yaml.YAMLError as exc:
    mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
    where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
    raise ReachError(CONFIG_ERROR, f"cannot load keys file {p}: invalid YAML{where}") from None
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_keys.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deep_reach/runtime/secure_paths.py deep_reach/runtime/keys.py deep_reach/runtime/state.py deep_reach/runtime/limits.py tests/test_keys.py tests/test_secure_paths.py
git commit -m "fix: harden keys file permissions and YAML errors"
```

---

### Task 2: Secret registration and output redaction

**Files:**
- Modify: `deep_reach/runtime/result.py`
- Modify: `deep_reach/runtime/keys.py`
- Modify: `deep_reach/cli.py`
- Modify: `deep_reach/runtime/doctor.py`
- Test: `tests/test_result_redaction.py`

**Interfaces:**
- Produces in `runtime.result`:
  - `is_secret_path(dotted: str) -> bool`
  - `register_secret(value: object) -> None`
  - `clear_secrets() -> None`
  - `redact_text(text: object) -> str`
  - `redact_obj(value: object) -> object`
  - `sanitize_url(url: str) -> str`
- Consumes: `Keys` values from Task 1.

- [ ] **Step 1: Write failing redaction tests**

Create `tests/test_result_redaction.py`:

```python
import unittest

from deep_reach.runtime.result import (
    ReachError, clear_secrets, dump, redact_text, register_secret, sanitize_url,
    UPSTREAM_BROKEN,
)


class RedactionTest(unittest.TestCase):
    def setUp(self):
        clear_secrets()

    def tearDown(self):
        clear_secrets()

    def test_error_and_dump_redact_registered_secret(self):
        register_secret("super-secret-token")
        error = ReachError(UPSTREAM_BROKEN, "failed with super-secret-token")
        self.assertNotIn("super-secret-token", error.message)
        self.assertNotIn("super-secret-token", dump({"error": error.message}))

    def test_escaped_secret_is_redacted_before_serialization(self):
        secret = 'a"b\\c\nd'
        register_secret(secret)
        self.assertNotIn("a\\\"b", dump({"value": secret}))

    def test_sanitize_url_redacts_credential_query_params(self):
        url = "https://example.test/x?key=abc123&ok=1&access_token=tok"
        cleaned = sanitize_url(url)
        self.assertNotIn("abc123", cleaned)
        self.assertNotIn("tok", cleaned)
        self.assertIn("ok=1", cleaned)

    def test_text_summary_and_doctor_text_redact(self):
        from deep_reach.cli import _text_summary
        from deep_reach.runtime.doctor import format_doctor_text

        register_secret("super-secret-token")
        summary = _text_summary(
            {
                "ok": True,
                "channel": "x",
                "action": "search",
                "backend": "b",
                "tier": "p0",
                "items": [{"title": "leak super-secret-token"}],
            }
        )
        self.assertNotIn("super-secret-token", summary)
        report = {
            "opencli": {},
            "profile": {"error": "leak super-secret-token"},
            "keys_file": "/tmp/keys",
            "keys_file_exists": True,
            "channels": [],
            "summary": {"tiers": {}},
            "state": {},
            "quota": {},
        }
        self.assertNotIn("super-secret-token", format_doctor_text(report))

    def test_short_values_are_not_registered(self):
        register_secret("abc")
        self.assertEqual(redact_text("abc"), "abc")
```

- [ ] **Step 2: Run them and verify failure**

Run: `uv run pytest tests/test_result_redaction.py -v`
Expected: FAIL because the functions do not exist.

- [ ] **Step 3: Implement redaction in `result.py`**

- `_SECRETS: set[str]`; `_SECRET_PATH_RE` matches credential suffixes:
  `api_key`, `apikey`, `api_token`, `token`, `secret`, `client_secret`,
  `consumer_key`, `consumer_secret`, `password`, `passwd`, `cookie`,
  `access_key`, `private_key`, `credential(s)`.
- `register_secret`: strip, ignore empty, length `< 6`, and placeholder values
  (`PLACEHOLDER_VALUES`).
- `redact_text`: replace registered values longest-first with `[redacted]`.
- `redact_obj`: recurse dict keys and values, list, tuple.
- `ReachError.__init__`: store `redact_text(message)` and `redact_text(hint)`.
- `dump`: `json.dumps(redact_obj(data), ...)`.
- `sanitize_url`: `urlsplit`/`parse_qsl`/`urlencode`; replace values of
  credential-looking query params with `[redacted]`.
- Export `PLACEHOLDER_VALUES`; in `keys.py` use it for `PLACEHOLDERS` to avoid
  two different lists.

- [ ] **Step 4: Register secrets from `Keys`**

- In `Keys.__init__`, recursively walk `data`; when `is_secret_path(prefix)`,
  call `register_secret(value)`.
- In `Keys.get`, when `is_secret_path(dotted)`, register the returned value
  before returning it. This covers env overrides.

- [ ] **Step 5: Apply redaction to text output**

- `cli._text_summary`: return `redact_text("\n".join(lines))`.
- `cli.cmd_setup`: print `redact_text(...)` of the assembled output.
- `cli.cmd_channels` text output: pass the final string through `redact_text`.
- `cmd_channel_help` and `cmd_profile` text: wrap dynamic strings with
  `redact_text`.
- `doctor.format_doctor_text`: return `redact_text("\n".join(lines))`.

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_result_redaction.py tests/test_keys.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add deep_reach/runtime/result.py deep_reach/runtime/keys.py deep_reach/cli.py deep_reach/runtime/doctor.py tests/test_result_redaction.py
git commit -m "fix: redact secrets from errors, JSON, and text output"
```

---

### Task 3: Sanitized child environments

**Files:**
- Create: `deep_reach/runtime/child_env.py`
- Modify: `deep_reach/backends/opencli.py`
- Modify: `deep_reach/backends/bsk_guard.py`
- Modify: `deep_reach/runtime/profile.py`
- Modify: `deep_reach/cli.py`
- Test: `tests/test_child_env.py`, `tests/test_cli_bsk.py`

**Interfaces:**
- Produces: `child_env(extra: Optional[dict[str, str]] = None) -> dict[str, str]`.
- Consumes: `os.environ` only.

- [ ] **Step 1: Write failing env-sanitization tests**

Create `tests/test_child_env.py`:

```python
import os
import unittest
from unittest import mock

from deep_reach.runtime.child_env import child_env


class ChildEnvTest(unittest.TestCase):
    def test_strips_deep_reach_and_credential_names(self):
        with mock.patch.dict(
            os.environ,
            {
                "DEEP_REACH_OFFICIAL_GITHUB_TOKEN": "a",
                "DEEP_REACH_OPENCLI_BIN": "/bin/opencli",
                "GITHUB_TOKEN": "b",
                "MY_API_KEY": "c",
                "NPM_CONFIG__AUTHTOKEN": "d",
                "PATH": "/bin",
                "HOME": "/tmp",
            },
            clear=False,
        ):
            env = child_env()
        self.assertNotIn("DEEP_REACH_OFFICIAL_GITHUB_TOKEN", env)
        self.assertNotIn("DEEP_REACH_OPENCLI_BIN", env)
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertNotIn("MY_API_KEY", env)
        self.assertNotIn("NPM_CONFIG__AUTHTOKEN", env)
        self.assertEqual(env["PATH"], "/bin")
        self.assertEqual(env["HOME"], "/tmp")

    def test_extra_values_are_added(self):
        env = child_env({"OPENCLI_WINDOW": "background"})
        self.assertEqual(env["OPENCLI_WINDOW"], "background")
```

Add to `tests/test_cli_bsk.py`:

```python
def test_bsk_subprocess_gets_sanitized_env(self):
    with mock.patch("deep_reach.backends.bsk_guard.subprocess.run") as run, \
         mock.patch.dict("os.environ", {"DEEP_REACH_OFFICIAL_GITHUB_TOKEN": "x"}):
        run.return_value.returncode = 0
        run_bsk(["status"])
    env = run.call_args.kwargs["env"]
    self.assertNotIn("DEEP_REACH_OFFICIAL_GITHUB_TOKEN", env)
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest tests/test_child_env.py tests/test_cli_bsk.py -k env -v`
Expected: FAIL because `child_env` is missing and bsk inherits env.

- [ ] **Step 3: Implement `child_env`**

- Drop names starting with `DEEP_REACH_` (case-insensitive).
- Drop names matching `(token|secret|password|passwd|cookie|api[_-]?key|apikey|access[_-]?key|private[_-]?key|credential)` case-insensitive.
- Merge `extra` after filtering.

- [ ] **Step 4: Wire every subprocess**

- `OpenCLIClient._run`: `env = child_env({...explicit OPENCLI_*...})`.
- `OpenCLIClient._kill_tree`: `subprocess.run(["taskkill", ...], env=child_env())`
  on Windows.
- `run_bsk`: `subprocess.run([...], env=child_env())`.
- `profile.launch`: `subprocess.Popen([...], env=child_env())`.
- `cli.cmd_setup`: `subprocess.run([...], env=child_env())`.
- `cli._latest_opencli_version`: `subprocess.run([...], env=child_env())`.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_child_env.py tests/test_cli_bsk.py tests/test_opencli_backend.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add deep_reach/runtime/child_env.py deep_reach/backends/opencli.py deep_reach/backends/bsk_guard.py deep_reach/runtime/profile.py deep_reach/cli.py tests/test_child_env.py tests/test_cli_bsk.py
git commit -m "fix: sanitize environment for external CLIs"
```

---

### Task 4: Redirect safety and key transport

**Files:**
- Modify: `deep_reach/backends/http.py`
- Modify: `deep_reach/backends/jina.py`
- Modify: `deep_reach/backends/xueqiu.py`
- Modify: `deep_reach/backends/public.py`
- Test: `tests/test_http_redirect.py`, `tests/test_r5_apis.py`, `tests/test_p2_common.py`

**Interfaces:**
- Produces in `runtime.result`: `sanitize_url` (Task 2).
- Produces in `backends.http`: validated redirect handler with cross-origin
  credential stripping; `fetch`/`fetch_json` errors use `sanitize_url`.
- Consumes: YouTube key from `Keys.get("official.youtube.api_key")`.

- [ ] **Step 1: Write failing redirect and YouTube tests**

Create `tests/test_http_redirect.py` with two local `http.server` threads:

- Server A replies `302` to server B with
  `Location: http://127.0.0.1:<B>/target?key=SECRET&ok=1`.
- Server B records headers and query.
- Set `DEEP_REACH_ALLOW_PRIVATE_URLS=1` during the test.
- Call `fetch("http://127.0.0.1:<A>/start", timeout=5, headers={...})` with
  `Authorization`, `X-Subscription-Token`, `X-Goog-Api-Key`, `Cookie`, and
  `X-Public`.
- Assert B sees `X-Public` only; no credential header; `key` query removed and
  `ok=1` kept.
- A same-origin redirect on server A keeps all headers and query params,
  proving the stripping is origin-scoped rather than unconditional.

Add to `tests/test_r5_apis.py`:

```python
def test_youtube_uses_header_not_query_key(self):
    keys = Keys({"official": {"youtube": {"api_key": "yt-secret-123"}}})
    with mock.patch("deep_reach.backends.public.fetch_json") as fetch_json:
        fetch_json.return_value = {"items": []}
        _youtube_search({"query": "x", "limit": 1}, 5, keys)
    url = fetch_json.call_args.args[0]
    kwargs = fetch_json.call_args.kwargs
    self.assertNotIn("key=", url)
    self.assertNotIn("yt-secret-123", url)
    self.assertEqual(kwargs["headers"]["X-Goog-Api-Key"], "yt-secret-123")
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest tests/test_http_redirect.py tests/test_r5_apis.py -k 'redirect or youtube_uses' -v`
Expected: FAIL because headers are forwarded and YouTube uses `key=`.

- [ ] **Step 3: Implement redirect stripping and URL sanitization**

- `http.py`: add `_origin(url)`, `_strip_sensitive_headers(headers)`,
  `_strip_sensitive_query(url)`, and `ValidatedRedirectHandler`.
- Sensitive header regex: `(authorization|cookie|token|secret|key|auth)`.
- Sensitive query regex: `^(key|api[_-]?key|token|access_token|secret|password|cookie|auth|signature|sig)$`.
- In `redirect_request`: validate the new URL, call `super()`, and if origins
  differ, filter headers and rewrite `full_url` without sensitive query params.
- Use `sanitize_url(url)` in `fetch`/`fetch_json` error messages.
- Rename the existing `_ValidatingRedirectHandler` to `ValidatedRedirectHandler`
  and keep `_ValidatingRedirectHandler = ValidatedRedirectHandler` as a
  compatibility alias for any test imports.

- [ ] **Step 4: Fix Jina and Xueqiu openers**

- `JinaReader.read`: call `fetch(url, timeout=..., headers=headers, accept="text/plain", code_map={401: NEED_SETUP, 403: NEED_SETUP, 429: QUOTA_EXHAUSTED})`; map those codes to the existing messages.
- `_Session` in `xueqiu.py`: add `ValidatedRedirectHandler()` to `build_opener`.
- Update `tests/test_p2_common.py` `JinaRateLimitTest`: it currently patches
  `deep_reach.backends.jina.urllib.request.urlopen`. Patch
  `deep_reach.backends.jina.fetch` instead, raising
  `ReachError(QUOTA_EXHAUSTED, "HTTP 429")`, and assert the Jina-specific
  quota message.

- [ ] **Step 5: Move YouTube key to `X-Goog-Api-Key`**

- `_youtube_get(url, params, timeout, action, headers=None)`; pass headers to `fetch_json`.
- `_youtube_search` / `_youtube_read`: remove `"key"` from params; pass
  `{"X-Goog-Api-Key": str(keys.get("official.youtube.api_key"))}`.

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_http_redirect.py tests/test_r5_apis.py tests/test_p2_http.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add deep_reach/backends/http.py deep_reach/backends/jina.py deep_reach/backends/xueqiu.py deep_reach/backends/public.py tests/test_http_redirect.py tests/test_r5_apis.py tests/test_p2_common.py
git commit -m "fix: strip credentials on cross-origin redirects"
```

---

### Task 5: Strict OpenCLI profile resolution

**Files:**
- Create: `deep_reach/runtime/browser_config.py`
- Modify: `deep_reach/backends/opencli.py`
- Modify: `deep_reach/cli.py`
- Modify: `deep_reach/runtime/doctor.py`
- Test: `tests/test_opencli_backend.py`, `tests/test_profile.py`

**Interfaces:**
- Produces: `normalize_opencli_profile(value: object) -> str` in
  `runtime.browser_config`.
- Produces: `OpenCLIClient(profile: Optional[str])` with strict behavior.
- Consumes: `child_env` from Task 3.

- [ ] **Step 1: Write failing strict-profile tests**

Update the existing `FakeClient._run` in `tests/test_opencli_backend.py` to accept
`with_profile: bool = True`, because `profile_status`/`version` call it with
`with_profile=False`.

Add to `tests/test_opencli_backend.py`:

```python
def test_no_profile_is_need_setup(self):
    client = OpenCLIClient(bin_path="fake-opencli", profile="")
    with self.assertRaises(ReachError) as ctx:
        client._run(["bilibili", "search", "x"], timeout=5)
    self.assertEqual(ctx.exception.code, NEED_SETUP)
    self.assertIn("dedicated", ctx.exception.message.lower())

def test_auto_is_treated_as_unconfigured(self):
    client = OpenCLIClient(bin_path="fake-opencli", profile="auto")
    self.assertEqual(client.profile, "")

def test_legacy_env_does_not_set_profile(self):
    with mock.patch.dict(os.environ, {"DEEP_REACH_OPENCLI_PROFILE": "ctx-1234"}):
        client = OpenCLIClient(bin_path="fake-opencli")
    self.assertEqual(client.profile, "")

def test_profile_status_reports_selected_context(self):
    client = OpenCLIClient(bin_path="fake-opencli", profile="ctx-1234")
    payload = {
        "ok": True,
        "data": {
            "extensionConnected": True,
            "profiles": [
                {"contextId": "main-999", "extensionVersion": "1.0"},
                {"contextId": "ctx-1234", "extensionVersion": "2.0"},
            ],
        },
    }
    with mock.patch.object(client, "_run", return_value=SimpleNamespace(stdout=json.dumps(payload), stderr="", returncode=0)):
        status = client.profile_status()
    self.assertTrue(status["configured"])
    self.assertTrue(status["connected"])
    self.assertEqual(status["context_id"], "ctx-1234")
    self.assertEqual(status["profile_ids"], ["main-999", "ctx-1234"])
```

Add to `tests/test_profile.py`:

```python
def test_set_context_rejects_auto(self):
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["DEEP_REACH_KEYS_FILE"] = str(Path(tmp) / "keys.yaml")
        with self.assertRaises(ReachError):
            set_context("auto")

def test_set_context_rejects_whitespace(self):
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["DEEP_REACH_KEYS_FILE"] = str(Path(tmp) / "keys.yaml")
        with self.assertRaises(ReachError):
            set_context("ctx 123")
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest tests/test_opencli_backend.py tests/test_profile.py -k 'profile or context' -v`
Expected: FAIL because `auto` is still accepted and `_run` does not require a profile.

- [ ] **Step 3: Implement `browser_config.py` and strict client**

- `normalize_opencli_profile`: strip; return `""` for `""`, `auto`, `none`,
  `unset`, or anything not matching `^[A-Za-z0-9_-]{4,64}$`.
- `OpenCLIClient.__init__`: `self.profile = normalize_opencli_profile(profile)`;
  remove `DEEP_REACH_OPENCLI_PROFILE`.
- `_run`: when `with_profile` and `self.profile` is empty, raise
  `ReachError(NEED_SETUP, "OpenCLI requires a dedicated browser profile", hint="Run `deep-reach profile launch`, install the extension there, then `deep-reach profile set <contextId>`.")`.
  Otherwise set `OPENCLI_PROFILE`, `OPENCLI_WINDOW`, clear CDP vars.
- Delete `_detect_profile` and `_profile_resolved`.
- `profile_status`: parse `profiles`, compute `profile_ids`, selected
  `context_id`, `configured`, `connected`, `setting`, `error`.

- [ ] **Step 4: Wire CLI and doctor client construction**

- `cli._register_backends`: normalize `keys.get("browser.opencli_profile")`
  and pass it.
- `doctor.build_doctor_report`: same normalization.
- `profile.status`: same normalization.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_opencli_backend.py tests/test_profile.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add deep_reach/runtime/browser_config.py deep_reach/backends/opencli.py deep_reach/cli.py deep_reach/runtime/doctor.py deep_reach/runtime/profile.py tests/test_opencli_backend.py tests/test_profile.py
git commit -m "feat: require an explicit dedicated OpenCLI profile"
```

---

### Task 6: Availability, doctor schema, and profile UI

**Files:**
- Modify: `deep_reach/runtime/availability.py`
- Modify: `deep_reach/runtime/doctor.py`
- Modify: `deep_reach/cli.py`
- Modify: `deep_reach/runtime/profile.py`
- Modify: `scripts/smoke.py`
- Test: `tests/test_availability.py`, `tests/test_doctor.py`, `tests/test_cli_channels.py`

**Interfaces:**
- Consumes: `normalize_opencli_profile` from Task 5.
- Produces: `Environment.opencli_profile_configured: bool`.
- Produces: doctor `keys_file_mode`, `keys_file_secure`, `keys_file_note`,
  `profile.setting/configured/connected/context_id/profile_ids/profiles/window/error/next`.

- [ ] **Step 1: Write failing availability and doctor tests**

Update the `env()` helper in `tests/test_availability.py` to accept
`profile_configured: bool = True` and pass it into `Environment`, so existing
OpenCLI tests keep their old expectations and the new strict tests opt out
explicitly.

Update `tests/test_doctor.py` `FakeClient.profile_status` to return the new
fields: `setting`, `configured`, `connected`, `context_id`, `profile_ids`,
`profiles`, `error`. Update the `profile_status` mocks in
`tests/test_cli_channels.py` the same way.

Add these imports to `tests/test_availability.py` if missing: `import os`,
`from unittest import mock`, and `detect_environment` from
`deep_reach.runtime.availability`.

Add to `tests/test_availability.py`:

```python
def test_opencli_without_profile_is_needs_setup(self):
    result = channel_availability(
        channel("ready", [BackendSpec("opencli-demo", "search")]),
        Environment(keys=Keys({}), opencli_installed=True,
                    browser_connected=None, opencli_profile_configured=False),
    )
    self.assertEqual(result.status, "needs_setup")
    self.assertFalse(result.runnable)

def test_opencli_with_profile_and_connection_is_ready(self):
    result = channel_availability(
        channel("ready", [BackendSpec("opencli-demo", "search")]),
        Environment(keys=Keys({}), opencli_installed=True,
                    browser_connected=True, opencli_profile_configured=True),
    )
    self.assertEqual(result.status, "ready")

def test_env_only_profile_counts_as_configured(self):
    with mock.patch.dict(
        os.environ, {"DEEP_REACH_BROWSER_OPENCLI_PROFILE": "ctx-1234"}
    ):
        detected = detect_environment(
            Keys({"browser": {"opencli_profile": ""}})
        )
    self.assertTrue(detected.opencli_profile_configured)
```

Add to `tests/test_doctor.py`:

```python
def test_doctor_reports_keys_mode_and_profile_schema(self):
    registry = load_registry()
    report = build_doctor_report(registry, Keys({}), client=FakeClient())
    self.assertIn("keys_file_mode", report)
    self.assertIn("keys_file_secure", report)
    profile = report["profile"]
    for name in ("setting", "configured", "connected", "context_id",
                 "profile_ids", "profiles", "window", "error", "next"):
        self.assertIn(name, profile)
    self.assertEqual(profile["window"], "background")

def test_doctor_text_warns_when_profile_is_unconfigured(self):
    text = format_doctor_text(build_doctor_report(load_registry(), Keys({}), client=FakeClient()))
    self.assertIn("not configured", text)
    self.assertIn("profile launch", text)
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest tests/test_availability.py tests/test_doctor.py -v`
Expected: FAIL because the environment field and report fields do not exist.

- [ ] **Step 3: Update availability**

- Add `opencli_profile_configured: bool = False` to `Environment`.
- `opencli_available`: require `opencli_installed` and
  `opencli_profile_configured`; when `browser_connected` is not `None`, also
  require `browser_connected`.
- `detect_environment`: set `opencli_profile_configured=bool(normalize_opencli_profile(keys.get("browser.opencli_profile")))`.
- `environment_from_profile`: use `profile.get("configured")` and
  `profile.get("connected")`.
- `backend_unavailable_reason`: distinguish not installed / no profile /
  profile not connected.
- Add `_opencli_hint(env)` with the install → launch → set → connect sequence
  and use it in `needs_setup` and `needs_login` branches.

- [ ] **Step 4: Update doctor and profile CLI**

- `build_doctor_report`: add `keys_file_mode` (`oct(mode)[2:]` or `None` on
  Windows), `keys_file_secure` (no group/other bits), `keys_file_note`.
- `profile` block per the spec schema; add `window="background"` and `next`.
- `format_doctor_text`: show `browser: dedicated <ctx> (connected)` or
  `browser: not configured (<next>)`; add a background-mode line; warn when
  keys are insecure.
- `cmd_profile status`: print setting, configured, selected context,
  `profile_ids`, connected, error.
- `cmd_profile set`: catch `ReachError` and print code/message, return 2.
- `cmd_setup`: add keys mode and profile-config state to the checks and next
  steps; use `ensure_private_dir` when creating the keys parent.
- `scripts/smoke.py`: replace `or "auto"` with
  `normalize_opencli_profile(...)`, and treat an empty profile as skipped
  rather than running OpenCLI without `OPENCLI_PROFILE`.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_availability.py tests/test_doctor.py tests/test_cli_channels.py tests/test_cli_capabilities.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add deep_reach/runtime/availability.py deep_reach/runtime/doctor.py deep_reach/runtime/profile.py deep_reach/cli.py scripts/smoke.py tests/test_availability.py tests/test_doctor.py tests/test_cli_channels.py
git commit -m "feat: surface dedicated-profile setup in doctor and channels"
```

---

### Task 7: Profile launch hardening and Chrome discovery

**Files:**
- Modify: `deep_reach/runtime/profile.py`
- Test: `tests/test_profile.py`

**Interfaces:**
- Consumes: `secure_paths.ensure_private_dir`, `child_env`, `normalize_opencli_profile`.
- Produces: `chrome_path()` that finds the macOS app bundle.

- [ ] **Step 1: Write failing launch tests**

Add `import sys`, `chrome_path`, and `launch` to `tests/test_profile.py` if
missing.

Add to `tests/test_profile.py`:

```python
def test_chrome_path_finds_macos_app_bundle(self):
    if sys.platform != "darwin":
        self.skipTest("macOS path")
    target = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    with mock.patch(
        "deep_reach.runtime.profile.Path.exists",
        autospec=True,
        side_effect=lambda path: str(path) == target,
    ), mock.patch("deep_reach.runtime.profile.shutil.which", return_value=None):
        self.assertEqual(chrome_path(), target)

def test_profile_launch_uses_sanitized_env_and_private_dir(self):
    fake = mock.Mock(pid=1234)
    with mock.patch("deep_reach.runtime.profile.chrome_path", return_value="/chrome"), \
         mock.patch("deep_reach.runtime.profile.profile_dir", return_value=Path(tempfile.mkdtemp())), \
         mock.patch("deep_reach.runtime.profile.subprocess.Popen", return_value=fake) as popen, \
         mock.patch.dict("os.environ", {"DEEP_REACH_OFFICIAL_GITHUB_TOKEN": "x"}):
        result = launch()
    self.assertTrue(result["ok"])
    env = popen.call_args.kwargs["env"]
    self.assertNotIn("DEEP_REACH_OFFICIAL_GITHUB_TOKEN", env)
```

Also update `test_set_context_survives_chmod_failure` to patch
`deep_reach.runtime.secure_paths.os.chmod` (the atomic writer and private-path
helper live there), not only `deep_reach.runtime.profile.os.chmod`.

Add:

```python
def test_set_context_preserves_symlink_target(self):
    if os.name == "nt":
        self.skipTest("symlinks need privileges on Windows")
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "dotfiles-keys.yaml"
        target.write_text("version: 1\nbrowser:\n  opencli_profile: \"\"\n", encoding="utf-8")
        link = Path(tmp) / "keys.yaml"
        link.symlink_to(target)
        os.environ["DEEP_REACH_KEYS_FILE"] = str(link)
        set_context("ctx-1234")
        self.assertTrue(link.is_symlink())
        self.assertIn('opencli_profile: "ctx-1234"', target.read_text(encoding="utf-8"))
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest tests/test_profile.py -k 'chrome_path or launch' -v`
Expected: FAIL because the macOS path is missing and launch does not pass `env`.

- [ ] **Step 3: Implement**

- Add the macOS/Linux candidate paths from the spec to `chrome_path()`.
- `launch`: `path.mkdir(mode=0o700, parents=True, exist_ok=True)`, call
  `ensure_private_dir(path)`, pass `env=child_env()` to `Popen`.
- `set_context`: normalize/validate; resolve symlink with `write_target`;
  atomic temp-file write with `0600` and `os.replace`; chmod target `0600` via
  `secure_paths.tighten_file`; preserve comments. Call `ensure_private_dir`
  only when the target parent is the canonical `~/.deep-reach`, never a custom
  override parent.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_profile.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deep_reach/runtime/profile.py tests/test_profile.py
git commit -m "fix: make profile launch work and keep its files private"
```

---

### Task 8: Config, docs, changelog, and full verification

**Files:**
- Modify: `deep_reach/data/keys.example.yaml`
- Modify: `README.md`
- Modify: `PRODUCT.md`
- Modify: `REFACTOR_PLAN.md`
- Modify: `SECURITY.md`
- Modify: `skill/SKILL.md`
- Modify: `skill/references/capabilities.md`
- Modify: `CHANGELOG.md`
- Test: `tests/test_config_example.py`, `tests/test_docs_contract.py`

**Interfaces:**
- Consumes: all previous tasks.

- [ ] **Step 1: Write failing config/doc assertions**

Add to `tests/test_config_example.py`:

```python
def test_opencli_profile_defaults_to_empty_and_never_auto(self):
    data = yaml.safe_load(
        (ROOT / "deep_reach/data/keys.example.yaml").read_text(encoding="utf-8")
    )
    self.assertEqual(data["browser"]["opencli_profile"], "")
    self.assertNotIn("auto", str(data["browser"]["opencli_profile"]))
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest tests/test_config_example.py -v`
Expected: FAIL because the template still contains `auto`.

- [ ] **Step 3: Update config and docs**

- `keys.example.yaml`: `opencli_profile: ""` with the dedicated-profile
  comment; keep `bsk_guard: true`.
- `runtime/profile.py` module docstring: remove the `auto` description; state
  that a contextId is required and the dedicated profile is the only mode.
- `README.md`: strict profile flow; explain `background` vs. true headless;
  migration for `auto`; keys permission/redaction guarantees.
- `PRODUCT.md`: no-main-profile promise and key safety.
- `REFACTOR_PLAN.md`: dedicated profile is the only supported mode.
- `SECURITY.md`: keys `0600`/directory `0700`, sanitized child environments,
  redaction, redirect header stripping, dedicated profile guarantee, and the
  background-vs-headless boundary.
- `skill/SKILL.md` and `skill/references/capabilities.md`: P1 is
  `needs_setup` until a dedicated profile is bound.
- `CHANGELOG.md`: v0.12.0 security fixes and breaking change.

- [ ] **Step 4: Run config/doc tests**

Run: `uv run pytest tests/test_config_example.py tests/test_docs_contract.py -v`
Expected: PASS.

- [ ] **Step 5: Full verification**

Run:

```bash
uv run pytest -q
uv run ruff check .
uv build
uv run python scripts/check_wheel.py dist/deep_reach-0.12.0-py3-none-any.whl
git diff --check
```

Expected: all tests pass, ruff clean, wheel check reports 21 visible channels,
no whitespace errors.

- [ ] **Step 6: Manual CLI smoke**

Run:

```bash
uv run deep-reach doctor
uv run deep-reach channels
uv run deep-reach profile status
uv run deep-reach roadmap; test $? -eq 2
```

Expected: doctor shows `browser: not configured` with the launch/set next
step; no traceback; `roadmap` exits 2.

- [ ] **Step 7: Commit**

```bash
git add deep_reach/data/keys.example.yaml README.md PRODUCT.md REFACTOR_PLAN.md SECURITY.md skill/SKILL.md skill/references/capabilities.md CHANGELOG.md tests/test_config_example.py
git commit -m "docs: document strict dedicated profile and key hardening"
```
