# Key security + dedicated OpenCLI profile

Date: 2026-11-11
Status: awaiting approval

## Intent

Two product requirements:

1. Keys must not leak through any Deep-Reach-controlled path.
2. OpenCLI must never silently use the user's main Chrome profile. P1 runs only
   against an explicitly bound dedicated profile.

The user chose the strict option: no `auto` profile detection, no fallback to
the first connected profile.

## Goals

- `~/.deep-reach/keys.yaml` is mode `600`; `~/.deep-reach` and the dedicated
  Chrome profile directory are mode `700`.
- Every external child process gets a sanitized environment: no `DEEP_REACH_*`
  variables and no variables whose names look like credentials.
- YAML parse errors never echo the offending line.
- Known secret values are redacted from `ReachError` messages, hints, and all
  JSON output.
- Cross-origin redirects never forward `Authorization`, `x-api-key`,
  `Cookie`, or similar headers. Jina and Xueqiu use the same validated opener.
- `opencli_profile` must be an explicit contextId. Empty, missing, or `auto`
  means P1 is not runnable and `doctor` shows the setup steps.
- OpenCLI keeps `OPENCLI_WINDOW=background`; no foreground window is opened by
  Deep-Reach.
- All changes are covered by offline tests; docs and CHANGELOG are updated.

## Non-goals

- Encrypting keys at rest or integrating macOS Keychain / Windows Credential
  Manager. Without a user-supplied master secret this adds complexity without
  a real boundary; file permissions plus a dedicated OS account are the
  current boundary.
- Isolating bsk. Previous decision stands: bsk uses the current browser profile
  with warnings. This design only hardens its child environment.
- True headless OpenCLI. Browser Bridge supports `foreground` and `background`
  only. True headless requires CDP, which bypasses the extension and the
  dedicated profile's login state; it is a separate product decision.
- Windows ACL hardening. POSIX `chmod` is best-effort; Windows relies on the
  user profile ACL.

## Approaches considered

### Key storage

- A. Application-level hardening: file modes, child env sanitization, error
  redaction, redirect header stripping. No new dependency, works headless.
- B. OS keychain: stronger at-rest story, but requires per-platform code and a
  migration path, and still leaves process/error leaks.

Chosen: A. It closes the concrete gaps with no new dependency.

### OpenCLI profile

- A. Strict dedicated profile: explicit contextId only; no auto-detection.
- B. Default off, explicit `auto` opt-in to share the main profile.
- C. Keep `auto`, warn only.

Chosen: A, per the user's decision. B and C still allow a silent or
easy-to-miss main-profile path.

### Headless

- A. Keep `background` window mode: no foreground window, but Chrome and the
  dedicated profile must be running.
- B. CDP headless: `--headless=new` plus `OPENCLI_CDP_ENDPOINT`. Loses the
  Browser Bridge extension and the dedicated profile's logged-in session;
  login-required sites become impractical.

Chosen: A. Document that Browser Bridge has no true headless mode.

## Resolved during the builder check

- Redirect stripping must be pattern-based, not a fixed list: Brave sends
  `X-Subscription-Token`; YouTube will move to `X-Goog-Api-Key`.
- `browser.opencli_profile` is the single authoritative setting, including its
  generic `DEEP_REACH_BROWSER_OPENCLI_PROFILE` override. The separate
  `DEEP_REACH_OPENCLI_PROFILE` lookup is removed.
- Redaction applies to text output and to the Python object before JSON
  serialization, so quoting/escaping cannot bypass it.
- `~/.deep-reach` is created/tightened by every writer, not only by
  `Keys.load` when the file already exists.
- `doctor --json` keeps the existing keys fields and adds an explicit profile
  block; `profiles` stays raw for compatibility, `profile_ids` is the stable
  list.
- `profile launch` gains the standard macOS/Linux Chrome paths; the macOS app
  bundle path is required for this machine.
- Setup hints follow install → launch → set → connect, so a missing OpenCLI
  does not produce a dead-end `profile set` instruction.

## Design

### 1. Child environment

New `deep_reach/runtime/child_env.py`:

```python
def child_env(extra=None) -> dict[str, str]:
    """Environment for external CLIs: no Deep-Reach keys, no credential-looking names."""
```

Rules:

- Drop every name starting with `DEEP_REACH_`.
- Drop names matching a credential pattern (case-insensitive):
  `token`, `secret`, `password`, `passwd`, `cookie`, `api_key`, `apikey`,
  `access_key`, `private_key`, `credential`.
