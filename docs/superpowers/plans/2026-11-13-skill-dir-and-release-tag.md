# Skill 目录与发布 Tag 修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让市场安装的 skill 使用 `deep-reach` 目录名，并让 mise/Cherry CLI 列表显示单 `v` 版本。

**Architecture:** 只改本仓库的打包路径和发布约定。skill 数据目录从
`deep_reach/data/skill/` 移到 `deep_reach/data/deep-reach/`；`0.14.2` 使用裸
semver release tag，使 mise 返回 `0.14.2`。不改 Cherry、bsk 或安装器的实现。

**Tech Stack:** Python 3.10+、setuptools、pytest、ruff、uv、GitHub Releases、mise pipx backend。

**Spec:** `docs/superpowers/specs/2026-11-13-skill-dir-and-release-tag-design.md`

## Global Constraints

- 目标版本：`0.14.2`。
- 市场安装目录必须是 `<skills-dir>/deep-reach/`，不能是 `<skills-dir>/skill/`。
- 发布 tag 必须是 `0.14.2`（裸 semver），不能是 `v0.14.2`。
- 旧 `v*` tag/release 不改、不删。
- 不修改或删除现有的 bsk 目录 `<skills-dir>/skill/`。
- 不发布到 PyPI。
- 不修改 Cherry 应用、bsk 仓库或 mise 源码。
- 合并、推送、打 tag、创建 GitHub release 需要用户确认后执行。

## Review Focus

- 市场 URL 的父目录不是 `deep-reach`：安装仍会落到 `skill/`，与 bsk 冲突；由
  `test_skill_install_url_names_unique_folder` 和 wheel 路径检查覆盖。
- 安装时目标父目录已有 bsk 的 `skill/`：实现必须只写 `<dest>/deep-reach/`，不能
  清理兄弟目录；由 `test_apply_preserves_existing_skill_sibling` 覆盖。
- 新版本号只改 Python 包、没改 `uv.lock` 或 SKILL frontmatter：版本检查会漂移；
  由 `test_skill_version_matches_package`、wheel 检查和 `rg` 覆盖。
- 安装文档继续写 `v0.14.2` 或 `requestedVersion="v0.14.2"`：mise 会再次返回带 v
  的版本，显示问题复现；由 `test_install_docs_use_bare_release_tag` 覆盖。
- wheel/sdist 仍包含旧 `data/skill/`：旧市场 URL 会继续可安装并占用 `skill/`；
  由 `scripts/check_wheel.py` 和构建后的 `unzip -l` 检查覆盖。

---

### Task 1: 把包内 skill 目录改名为 `deep-reach`

**Files:**
- Move: `deep_reach/data/skill/` → `deep_reach/data/deep-reach/`
- Modify: `deep_reach/runtime/skill.py`
- Modify: `pyproject.toml`
- Modify: `scripts/check_wheel.py`
- Modify: `tests/test_skill.py`
- Modify: `tests/test_docs_contract.py`（仅路径常量）

**Interfaces:**
- Produces: `skill_dir() -> Path`，返回路径末级为 `deep-reach`。
- Produces: `SKILL_REL = "deep-reach"`。

- [ ] **Step 1: 写失败测试**

在 `tests/test_skill.py` 新增：

```python
class PackagedSkillTest(unittest.TestCase):
    def test_packaged_skill_dir_uses_unique_name(self):
        self.assertEqual(skill_dir().name, "deep-reach")
```

把 `SkillCliTest.test_path_json` 的断言改为：

```python
self.assertEqual(Path(data["path"]).name, "deep-reach")
```

在 `SkillInstallTest` 中加入：

```python
def test_apply_preserves_existing_skill_sibling(self):
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp)
        sibling = dest / "skill"
        sibling.mkdir()
        marker = sibling / "SKILL.md"
        marker.write_text("bsk", encoding="utf-8")
        apply_install(build_install_plan(dest))
        self.assertEqual(marker.read_text(encoding="utf-8"), "bsk")
        self.assertTrue((dest / "deep-reach" / "SKILL.md").is_file())
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_skill.py::PackagedSkillTest::test_packaged_skill_dir_uses_unique_name tests/test_skill.py::SkillCliTest::test_path_json -v`

Expected: FAIL，实际名称为 `skill`。

- [ ] **Step 3: 移动目录并更新路径常量**

```bash
git mv deep_reach/data/skill deep_reach/data/deep-reach
```

`deep_reach/runtime/skill.py`：

```python
SKILL_REL = "deep-reach"
```

`pyproject.toml` 的 package-data：

```toml
"deep_reach.data" = ["*.yaml", "deep-reach/*.md", "deep-reach/references/*.md"]
```

