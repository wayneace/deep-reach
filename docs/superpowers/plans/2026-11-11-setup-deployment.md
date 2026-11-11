# Setup Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `deep-reach setup` into the first-run deployment entry that creates the private keys file after confirmation, then hands the agent a client-neutral OpenCLI install prompt.

**Architecture:** A new `deep_reach/runtime/setup.py` owns the plan, atomic template copy, and human-readable summaries. `cmd_setup` in `cli.py` only handles flags, confirmation, and exit codes. OpenCLI install wording is centralized in `runtime/availability.py` so `setup`, `doctor`, `update`, and missing-binary errors all tell an agent to use its client's package manager instead of assuming npm.

**Tech Stack:** Python 3.10+, unittest, pytest runner, PyYAML, POSIX file modes.

**Spec:** `docs/superpowers/specs/2026-11-11-setup-deployment-design.md`

## Global Constraints

- `~/.deep-reach/` is created/tightened to `0700` on POSIX; `keys.yaml` to `0600`.
- Never overwrite an existing `keys.yaml`; never print key values.
- `--dry-run` writes nothing. `--yes` skips the prompt. Non-interactive without `--yes` writes nothing and exits 2.
- `setup` never launches Chrome and never executes an OpenCLI installer.
- OpenCLI guidance must mention the agent client's manager (Cherry Studio: `cli_install`, recipe `npm:@jackwener/opencli`) and keep the plain-environment npm command as fallback.
- `doctor` remains the diagnostic command.
- No version bump, merge, push, or release in this plan.

## Review Focus

- Existing keys file with real secrets: setup must keep it byte-for-byte and never echo a value.
- Symlinked keys file: setup must not follow or overwrite the link target.
- Invalid YAML: setup must report the error and leave the file untouched.
- Non-interactive agent invocation: must not block on `input()`.
- Existing `~/.deep-reach` directory with loose mode: must be tightened without deleting contents.
- Cherry-managed session: no output may instruct the agent to run a global npm install as the only option.

---

### Task 1: Setup plan, atomic scaffold, and CLI flow

**Files:**
- Create: `deep_reach/runtime/setup.py`
- Modify: `deep_reach/cli.py` (`cmd_setup`, parser around line 792)
- Modify: `tests/test_cli_channels.py` (`SetupTextTest`, lines 117-200)
- Create: `tests/test_setup.py`

**Interfaces:**
- Consumes: `Keys`, `default_keys_path`, `template_path`, `ensure_private_dir`, `tighten_file`, `ReachError`, `CONFIG_ERROR`, `BROWSER_BRIDGE_URL`.
- Produces:
  - `@dataclass(frozen=True) class SetupPlan` with fields `keys_path: Path`, `keys_exists: bool`, `keys_is_symlink: bool`, `parent_exists: bool`, `parent_is_canonical: bool`, `opencli_version: str`, `keys: Keys`; properties `create_file -> bool`, `create_dir -> bool`.
  - `@dataclass(frozen=True) class ActionResult` with `status: str`, `path: Path`, `note: str = ""`.
  - `detect_opencli_version() -> str` (empty string when missing).
  - `build_setup_plan(keys: Keys, opencli_version: Optional[str] = None) -> SetupPlan`.
  - `apply_setup(plan: SetupPlan) -> list[ActionResult]`.
  - `format_setup_plan(plan: SetupPlan) -> str`.
  - `format_setup_summary(plan: SetupPlan, results: list[ActionResult], keys: Keys) -> str`.
  - `KEY_NOTES: tuple[tuple[str, str], ...]`.

- [ ] **Step 1: Write the failing module tests**

Create `tests/test_setup.py` with these tests (use `tempfile.TemporaryDirectory`, and patch `deep_reach.runtime.setup.Path.home` to a temp home when asserting `~` paths or canonical modes):