- Keep everything else, including `PATH`, `HOME`, proxies, `LANG`, Node/npm
  variables, and Windows system variables.
- Callers add only the variables the child actually needs.

Used by:

- `OpenCLIClient._run`
- `run_bsk`
- `profile.launch` (Chrome)
- `cmd_setup` (`opencli --version`)
- `_latest_opencli_version` (`npm view`)

There is no passthrough escape hatch. OpenCLI and bsk do not document needing
Deep-Reach keys, and a passthrough would reopen the gap.

### 2. Keys file and directory

New `runtime/secure_paths.py`:

- `ensure_private_dir(path)`: create with `0700` when missing; `chmod 0700`
  when the existing directory is owned by the current user and is not a
  symlink. Return a note when it cannot be tightened.
- `tighten_file(path)`: POSIX only, best effort. Skip symlinks and files owned
  by another user, with a note. Otherwise `chmod 0600`.
- `write_target(path)`: resolve a symlink to its target so atomic writes
  preserve dotfile setups instead of replacing the link.

Call sites:

- `Keys.load` calls `ensure_private_dir(parent)` and `tighten_file(path)`
  **before** parsing, so even a malformed world-readable file is tightened.
- `state.save` and `limits._lock_path` call `ensure_private_dir` when creating
  `~/.deep-reach` or its `locks/` subdirectory.
- `profile.set_context`, `profile.launch`, and `cmd_setup` use the same helper.

`Keys.load`:

- Store `permission_note` on `Keys` for `doctor`/`setup`.
- Catch `yaml.YAMLError` separately and raise
  `CONFIG_ERROR: cannot load keys file <path>: invalid YAML at line L, column C`.
  Never include the parser's line snippet; use `from None`.
- Other load errors keep the path but not file content.

`profile.set_context`:

- Validate contextId with `^[A-Za-z0-9_-]{4,64}$`; reject `auto`.
- Resolve the write target with `write_target(path)` so a symlinked
  `keys.yaml` keeps pointing at its dotfile target.
- Create the parent with mode `0700`.
- Write atomically: temp file in the target directory with mode `0600`,
  `flush` + `fsync`, `os.replace`, then `chmod 0600`.
- Preserve comments and unrelated keys as today.

`Keys.get`:

- When the dotted path looks secret-bearing, register the returned value with
  the redactor. This covers file values and `DEEP_REACH_*` env overrides.

### 3. Error and output redaction

In `runtime/result.py`:

- `register_secret(value)`: ignore empty/placeholder values and values shorter
  than 6 characters.
- `redact_text(text)`: replace each registered value with `[redacted]`.
- `redact_obj(value)`: recursively redact strings inside dict/list/tuple.
- `ReachError.__init__` redacts `message` and `hint`.
- `dump` applies `redact_obj` **before** `json.dumps`. This catches secrets
  containing quotes, backslashes, newlines, or control characters, which a
  post-serialization string replace would miss.
- Text output paths also call `redact_text`: `_text_summary`,
  `format_doctor_text`, `cmd_setup` output, and `cmd_channels` text.
- `sanitize_url(url)`: replace values of credential-looking query parameters
  (`key`, `api_key`, `apikey`, `token`, `access_token`, `secret`, `password`,
  `cookie`, `auth`, `signature`, `sig`) with `[redacted]` in error messages.
  Used by `fetch`/`fetch_json` errors irrespective of the secret registry.

Rationale: even if a backend or upstream error echoes a key, the value never
reaches stdout/stderr, including under `--text` and `--json` escaping.

### 4. Redirect handling and key transport

In `backends/http.py`:

- Extend the redirect handler to strip credential-bearing headers when the
  redirect origin (scheme + host + port) differs from the request origin.
- Header matching is **pattern-based**, not a fixed list: any header whose
  lowercase name matches `authorization`, `proxy-authorization`, `cookie`,
  `token`, `secret`, or `key` is stripped. This covers `Authorization`,
  `X-API-Key`, `api-key`, `X-Auth-Token`, `X-Subscription-Token` (Brave), and
  `X-Goog-Api-Key` (YouTube) without a future allowlist gap.
- Strip credential-looking query parameters from cross-origin redirect
  targets (`key`, `api_key`, `token`, `access_token`, `secret`, `password`,
  `cookie`, `auth`, `signature`, `sig`).
