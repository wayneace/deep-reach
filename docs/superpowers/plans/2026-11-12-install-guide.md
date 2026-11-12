# Deep-Reach 分发安装指南 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让别人能把一个链接发给自己的 agent（Cherry / Codex / Claude Code / 通用），agent 按文档完成 CLI、skill、OpenCLI 和首次配置。

**Architecture:** 新增 `docs/install.md` 作为唯一分发入口；README 增加“安装（给别人用）”并保留源码开发路径；SKILL.md、`setup` summary、`update` 输出都改成 marketplace-first、CLI-fallback 的双路径；加 docs/CLI 输出测试。

**Tech Stack:** Markdown、Python 3.10+、pytest、ruff。

**Spec:** 本计划由 2026-11-12 的安装审计直接产生（无单独 spec）。

## Global Constraints

- 不把 PyPI 当作安装来源：`deep-reach` 不在 PyPI，必须从 GitHub tag/release 安装。
- Cherry 用户：CLI 用 `cli_install`（`pipx:wayneace/deep-reach`），skill 优先 marketplace；不要同时用 `deep-reach skill install` 再装一份。
- Codex：skill 目录用 `~/.agents/skills`（用户级）或 `.agents/skills`（项目级）；`~/.codex/skills` 已弃用。
- Claude Code：skill 目录用 `~/.claude/skills` 或 `.claude/skills`。
- 通用 agent：`deep-reach skill install --dest <skills-dir>`，安装为 `<skills-dir>/deep-reach/`。
- OpenCLI：Cherry 用 `cli_install`（`npm:@jackwener/opencli`）；通用环境 npm。
- 不删除用户已有的旧 skill；只提示。
- 不自动推送/发布；实现完成后由用户决定。

## Review Focus

- 别人只拿到 `docs/install.md` 链接时，能否判断自己用哪种安装方式。
- Cherry 用户是否会被引导去 marketplace，而不是再装一份 CLI skill。
- Codex 用户是否知道 `~/.agents/skills`，而不是已弃用的 `~/.codex/skills`。
- 安装版 CLI 用户运行 `deep-reach update` 时，是否看到正确的更新方式。
- 旧版/本地 skill 是否会被误删或重复安装。

---

## Task 1: Add docs/install.md

**Files:**
- Create: `docs/install.md`
- Modify: `tests/test_docs_contract.py`

**Interfaces:**
- Produces: a single distributable install document at `docs/install.md`.
- Later README/skill link to it.

- [ ] **Step 1: Write the failing docs contract test**

Add to `tests/test_docs_contract.py`:

```python
INSTALL = ROOT / "docs" / "install.md"


class InstallGuideTest(unittest.TestCase):
    def setUp(self):
        self.text = INSTALL.read_text(encoding="utf-8")

    def test_covers_supported_clients(self):
        for phrase in (
            "Cherry Studio",
            "Codex",
            "Claude Code",
            "~/.agents/skills",
            "~/.claude/skills",
            "deep-reach skill install",
            "marketplace",
            "cli_install",
            "npm:@jackwener/opencli",
        ):
            self.assertIn(phrase, self.text)

    def test_does_not_tell_users_to_install_from_pypi(self):
        lowered = self.text.lower()
        self.assertIn("pypi", lowered)
        self.assertIn("不要", lowered)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_docs_contract.py -q`  
Expected: FAIL because `docs/install.md` does not exist.

- [ ] **Step 3: Write docs/install.md**

Include these sections, in this order:

1. Title + one-line “send this link to your agent”:
   ```text
   https://raw.githubusercontent.com/wayneace/deep-reach/main/docs/install.md
   ```
2. Client matrix:
   | 客户端 | CLI | Skill | OpenCLI |
   - Cherry Studio: `cli_install` `pipx:wayneace/deep-reach` | marketplace GitHub `SKILL.md` URL | `cli_install` `npm:@jackwener/opencli`
   - Codex: GitHub tag CLI | `~/.agents/skills` | npm
   - Claude Code: GitHub tag CLI | `~/.claude/skills` | npm
   - 通用: GitHub tag CLI | `<skills-dir>` | npm
3. Common requirements: Python 3.10+, uv, Node.js/npm for OpenCLI, Chrome for P1, bsk optional.
4. Cherry steps:
   - CLI: `cli_install` tool `pipx:wayneace/deep-reach`, version `v0.14.0` (or latest release).
   - Skill: marketplace URL `https://github.com/wayneace/deep-reach/blob/main/deep_reach/data/skill/SKILL.md`; choose the GitHub result; do not run `deep-reach skill install` afterward.
   - OpenCLI: `cli_install` tool `npm:@jackwener/opencli`, version `2.0.3`.
   - Setup/profile/verify.
