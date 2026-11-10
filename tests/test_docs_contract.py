import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = (
    "README.md",
    "PRODUCT.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "pyproject.toml",
    "skill/SKILL.md",
    "skill/references/capabilities.md",
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


if __name__ == "__main__":
    unittest.main()