`scripts/check_wheel.py`：

```python
SKILL_SUFFIX = "deep_reach/data/deep-reach/SKILL.md"
SKILL_CAPS_SUFFIX = "deep_reach/data/deep-reach/references/capabilities.md"
```

`tests/test_docs_contract.py` 的两处路径同步改为：

```python
"deep_reach/data/deep-reach/SKILL.md",
"deep_reach/data/deep-reach/references/capabilities.md",
```

以及：

```python
SKILL = ROOT / "deep_reach" / "data" / "deep-reach" / "SKILL.md"
```

- [ ] **Step 4: 运行 skill 测试确认通过**

Run: `uv run pytest tests/test_skill.py -q`

Expected: PASS；包括新的 sibling 测试。

- [ ] **Step 5: 提交**

```bash
git add deep_reach/data deep_reach/runtime/skill.py pyproject.toml scripts/check_wheel.py tests/test_skill.py tests/test_docs_contract.py
git commit -m "fix: give packaged skill a unique directory name"
```

### Task 2: 使用裸 semver tag 并更新 0.14.2 文档

**Files:**
- Modify: `deep_reach/data/deep-reach/SKILL.md`
- Modify: `README.md`
- Modify: `docs/install.md`
- Modify: `PRODUCT.md`
- Modify: `CHANGELOG.md`
- Modify: `pyproject.toml`
- Modify: `deep_reach/__init__.py`
- Modify: `uv.lock`
- Modify: `tests/test_docs_contract.py`

**Interfaces:**
- Consumes: Task 1 的 `deep-reach` 路径。
- Produces: 文档中的安装版本 `0.14.2`，无 `v` 前缀。

- [ ] **Step 1: 写失败测试**

在 `SkillContractTest` 中加入：

```python
def test_skill_install_url_names_unique_folder(self):
    self.assertIn("deep_reach/data/deep-reach/SKILL.md", self.text)
    self.assertNotIn("deep_reach/data/skill/SKILL.md", self.text)
```

在 `InstallGuideTest` 中加入：

```python
def test_install_docs_use_bare_release_tag(self):
    self.assertIn(f'requestedVersion="{__version__}"', self.text)
    self.assertIn(f"@{__version__}", self.text)
    self.assertNotIn(f'requestedVersion="v{__version__}"', self.text)
    self.assertNotIn(f"@v{__version__}", self.text)

def test_install_docs_use_unique_skill_folder(self):
    self.assertIn("deep_reach/data/deep-reach/SKILL.md", self.text)
    self.assertNotIn("deep_reach/data/skill/SKILL.md", self.text)
```

在模块级 changelog 测试中加入：

```python
def test_changelog_has_0142(self):
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    self.assertIn(f"## {__version__}", text)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_docs_contract.py -q`

Expected: FAIL；旧路径、`v0.14.1` 安装示例、缺少 0.14.2 changelog。

- [ ] **Step 3: 更新文档和版本**

逐项替换：

- `README.md`：版本号 `0.14.2`；市场 URL 改为
  `https://github.com/wayneace/deep-reach/blob/main/deep_reach/data/deep-reach/SKILL.md`。
- `docs/install.md`：源码路径改为 `deep_reach/data/deep-reach/`；两处市场 URL
  改为新路径；所有 `v0.14.1` / `@v0.14.1` 改为 `0.14.2` / `@0.14.2`；
  `requestedVersion="v0.14.1"` 改为 `requestedVersion="0.14.2"`。
- `deep_reach/data/deep-reach/SKILL.md`：`metadata.version` 改为 `"0.14.2"`；
  安装 URL 改为新路径。
- `PRODUCT.md`：`版本：0.14.2`。
- `pyproject.toml`：`version = "0.14.2"`。
- `deep_reach/__init__.py`：`__version__ = "0.14.2"`。
- `uv.lock`：运行 `uv lock` 同步 deep-reach 包的 `version`，确认 diff 只包含
  版本变化。
- `CHANGELOG.md` 顶部加入：

```markdown
## 0.14.2 — 2026-11-13

Skill 安装目录与发布 tag 修复。

- Skill 包内路径改为 `deep_reach/data/deep-reach/`；市场安装目录从通用的
  `skill/` 变为 `deep-reach/`，不再与 bsk 的 bundled skill 冲突。
- 从本版本起 release tag 使用裸 semver（`0.14.2`），避免 mise 返回
  `v0.14.2` 后客户端再补一个 `v` 显示成 `vv0.14.2`。
- 旧市场安装需要从新 URL 重装；CLI 安装路径不变。
```

- [ ] **Step 4: 运行文档契约测试确认通过**

