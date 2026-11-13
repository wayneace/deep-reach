import unittest
from pathlib import Path

from deep_reach import __version__

ROOT = Path(__file__).resolve().parents[1]
DOCS = (
    "README.md",
    "PRODUCT.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "pyproject.toml",
    "docs/install.md",
    "deep_reach/data/deep-reach/SKILL.md",
    "deep_reach/data/deep-reach/references/capabilities.md",
    "deep_reach/product.py",
)
BANNED = (
    "只读",
    "read-only",
    "不发帖",
    "不评论",
    "100% 被",
    "不做写操作",
    "OpenCLI 浏览器桥",
    "OpenCLI 登录",
)


class DocsContractTest(unittest.TestCase):
    def test_docs_do_not_claim_a_read_only_product(self):
        for name in DOCS:
            text = (ROOT / name).read_text(encoding="utf-8").lower()
            for phrase in BANNED:
                self.assertNotIn(
                    phrase.lower(), text, f"{name} still contains {phrase!r}"
                )

    def test_changelog_has_v0110(self):
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("v0.11.0", text)

    def test_changelog_has_v0111(self):
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("v0.11.1", text)

    def test_changelog_has_v0120(self):
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("v0.12.0", text)

    def test_changelog_has_v0130(self):
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("v0.13.0", text)

    def test_changelog_has_v0140(self):
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("v0.14.0", text)

    def test_changelog_has_v0141(self):
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("v0.14.1", text)

    def test_changelog_has_0142(self):
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn(f"## {__version__}", text)


SKILL = ROOT / "deep_reach" / "data" / "deep-reach" / "SKILL.md"


class SkillContractTest(unittest.TestCase):
    def setUp(self):
        self.text = SKILL.read_text(encoding="utf-8")

    def test_skill_version_matches_package(self):
        self.assertIn(f'version: "{__version__}"', self.text)

    def test_skill_routes_instead_of_always_calling(self):
        for phrase in (
            "选择路由",
            "普通公开网页优先用内置工具",
            "粘贴",
            "竞品调研",
            "GitHub",
            "V2EX",
            "NEED_UI",
            "deep-reach bsk",
            "channels --json",
            "doctor --json",
        ):
            self.assertIn(phrase, self.text)

    def test_skill_error_table_is_complete(self):
        for code in (
            "UPSTREAM_BROKEN",
            "QUOTA_EXHAUSTED",
            "CONFIG_ERROR",
        ):
            self.assertIn(code, self.text)

    def test_skill_uses_installed_cli(self):
        self.assertNotIn("uv run deep-reach", self.text)

    def test_skill_does_not_mention_removed_roadmap(self):
        self.assertNotIn("roadmap", self.text.lower())

    def test_skill_documents_install_command(self):
        self.assertIn("deep-reach skill install", self.text)

    def test_skill_prefers_marketplace_and_names_client_paths(self):
        for phrase in (
            "marketplace",
            "~/.agents/skills",
            "~/.claude/skills",
            "不要两种方式同时装",
        ):
            self.assertIn(phrase, self.text)

    def test_skill_install_url_names_unique_folder(self):
        self.assertIn("deep_reach/data/deep-reach/SKILL.md", self.text)
        self.assertNotIn("deep_reach/data/skill/SKILL.md", self.text)


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

    def test_install_docs_use_bare_release_tag(self):
        self.assertIn(f'requestedVersion="{__version__}"', self.text)
        self.assertIn(f"@{__version__}", self.text)
        self.assertNotIn(f'requestedVersion="v{__version__}"', self.text)
        self.assertNotIn(f"@v{__version__}", self.text)

    def test_install_docs_use_unique_skill_folder(self):
        self.assertIn("deep_reach/data/deep-reach/SKILL.md", self.text)
        self.assertNotIn("deep_reach/data/skill/SKILL.md", self.text)

    def test_warns_cli_install_would_overwrite_marketplace_copy(self):
        self.assertIn("覆盖市场", self.text)
        self.assertIn("更新跟踪", self.text)


if __name__ == "__main__":
    unittest.main()
