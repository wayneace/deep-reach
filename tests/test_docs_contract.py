import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ("README.md", "PRODUCT.md", "skill/SKILL.md", "deep_reach/product.py")
BANNED = ("只读", "read-only", "不发帖", "不评论", "100% 被")


class DocsContractTest(unittest.TestCase):
    def test_docs_do_not_claim_a_read_only_product(self):
        for name in DOCS:
            text = (ROOT / name).read_text(encoding="utf-8")
            for phrase in BANNED:
                self.assertNotIn(phrase, text, f"{name} still contains {phrase!r}")


if __name__ == "__main__":
    unittest.main()