```python
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from deep_reach.runtime.keys import Keys, template_path
from deep_reach.runtime.setup import (
    apply_setup,
    build_setup_plan,
    format_setup_plan,
    format_setup_summary,
)


class SetupPlanTest(unittest.TestCase):
    def test_plan_creates_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "home" / ".deep-reach" / "keys.yaml"
            with mock.patch(
                "deep_reach.runtime.setup.Path.home", return_value=Path(tmp) / "home"
            ):
                plan = build_setup_plan(Keys({}, path=path), opencli_version="")
                text = format_setup_plan(plan)
            self.assertTrue(plan.create_dir)
            self.assertTrue(plan.create_file)
            self.assertIn("~/.deep-reach/keys.yaml", text)
            self.assertIn("cli_install", text)
            self.assertIn("npm install -g @jackwener/opencli", text)

    def test_plan_keeps_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keys.yaml"
            path.write_text("version: 1\n", encoding="utf-8")
            plan = build_setup_plan(Keys.load(path), opencli_version="2.0.3")
            self.assertFalse(plan.create_file)
            self.assertIn("keep", format_setup_plan(plan).lower())


class SetupApplyTest(unittest.TestCase):
    def test_apply_creates_private_file(self):
        if os.name == "nt":
            self.skipTest("POSIX permissions only")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            path = home / ".deep-reach" / "keys.yaml"
            with mock.patch("deep_reach.runtime.setup.Path.home", return_value=home):
                plan = build_setup_plan(Keys({}, path=path), opencli_version="")
                results = apply_setup(plan)
            self.assertEqual(path.read_bytes(), template_path().read_bytes())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual([r.status for r in results], ["created", "created"])

    def test_apply_does_not_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keys.yaml"
            path.write_text("version: 1\nofficial:\n  github:\n    token: keep-me\n")
            plan = build_setup_plan(Keys.load(path), opencli_version="")
            apply_setup(plan)
            self.assertIn("keep-me", path.read_text(encoding="utf-8"))

    def test_apply_skips_symlink(self):
        if os.name == "nt":
            self.skipTest("symlink setup is POSIX-only in tests")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target.yaml"
            target.write_text("version: 1\n", encoding="utf-8")
            link = Path(tmp) / "keys.yaml"
            link.symlink_to(target)
            plan = build_setup_plan(Keys.load(link), opencli_version="")
            results = apply_setup(plan)
            self.assertEqual(target.read_text(encoding="utf-8"), "version: 1\n")
            self.assertEqual(results[-1].status, "skipped")


class SetupSummaryTest(unittest.TestCase):
    def test_summary_lists_empty_keys_and_extension_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keys.yaml"
            plan = build_setup_plan(
                Keys({"official": {"github": {"token": "secret-value"}}}, path=path),
                opencli_version="",
            )
            text = format_setup_summary(plan, [], plan.keys)
        self.assertIn("official.youtube.api_key", text)
        self.assertNotIn("official.github.token", text)
        self.assertNotIn("secret-value", text)
        self.assertIn("chromewebstore.google.com", text)
```

- [ ] **Step 2: Run the module tests to verify they fail**

Run: `uv run pytest tests/test_setup.py -v`
Expected: FAIL because `deep_reach.runtime.setup` does not exist.

- [ ] **Step 3: Implement `deep_reach/runtime/setup.py`**

Implement the dataclasses, plan, apply, and formatting. Use these exact behaviors:

- `build_setup_plan` uses `keys.path or default_keys_path()`, `path.parent == Path.home() / ".deep-reach"` for `parent_is_canonical`, and `detect_opencli_version()` unless `opencli_version` is passed.
- `detect_opencli_version` checks `DEEP_REACH_OPENCLI_BIN` then `shutil.which("opencli")`, runs `--version` with `child_env()` and a 5-second timeout, returns `""` when missing and `"unknown"` on failure.
- `apply_setup` returns `[ActionResult("created"|"kept", parent, note), ActionResult(...)]`. For the canonical parent call `ensure_private_dir`; for a custom missing parent use `mkdir(parents=True, exist_ok=True)`. If `keys_is_symlink`, return `skipped` and do not write.
- `_write_template(path)` reads `template_path().read_bytes()`, writes to `tempfile.mkstemp(dir=path.parent, prefix="keys-")`, flushes and `os.fsync`, chmods `0600` on POSIX, then `os.replace`. Remove the temp file on failure.
- `format_setup_plan` must include the `Will create:` / `Keep:` sections and the client-neutral OpenCLI block:
  `cli_install` with `npm:@jackwener/opencli`, plus `npm install -g @jackwener/opencli@<recommended version>`.
- `format_setup_summary` lists `Files:` with final modes, `Empty keys (all optional):` using `KEY_NOTES` and `keys.has(path)`, and `Next:` with `deep-reach profile launch`, the `BROWSER_BRIDGE_URL`, `profile status`, `profile set <contextId>`, and `doctor`.
- `KEY_NOTES` covers: `official.github.token`, `official.youtube.api_key`, `official.ebay.client_id`, `official.ebay.client_secret`, `official.etsy.api_key`, `official.producthunt.token`, `official.uspto.odp_api_key`, `official.epo.consumer_key`, `official.epo.consumer_secret`, `xueqiu.cookie`, `search.tavily.api_key`, `search.firecrawl.api_key`, `search.brightdata.api_token`, `search.brave.api_key`, `search.jina.api_key`.
- Do not print values; only key names and descriptions.