Run: `uv run pytest tests/test_docs_contract.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add README.md docs/install.md deep_reach/data/deep-reach/SKILL.md PRODUCT.md CHANGELOG.md pyproject.toml deep_reach/__init__.py uv.lock tests/test_docs_contract.py docs/superpowers/specs/2026-11-13-skill-dir-and-release-tag-design.md docs/superpowers/plans/2026-11-13-skill-dir-and-release-tag.md
git commit -m "chore: release 0.14.2 with unique skill folder"
```

### Task 3: 全量验证、构建和本地安装检查

**Files:**
- No source edits; may update `README.md` test count.
- Build outputs: `dist/deep_reach-0.14.2-py3-none-any.whl`, `dist/deep_reach-0.14.2.tar.gz`

**Interfaces:**
- Consumes: Task 1/2 的包路径和版本。
- Produces: 可发布的 wheel/sdist，以及验证输出。

- [ ] **Step 1: 跑全量测试和 lint**

Run:

```bash
uv run pytest -q
uv run ruff check .
```

Expected: 所有测试 PASS；ruff 无输出。

- [ ] **Step 2: 构建并检查 wheel**

Run:

```bash
uv build
uv run python scripts/check_wheel.py dist/deep_reach-0.14.2-py3-none-any.whl
unzip -l dist/deep_reach-0.14.2-py3-none-any.whl | grep 'deep_reach/data/'
```

Expected: wheel/sdist 生成；检查脚本通过；列表包含
`deep_reach/data/deep-reach/SKILL.md` 和
`deep_reach/data/deep-reach/references/capabilities.md`，不包含
`deep_reach/data/skill/`。

- [ ] **Step 3: 验证 CLI skill 路径和临时安装**

Run:

```bash
uv run deep-reach skill path --json
tmp="$(mktemp -d)"
uv run deep-reach skill install --dest "$tmp" --yes
uv run deep-reach skill status --dest "$tmp" --json
test -f "$tmp/deep-reach/SKILL.md"
test ! -e "$tmp/skill"
```

Expected: `path` 末级为 `deep-reach`；`status.state` 为 `current`；临时目录中只有
`deep-reach/`。

- [ ] **Step 4: 扫描旧路径和旧 tag 示例**

Run:

```bash
rg -n 'deep_reach/data/skill|@v0\.14\.2|requestedVersion="v0\.14\.2"' \
  README.md docs/install.md deep_reach/data/deep-reach tests scripts pyproject.toml
```

Expected: 无输出（历史 `docs/superpowers/` 文档不在扫描范围）。

- [ ] **Step 5: 更新 README 测试数并提交**

把 `README.md` 中的“378 个单元测试”改为实际通过数；然后：

```bash
git add README.md
git commit -m "docs: update test count for 0.14.2"
```

`dist/` 已被 `.gitignore` 忽略，release 时直接上传本地文件，不提交到仓库。

### Task 4: 合并、发布和更新本机（需要用户确认）

**Files:**
- No source edits.

**Interfaces:**
- Consumes: 已验证的 `0.14.2` 提交和 `dist/` 产物。
- Produces: GitHub release `0.14.2`、本机 Cherry CLI `0.14.2`、市场 skill 新目录。

- [ ] **Step 1: 获得用户对合并、推送、打 tag、创建 release 的明确同意。**
- [ ] **Step 2: 合并分支到 `main`，推送 `main`。**
- [ ] **Step 3: 创建并推送裸 tag：**

```bash
git tag 0.14.2
git push origin main 0.14.2
```

- [ ] **Step 4: 创建 GitHub release：**

```bash
gh release create 0.14.2 \
  dist/deep_reach-0.14.2-py3-none-any.whl \
  dist/deep_reach-0.14.2.tar.gz \
  --title "0.14.2" \
  --notes "Skill 目录改为 deep-reach；release tag 改为裸 semver。"
```

- [ ] **Step 5: 更新本机 Cherry CLI：**

```text
cli_install(name="deep-reach", tool="pipx:wayneace/deep-reach", requestedVersion="0.14.2")
```

验证 `cli_list` 的 `deep-reach.version` 为 `0.14.2`，`deep-reach --version` 为
`deep-reach 0.14.2`。

- [ ] **Step 6: 从新 URL 重装市场 skill：**

```text
https://github.com/wayneace/deep-reach/blob/main/deep_reach/data/deep-reach/SKILL.md
```

验证安装目录为 `.../Data/Skills/deep-reach/`，`SKILL.md` 的
`metadata.version` 为 `0.14.2`，且 `.../Data/Skills/skill/` 仍是 bsk。
