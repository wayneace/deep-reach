import unittest
from unittest import mock

from deep_reach.backends.jina import JinaReader
from deep_reach.backends.p2_common import clamp_limit, p2_fetch_json, require_key
from deep_reach.runtime.keys import Keys
from deep_reach.runtime.result import NEED_SETUP, QUOTA_EXHAUSTED, ReachError


class P2CommonTest(unittest.TestCase):
    def test_clamp_limit(self):
        self.assertEqual(clamp_limit(None), 10)
        self.assertEqual(clamp_limit("x"), 10)
        self.assertEqual(clamp_limit(0), 1)
        self.assertEqual(clamp_limit(-3), 1)
        self.assertEqual(clamp_limit("50"), 20)
        self.assertEqual(clamp_limit("5"), 5)

    def test_require_key(self):
        with self.assertRaises(ReachError) as ctx:
            require_key(Keys({}), "search.tavily.api_key", "tavily")
        self.assertEqual(ctx.exception.code, NEED_SETUP)


class P2FetchJsonTest(unittest.TestCase):
    def test_json_posts_get_content_type(self):
        captured = {}

        def fake(url, **kwargs):
            captured.update(kwargs)
            return {}

        with mock.patch(
            "deep_reach.backends.p2_common.fetch_json", side_effect=fake
        ):
            p2_fetch_json(
                "https://api.example.com",
                timeout=5,
                data=b'{"query": "x"}',
                method="POST",
            )
        self.assertEqual(captured["headers"]["Content-Type"], "application/json")

    def test_existing_content_type_is_preserved(self):
        captured = {}

        def fake(url, **kwargs):
            captured.update(kwargs)
            return {}

        with mock.patch(
            "deep_reach.backends.p2_common.fetch_json", side_effect=fake
        ):
            p2_fetch_json(
                "https://api.example.com",
                timeout=5,
                headers={"Content-Type": "application/custom"},
                data=b"{}",
                method="POST",
            )
        self.assertEqual(captured["headers"]["Content-Type"], "application/custom")


class JinaRateLimitTest(unittest.TestCase):
    def test_429_is_quota_exhausted(self):
        with mock.patch(
            "deep_reach.backends.jina.fetch",
            side_effect=ReachError(QUOTA_EXHAUSTED, "HTTP 429"),
        ):
            with self.assertRaises(ReachError) as ctx:
                JinaReader().read("https://example.com")
        self.assertEqual(ctx.exception.code, QUOTA_EXHAUSTED)
        self.assertIn("free-tier", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