- [ ] **Step 4: Run the module tests to verify they pass**

Run: `uv run pytest tests/test_setup.py -v`
Expected: PASS.

- [ ] **Step 5: Write the failing CLI tests**

Replace `SetupTextTest` in `tests/test_cli_channels.py` with:
- `test_setup_dry_run_makes_no_changes`: `cmd_setup(argparse.Namespace(dry_run=True, yes=False))` prints the plan, returns 0, and the keys path does not exist.
- `test_setup_yes_creates_keys`: `--yes` creates the file, returns 0, output contains `Empty keys`, `chromewebstore.google.com`, and `cli_install`.
- `test_setup_declined_makes_no_changes`: patch `deep_reach.cli.sys.stdin.isatty` to return True and `builtins.input` to return `"n"`; returns 2 and the file does not exist.
- `test_setup_non_interactive_without_yes_makes_no_changes`: patch `isatty` False; returns 2 and the file does not exist.
- `test_setup_invalid_yaml_does_not_overwrite`: write invalid YAML, patch `_load_keys` to raise `ReachError(CONFIG_ERROR, "invalid YAML")`; returns 2 and content is unchanged.
Each test patches `deep_reach.cli._load_keys` to return `Keys({}, path=key_path)` except the invalid-YAML case.

- [ ] **Step 6: Run the CLI tests to verify they fail**

Run: `uv run pytest tests/test_cli_channels.py::SetupTextTest -v`
Expected: FAIL because the old `cmd_setup` has no flags and does not create files.

- [ ] **Step 7: Rewrite `cmd_setup` and parser flags**

- Remove the old check table and template-copy message.
- Build the plan from `keys`, print `format_setup_plan(plan)`.
- `--dry-run`: return 0.
- If no `create_dir` and no `create_file`: print a blank line and `format_setup_summary(plan, [], keys)`, return 0.
- If not `yes`: when `not sys.stdin.isatty()`, print `No changes made. Re-run with --yes after confirming.` and return 2; otherwise ask `Proceed with file setup? [y/N] ` and return 2 on anything except `y`/`yes`.
- Apply inside `try/except ReachError`, print `CONFIG_ERROR: ...` to stderr and return 2 on failure.
- Print a blank line and the summary; return 0.
- Add `--dry-run` and `--yes` flags to the `setup` subparser.

- [ ] **Step 8: Run the CLI tests to verify they pass**

Run: `uv run pytest tests/test_cli_channels.py::SetupTextTest -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add deep_reach/runtime/setup.py deep_reach/cli.py tests/test_setup.py tests/test_cli_channels.py
git commit -m "feat: make setup deploy the private keys file"
```

---

### Task 2: Client-neutral OpenCLI install guidance

**Files:**
- Modify: `deep_reach/runtime/availability.py:28` and `_opencli_hint` around line 219
- Modify: `deep_reach/runtime/doctor.py:57`
- Modify: `deep_reach/backends/opencli.py:157`
- Modify: `deep_reach/cli.py:688-711` (`cmd_update`)
- Modify: `tests/test_availability.py:236`
- Modify: `tests/test_doctor.py:204`
- Modify: `tests/test_opencli_backend.py:159`

**Interfaces:**
- Produces: `OPENCLI_CLIENT_HINT` (English) and `OPENCLI_CLIENT_HINT_ZH` (Chinese) in `runtime/availability.py`. Both mention Cherry Studio `cli_install` with `npm:@jackwener/opencli` and the plain-environment npm command.

- [ ] **Step 1: Add failing assertions for the client-neutral wording**