- Keep the existing private-address validation for every redirect.
- `fetch` continues to use the shared opener, and error messages use
  `sanitize_url`.

Key transport changes:

- `backends/public.py` (YouTube): move `official.youtube.api_key` out of the
  `key` query parameter and into the `X-Goog-Api-Key` request header. This was
  verified against the live API: the header is recognized and returns the same
  `API key not valid` response as the query parameter.
- `backends/jina.py`: replace direct `urllib.request.urlopen` with
  `http.fetch`, mapping 401/403 to `NEED_SETUP` and 429 to `QUOTA_EXHAUSTED`.
  This gives Jina the same redirect validation and header stripping.
- `backends/xueqiu.py`: add the validated redirect handler to its cookie-aware
  opener. Cookies are domain-scoped, but this closes the redirect SSRF path.

### 5. Strict OpenCLI profile

Single source of truth:

- The only setting is `browser.opencli_profile` read through `Keys.get`, so
  the existing generic override `DEEP_REACH_BROWSER_OPENCLI_PROFILE` works.
- Remove the separate `DEEP_REACH_OPENCLI_PROFILE` lookup from
  `OpenCLIClient.__init__`; it currently masks the keys-file value and would
  make `doctor` disagree with what actually runs.
- Precedence: explicit `OpenCLIClient(profile=...)` argument (tests/library) >
  `keys.get("browser.opencli_profile")` (file or generic env override) >
  empty.
- A small `runtime/browser_config.py` owns `normalize_opencli_profile(value)`:
  strip whitespace; return `""` for `auto` or invalid values. This helper is
  used by `cli`, `availability`, `doctor`, and `profile` so they cannot drift.

`OpenCLIClient`:

- Remove `_detect_profile` and the `auto` default.
- `profile` is empty unless the caller passes an explicit contextId.
- `_run(..., with_profile=True)` raises `NEED_SETUP` when no profile is
  configured. It never invokes OpenCLI without `OPENCLI_PROFILE`, because
  OpenCLI would otherwise auto-select the only connected profile.
- `profile_status` runs `opencli doctor` for diagnostics, then reports:
  - `setting`: the raw configured value
  - `configured`: whether a valid contextId is set
  - `connected`: whether that contextId appears in `profiles`
  - `context_id`: the configured contextId, not `profiles[0]`
  - `profile_ids`: list of connected contextId strings
  - `profiles`: raw OpenCLI profile dicts (kept for compatibility)
  - `error`: why the configured profile is not usable
- `OPENCLI_WINDOW=background`; clear `OPENCLI_CDP_ENDPOINT` and
  `OPENCLI_CDP_TARGET`.

`runtime/availability.py`:

- `Environment` gains `opencli_profile_configured`.
- `opencli_available` requires installed + configured, and, when probed,
  connected.
- `opencli_profile_configured` is true for a valid contextId from the file or
  the generic env override, matching what the client will use.
- Setup hint precedence, so `channels`/`doctor` never dead-end:
  1. OpenCLI not installed → install `npm install -g @jackwener/opencli`.
  2. Installed but no profile → `deep-reach profile launch`, install the
     extension in that window, then `deep-reach profile set <contextId>`.
  3. Configured but not connected → open the dedicated profile / enable the
     extension; run `deep-reach profile status`.
  4. Configured and connected → normal channel `next_action`.
- `channels` stays fast: it checks the configured string, not the browser.

`runtime/doctor.py` JSON schema (agent-facing contract):

```json
{
  "keys_file": "...",
  "keys_file_exists": true,
  "keys_file_mode": "600",
  "keys_file_secure": true,
  "keys_file_note": "",
  "keys_template": "...",
  "keys_hint": "",
  "profile": {
    "setting": "<ctx>",
    "configured": true,
    "connected": true,
    "context_id": "<ctx>",
    "profile_ids": ["<ctx>"],
    "profiles": [{"contextId": "<ctx>", "extensionVersion": "..."}],
    "window": "background",
    "error": "",
    "next": ""
  }
}
```

- Existing top-level `keys_file`, `keys_file_exists`, `keys_template`, and
  `keys_hint` stay unchanged.
- `keys_file_mode` is `null` on Windows.
- `profiles` stays raw OpenCLI dicts; `profile_ids` is the stable list for
  agents that only need IDs.
- Text output:
  - `browser: dedicated <ctx> (connected)` or `browser: not configured (...)`
  - `browser: background window mode (OpenCLI has no true headless mode)`
  - warning when `opencli_profile` is empty or `auto`
  - warning when the keys file is group/other-readable

