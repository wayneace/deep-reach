import io
import unittest
import urllib.error
from unittest import mock

from deep_reach.backends.jina import JinaReader
from deep_reach.backends.p2_common import clamp_limit, require_key
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


class JinaRateLimitTest(unittest.TestCase):
    def test_429_is_quota_exhausted(self):
        error = urllib.error.HTTPError(
            "https://r.jina.ai/x", 429, "limited", {}, io.BytesIO(b"")
        )
        with mock.patch(
            "deep_reach.backends.jina.urllib.request.urlopen", side_effect=error
        ):
            with self.assertRaises(ReachError) as ctx:
                JinaReader().read("https://example.com")
        self.assertEqual(ctx.exception.code, QUOTA_EXHAUSTED)


if __name__ == "__main__":
    unittest.main()
