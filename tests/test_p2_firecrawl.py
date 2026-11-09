import json
import unittest
from unittest import mock

from deep_reach.backends.firecrawl import register_firecrawl_backends
from deep_reach.channels.base import BackendSpec, Channel
from deep_reach.runtime.dispatch import BACKENDS
from deep_reach.runtime.keys import Keys
from deep_reach.runtime.result import UPSTREAM_BROKEN, ReachError


def channel():
    return Channel(name="web", category="web", actions=())


def spec(label):
    return BackendSpec(label, "search", tier="p2", requires_key=True)


class FirecrawlTest(unittest.TestCase):
    def tearDown(self):
        BACKENDS.clear()

    def test_search_request_shape(self):
        captured = {}

        def fake(url, **kwargs):
            captured.update(url=url, **kwargs)
            return {
                "success": True,
                "data": [{"title": "T", "url": "https://x", "description": "D"}],
            }

        register_firecrawl_backends(Keys({"search": {"firecrawl": {"api_key": "fc"}}}))
        with mock.patch("deep_reach.backends.firecrawl.p2_fetch_json", side_effect=fake):
            items = BACKENDS.get("firecrawl-search")(
                action="search",
                params={"query": "desk", "limit": 5},
                timeout=5,
                spec=spec("firecrawl-search"),
                channel=channel(),
            )

        self.assertEqual(captured["url"], "https://api.firecrawl.dev/v2/search")
        body = json.loads(captured["data"])
        self.assertEqual(body, {"query": "desk", "limit": 5})
        self.assertEqual(items[0]["title"], "T")

    def test_empty_search_is_success(self):
        register_firecrawl_backends(Keys({"search": {"firecrawl": {"api_key": "fc"}}}))
        with mock.patch(
            "deep_reach.backends.firecrawl.p2_fetch_json",
            return_value={"success": True, "data": []},
        ):
            items = BACKENDS.get("firecrawl-search")(
                action="search",
                params={"query": "desk"},
                timeout=5,
                spec=spec("firecrawl-search"),
                channel=channel(),
            )
        self.assertEqual(items, [])

    def test_scrape_parses_markdown(self):
        def fake(url, **kwargs):
            return {
                "success": True,
                "data": {"markdown": "# Hello", "metadata": {"title": "Example"}},
            }

        register_firecrawl_backends(Keys({"search": {"firecrawl": {"api_key": "fc"}}}))
        with mock.patch("deep_reach.backends.firecrawl.p2_fetch_json", side_effect=fake):
            items = BACKENDS.get("firecrawl-scrape")(
                action="read",
                params={"target": "https://example.com"},
                timeout=5,
                spec=spec("firecrawl-scrape"),
                channel=channel(),
            )

        self.assertEqual(items[0]["title"], "Example")
        self.assertEqual(items[0]["text"], "# Hello")

    def test_failed_scrape_raises(self):
        register_firecrawl_backends(Keys({"search": {"firecrawl": {"api_key": "fc"}}}))
        with mock.patch(
            "deep_reach.backends.firecrawl.p2_fetch_json",
            return_value={"success": False, "error": "blocked"},
        ):
            with self.assertRaises(ReachError) as ctx:
                BACKENDS.get("firecrawl-scrape")(
                    action="read",
                    params={"target": "https://example.com"},
                    timeout=5,
                    spec=spec("firecrawl-scrape"),
                    channel=channel(),
                )
        self.assertEqual(ctx.exception.code, UPSTREAM_BROKEN)

    def test_search_without_data_raises(self):
        register_firecrawl_backends(Keys({"search": {"firecrawl": {"api_key": "fc"}}}))
        with mock.patch(
            "deep_reach.backends.firecrawl.p2_fetch_json",
            return_value={"success": True},
        ):
            with self.assertRaises(ReachError) as ctx:
                BACKENDS.get("firecrawl-search")(
                    action="search",
                    params={"query": "desk"},
                    timeout=5,
                    spec=spec("firecrawl-search"),
                    channel=channel(),
                )
        self.assertEqual(ctx.exception.code, UPSTREAM_BROKEN)


if __name__ == "__main__":
    unittest.main()