`runtime/profile.py`:

- `status` lists all connected profiles and marks the configured one.
- `set_context` validation and atomic write as above.
- `launch` creates/chmods the profile directory to `0700` and uses `child_env`.
- `chrome_path()` adds standard macOS and Linux locations:
  - `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`
  - `~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`
  - `/usr/bin/google-chrome`, `/usr/bin/google-chrome-stable`,
    `/usr/bin/chromium`, `/usr/bin/chromium-browser`, `/snap/bin/chromium`
  - existing `CHROME_PATH`, Windows paths, and `PATH` lookup stay.
  This machine only has the macOS app bundle path, so without this
  `profile launch` cannot start the migration flow.

`cli.py`:

- `_register_backends` reads `browser.opencli_profile`, normalizes it with the
  shared helper, and passes it to `OpenCLIClient`.
- `cmd_profile status` prints every contextId and the configured one.
- `cmd_setup` reports keys permissions and the dedicated-profile next step.

### 6. Generated config and docs

`deep_reach/data/keys.example.yaml`:

```yaml
browser:
  # 必须是专用 Chrome profile 的 contextId；留空则 P1 不运行。
  # 不要填 auto：Deep-Reach 不会自动选择已连接的 profile。
  opencli_profile: ""
  bsk_guard: true
```

Docs to update:

- `README.md`: replace the `auto` section with the strict flow; explain
  `background` vs. true headless; state that P1 requires logging in inside the
  dedicated profile.
- `PRODUCT.md`: add the security guarantee and the no-main-profile promise.
- `REFACTOR_PLAN.md`: mark the dedicated profile as the only supported mode.
- `skill/SKILL.md` and `skill/references/capabilities.md`: mention the
  dedicated profile requirement and that P1 is `needs_setup` until configured.
- `CHANGELOG.md`: breaking change (`auto` and first-profile detection removed),
  migration steps, security fixes.
- Version: fold into the unreleased `0.12.0`; the branch has no published
  release yet.

## Tests

Offline, no live browser required:

1. `test_child_env.py`: fake child dumps env; no `DEEP_REACH_*`, no
   credential-looking names, `PATH`/`HOME` preserved.
2. `test_keys.py`: mode tightened to 600; directory 700; symlink/ownership
   notes; YAML error has line/column but not the secret text; malformed
   world-readable file is tightened before parsing.
3. `test_result.py`: registered secret is redacted from `ReachError`, `dump`,
   `--text` summaries, and `format_doctor_text`; a secret containing quotes,
   backslashes, or newlines is still redacted.
4. `test_http_redirect.py`: fake servers on two origins; `Authorization`,
   `X-Subscription-Token`, `X-Goog-Api-Key`, and `Cookie` are stripped
   cross-origin and kept same-origin; credential query params are removed from
   cross-origin redirect targets; private redirect target rejected.
5. `test_r5_apis.py` / YouTube: request URL contains no `key` parameter and the
   `X-Goog-Api-Key` header is present.
6. `test_opencli_backend.py`: no profile → `NEED_SETUP`; `auto` → unconfigured;
   selected context must be in `profiles`; `OPENCLI_PROFILE` set explicitly;
   `DEEP_REACH_OPENCLI_PROFILE` no longer changes behavior.
7. `test_doctor.py` / `test_availability.py`: P1 `needs_setup` without a
   dedicated profile; ready after binding; text contains the migration command;
   `keys_file_mode`/`profile` JSON schema matches the contract.
8. `test_profile.py`: context validation, atomic write, 600/700 modes, `auto`
   rejected, symlinked keys target preserved, macOS Chrome path discovered.
9. `test_cli_bsk.py`: bsk child env sanitized.
10. Full suite + `ruff check .` + wheel check.

## Risks and migration

- Existing users with `opencli_profile: auto` lose P1 until they run
  `profile launch` and `profile set`. This is intentional and documented as a
  breaking change.
- The dedicated profile has no logins initially. P1 sites that need login will
  be logged out until the user logs in inside that window. P0/P2 are unaffected.
- A background Chrome window still exists; only a true CDP setup removes the
  window, and that setup is out of scope.
- Stripping credential-looking env vars could break a child that unexpectedly
  needs one. Neither OpenCLI nor bsk documents such a dependency; if this
  appears, the child should get an explicit, narrow variable from Deep-Reach,
  not a passthrough.
