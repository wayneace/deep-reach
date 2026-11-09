import json
import unittest
from unittest import mock

from deep_reach.backends.tavily import register_tavily_backends
from deep_reach.channels.base import BackendSpec, Channel
from deep_reach.runtime.dispatch import BACKENDS
from deep_reach.runtime.keys import Keys
from deep_reach.runtime.result import UPSTREAM_BROKEN, ReachError


def make_channel():
    return Channel(name="web", category="web", actions=())


def spec(label):
    return BackendSpec(label=label, method="search", tier="p2", requires_key=True)


class TavilyTest(unittest.TestCase):
    def tearDown(self):
        BACKENDS.clear()

    def test_search_request_shape_and_items(self):
        captured = {}

        def fake(url, **kwargs):
            captured.update(url=url, **kwargs)
            return {
                "results": [
                    {"title": "Desk", "url": "https://example.com/a", "content": "hello"}
                ]
            }

        register_tavily_backends(Keys({"search": {"tavily": {"api_key": "tvly-test"}}}))
        with mock.patch("deep_reach.backends.tavily.p2_fetch_json", side_effect=fake):
            items = BACKENDS.get("tavily-search")(
                action="search",
                params={"query": "desk", "limit": 5},
                timeout=5,
                spec=spec("tavily-search"),
                channel=make_channel(),
            )

        self.assertEqual(captured["url"], "https://api.tavily.com/search")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer tvly-test")
        body = json.loads(captured["data"])
        self.assertEqual(body["query"], "desk")
        self.assertEqual(body["max_results"], 5)
        self.assertEqual(items[0]["title"], "Desk")
        self.assertEqual(items[0]["backend"], "tavily-search")

    def test_empty_results_are_success(self):
        register_tavily_backends(Keys({"search": {"tavily": {"api_key": "k"}}}))
        with mock.patch(
            "deep_reach.backends.tavily.p2_fetch_json",
            return_value={"results": []},
        ):
            items = BACKENDS.get("tavily-search")(
                action="search",
                params={"query": "desk"},
                timeout=5,
                spec=spec("tavily-search"),
                channel=make_channel(),
            )
        self.assertEqual(items, [])

    def test_extract_parses_raw_content(self):
        def fake(url, **kwargs):
            return {
                "results": [{"url": "https://example.com", "raw_content": "# Hello"}]
            }

        register_tavily_backends(Keys({"search": {"tavily": {"api_key": "k"}}}))
        with mock.patch("deep_reach.backends.tavily.p2_fetch_json", side_effect=fake):
            items = BACKENDS.get("tavily-extract")(
                action="read",
                params={"target": "https://example.com"},
                timeout=5,
                spec=spec("tavily-extract"),
                channel=make_channel(),
            )

        self.assertEqual(items[0]["text"], "# Hello")

    def test_malformed_payload_raises_upstream_broken(self):
        register_tavily_backends(Keys({"search": {"tavily": {"api_key": "k"}}}))
        with mock.patch(
            "deep_reach.backends.tavily.p2_fetch_json", return_value={"unexpected": []}
        ):
            with self.assertRaises(ReachError) as ctx:
                BACKENDS.get("tavily-search")(
                    action="search",
                    params={"query": "desk"},
                    timeout=5,
                    spec=spec("tavily-search"),
                    channel=make_channel(),
                )
        self.assertEqual(ctx.exception.code, UPSTREAM_BROKEN)


if __name__ == "__main__":
    unittest.main()