5. Codex steps:
   - CLI:
     ```bash
     uv tool install "git+https://github.com/wayneace/deep-reach@v0.14.0"
     ```
   - Skill:
     ```bash
     deep-reach skill install --dest ~/.agents/skills --yes
     ```
   - Project scope: `--dest <repo>/.agents/skills`.
   - Note `~/.codex/skills` works but is deprecated.
   - OpenCLI:
     ```bash
     npm install -g @jackwener/opencli@2.0.3
     ```
6. Claude Code steps: same CLI; `--dest ~/.claude/skills` or `<repo>/.claude/skills`.
7. Generic agent: same CLI; `--dest <client skills dir>`; explain the install target is `<skills-dir>/deep-reach/`.
8. Source checkout (development only):
   ```bash
   git clone https://github.com/wayneace/deep-reach.git
   cd deep-reach
   uv sync
   uv run deep-reach setup
   ```
   Note: `uv run` is only for source checkouts; installed users use `deep-reach`.
9. First-run setup (all clients):
   ```bash
   deep-reach setup
   deep-reach profile launch
   # install/enable the OpenCLI extension
   deep-reach profile status
   deep-reach profile set <contextId>
   deep-reach doctor
   ```
10. Verify:
    ```bash
    deep-reach --version
    deep-reach doctor --json
    deep-reach weibo hot --limit 1 --text
    ```
11. Update:
    - Cherry CLI: `cli_install` latest `pipx:wayneace/deep-reach`.
    - Cherry skill: marketplace check for update.
    - Codex/Claude/generic CLI: reinstall from the latest GitHub tag with `uv tool install --force ...` (or `pipx install --force ...`).
    - Codex/Claude/generic skill: `deep-reach skill install --dest <skills-dir> --yes` (it compares versions).
    - Source: `git pull && uv sync`.
12. Security:
    - keys are 0600; don't paste keys; dedicated Chrome profile; no main browser login sharing.

- [ ] **Step 4: Run the docs test**

Run: `uv run pytest tests/test_docs_contract.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/install.md tests/test_docs_contract.py
git commit -m "docs: add a distributable install guide"
```

---

## Task 2: README install section

**Files:**
- Modify: `README.md`
- Modify: `tests/test_docs_contract.py` (optional phrase check)

- [ ] **Step 1: Add “安装（给别人用）” after the intro**

Content:
```markdown
## 安装（给别人用）

把这份文档发给对方的 agent：[docs/install.md](docs/install.md)

- **Cherry Studio**：CLI 用 `cli_install`（`pipx:wayneace/deep-reach`）；skill 优先从技能市场安装 GitHub 上的 `SKILL.md`。
- **Codex / Claude Code / 通用**：从 GitHub tag 安装 CLI（`uv tool install`），再用 `deep-reach skill install --dest <skills-dir>` 安装 skill。
- **源码开发**：见下面的“快速开始”，只适用于仓库内开发。

> `deep-reach` 目前不在 PyPI；不要从 PyPI 安装同名包。
```

- [ ] **Step 2: Clarify “快速开始”**

Rename the heading to `## 快速开始（源码开发）` and add one line:
```text
以下命令只在源码仓库内使用；给别人安装请看 [docs/install.md](docs/install.md)。
```

- [ ] **Step 3: Update “Agent skill”**

Replace the current CLI-only section with:
- Cherry: marketplace-first (URL).
- Other clients: `deep-reach skill install --dest <skills-dir>`.
- Explain marketplace folder `skill` vs CLI folder `deep-reach`; don't install both.
- Link to `docs/install.md`.

- [ ] **Step 4: Update browser/profile examples**

Change `uv run deep-reach profile ...` to `deep-reach profile ...` and add:
```text
源码仓库内用 `uv run deep-reach`；安装版直接用 `deep-reach`。
```

- [ ] **Step 5: Run docs tests and commit**

Run: `uv run pytest tests/test_docs_contract.py -q`  
Expected: PASS.

```bash
git add README.md tests/test_docs_contract.py
git commit -m "docs: add install paths for other agents"
```

---

## Task 3: SKILL.md and setup summary marketplace-first