In `test_availability.py`, after the existing npm assertion in
`test_next_action_for_needs_setup_mentions_opencli`, add
`self.assertIn("cli_install", hint)`.
In `test_doctor.py` missing-OpenCLI tests, add
`self.assertIn("cli_install", text)` / `self.assertIn("cli_install", rows["weibo"]["next_action"])`.
In `test_opencli_backend.py`, after the missing-binary npm assertion, add
`self.assertIn("cli_install", ctx.exception.message)`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_availability.py tests/test_doctor.py tests/test_opencli_backend.py -v`
Expected: FAIL on the new `cli_install` assertions.

- [ ] **Step 3: Add and use the shared hints**

In `availability.py` add:

```python
OPENCLI_CLIENT_HINT = (
    "install OpenCLI with your agent client's package manager "
    f"(Cherry Studio: cli_install, recipe {OPENCLI_PACKAGE}; "
    f"plain environment: {OPENCLI_INSTALL_COMMAND})"
)
OPENCLI_CLIENT_HINT_ZH = (
    "用当前 agent 客户端的管理器安装 OpenCLI（Cherry Studio 用 cli_install，"
    f"recipe {OPENCLI_PACKAGE}；普通环境用 {OPENCLI_INSTALL_COMMAND}）"
)
```

Use `OPENCLI_CLIENT_HINT_ZH` in `_opencli_hint`; use `OPENCLI_CLIENT_HINT` in
`doctor.py`'s missing-OpenCLI action and `OpenCLIClient`'s `FileNotFoundError`.
Add one line to `cmd_update`:
`print(f"  If your client manages CLIs, use its manager: {OPENCLI_CLIENT_HINT}")`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_availability.py tests/test_doctor.py tests/test_opencli_backend.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deep_reach/runtime/availability.py deep_reach/runtime/doctor.py deep_reach/backends/opencli.py deep_reach/cli.py tests/test_availability.py tests/test_doctor.py tests/test_opencli_backend.py
git commit -m "feat: guide OpenCLI install through the agent client"
```

---

### Task 3: Docs, changelog, and full verification

**Files:**
- Modify: `README.md` (Quick start and Key file sections)
- Modify: `skill/SKILL.md` (quick start)
- Modify: `CHANGELOG.md` (new Unreleased section)
- Maybe modify: `README.md` test count after the full run

**Interfaces:**
- No code interfaces; documentation must match the implemented `setup` flags and wording.

- [ ] **Step 1: Update README**

- Add `uv run deep-reach setup` to Quick start.
- Replace “运行 `deep-reach setup` 会打印当前安装里的模板绝对路径” with the new flow: plan → confirmation → `keys.yaml` creation; `--dry-run` / `--yes`; existing files are kept.
- State that `setup` does not install OpenCLI itself; it prints a client-neutral prompt. Cherry Studio uses `cli_install` with `npm:@jackwener/opencli`; plain environments use `npm install -g @jackwener/opencli@2.0.3`.
- Keep the extension URL and profile steps; state that setup does not launch Chrome.
- Update the test count to the number printed by the full suite.

- [ ] **Step 2: Update SKILL.md**

Add `deep-reach setup` as the first-run step and one sentence: if OpenCLI is missing, install it with the current agent client's manager before `profile launch`.

- [ ] **Step 3: Update CHANGELOG**

Add at the top:

```markdown
## Unreleased

- `deep-reach setup` 现在是首次部署入口：先展示将创建/保留的文件，确认后从包内模板创建 `~/.deep-reach/keys.yaml`（0600），已有文件绝不覆盖。
- 新增 `setup --dry-run` 和 `setup --yes`；非交互环境未加 `--yes` 时不做任何修改。
- `setup` 不直接安装 OpenCLI，而是提示 agent 使用当前客户端的管理器（Cherry Studio 用 `cli_install`，recipe `npm:@jackwener/opencli`；普通环境用 npm）；`doctor` / `update` / OpenCLI 缺失错误使用同一套提示。
- `setup` 汇总创建/保留的文件、仍为空的 key 及用途、扩展商店链接和 `profile launch/status/set` 步骤；不自动打开 Chrome。
```

- [ ] **Step 4: Run the full verification**

Run:

```bash
uv run pytest
uv run ruff check .
```

Expected: all tests pass and ruff reports no issues. Record the exact test count.

- [ ] **Step 5: Commit**

```bash
git add README.md skill/SKILL.md CHANGELOG.md
git commit -m "docs: document the setup deployment flow"
```

---

## Self-Review

- Spec coverage: setup plan/confirmation/scaffold (Task 1), client-neutral OpenCLI prompt (Tasks 1-2), summary/empty keys/extension URL (Task 1), docs (Task 3).
- No auto-install, no Chrome launch, no key writes beyond the template copy.
- Types and names used by later tasks match Task 1's Interfaces block.
- Review Focus items each have a test in Task 1 (existing file, symlink, invalid YAML, non-interactive, directory mode, client-neutral hint).
