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
    "deep_reach/data/skill/SKILL.md",
    "deep_reach/data/skill/references/capabilities.md",
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


SKILL = ROOT / "deep_reach" / "data" / "skill" / "SKILL.md"


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


if __name__ == "__main__":
    unittest.main()