**Files:**
- Modify: `deep_reach/data/skill/SKILL.md`
- Modify: `deep_reach/runtime/setup.py`
- Modify: `tests/test_setup.py`
- Modify: `tests/test_docs_contract.py`

- [ ] **Step 1: Write failing tests**

In `tests/test_setup.py`:
```python
def test_summary_prefers_marketplace_and_keeps_cli_fallback(self):
    ...
    self.assertIn("marketplace", text)
    self.assertIn("deep-reach skill install --dest", text)
```

In `tests/test_docs_contract.py`, assert the skill contains:
- `"marketplace"`
- `"~/.agents/skills"`
- `"不要两种方式同时装"`

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_setup.py tests/test_docs_contract.py -q`  
Expected: FAIL.

- [ ] **Step 3: Update SKILL.md install section**

Replace `## 安装 skill` with:
```markdown
## 安装 skill

如果客户端有技能市场（Cherry Studio），优先从市场安装：
https://github.com/wayneace/deep-reach/blob/main/deep_reach/data/skill/SKILL.md

市场安装的目录名是 `skill`，由市场负责更新。

没有市场时再用 CLI 安装：

```bash
deep-reach skill install --dest ~/.agents/skills --yes   # Codex
deep-reach skill install --dest ~/.claude/skills --yes   # Claude Code
deep-reach skill install --dest <skills-dir> --yes       # 其他客户端
```

CLI 安装的目录名是 `deep-reach`。不要两种方式同时装。
```

- [ ] **Step 4: Update setup summary**

In `format_setup_summary`, replace the skill lines with:
```text
Skill:
  marketplace: install from your client's skill marketplace (Cherry Studio recommended)
  fallback:    deep-reach skill install --dest <skills-dir>
  check:       deep-reach skill status --dest <skills-dir>
```

- [ ] **Step 5: Run tests and commit**

Run: `uv run pytest tests/test_setup.py tests/test_docs_contract.py -q`  
Expected: PASS.

```bash
git add deep_reach/data/skill/SKILL.md deep_reach/runtime/setup.py tests/test_setup.py tests/test_docs_contract.py
git commit -m "docs: prefer the skill marketplace in setup"
```

---

## Task 4: Fix deep-reach update output

**Files:**
- Modify: `deep_reach/cli.py`
- Create/Modify: `tests/test_cli_update.py` or add to existing CLI tests.

- [ ] **Step 1: Write a failing CLI output test**

```python
def test_update_explains_cherry_installed_and_source_paths(self):
    out = io.StringIO()
    with redirect_stdout(out):
        code = main(["update"])
    text = out.getvalue()
    self.assertEqual(code, 0)
    for phrase in (
        "Cherry Studio",
        "cli_install",
        "pipx:wayneace/deep-reach",
        "uv tool install",
        "git pull",
        "skill marketplace",
        "deep-reach skill install",
    ):
        self.assertIn(phrase, text)
```

- [ ] **Step 2: Run it to verify failure**

Run: `uv run pytest tests/test_cli_update.py -q`  
Expected: FAIL.

- [ ] **Step 3: Rewrite the update section**

Replace the “Project update” block with:
```text
Deep-Reach update:
  Cherry Studio:
    cli_install  recipe=pipx:wayneace/deep-reach  version=<latest>
  Installed CLI (Codex/Claude/generic):
    uv tool install --force "git+https://github.com/wayneace/deep-reach@<version>"
    # or: pipx install --force "git+https://github.com/wayneace/deep-reach@<version>"
  Source checkout:
    cd <deep-reach project>
    git pull
    uv sync

Skill update:
  Cherry Studio: check for updates in the skill marketplace
  CLI-installed skill: deep-reach skill install --dest <skills-dir>
```

Keep the OpenCLI section above unchanged.

- [ ] **Step 4: Run the test and full suite**

Run: `uv run pytest tests/test_cli_update.py -q`  
Expected: PASS.

Run: `uv run pytest -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deep_reach/cli.py tests/test_cli_update.py
git commit -m "fix: explain how to update installed CLIs and skills"
```

---

## Self-Review

- Spec coverage: install.md (Task 1), README (Task 2), SKILL/setup (Task 3), update (Task 4).
- Install paths: Cherry marketplace-first; Codex/Claude CLI install; source dev; no PyPI.
- Tests: docs contract, setup summary, update output.
- Version/release: not in this plan; after implementation, ask whether to bump/release. The install guide uses the current published tag `v0.14.0`; if a new release is made, update the tag in the guide.
