import unittest
from unittest import mock

from deep_reach.backends.brave import register_brave_backend
from deep_reach.channels.base import BackendSpec, Channel
from deep_reach.runtime.dispatch import BACKENDS
from deep_reach.runtime.keys import Keys
from deep_reach.runtime.result import UPSTREAM_BROKEN, ReachError


def channel():
    return Channel(name="web", category="web", actions=())


def spec():
    return BackendSpec("brave-search", "search", tier="p2", requires_key=True)


class BraveTest(unittest.TestCase):
    def tearDown(self):
        BACKENDS.clear()

    def test_search_request_shape_and_items(self):
        captured = {}

        def fake(url, **kwargs):
            captured.update(url=url, **kwargs)
            return {
                "web": {
                    "results": [
                        {"title": "Desk", "url": "https://example.com", "description": "hi"}
                    ]
                }
            }

        register_brave_backend(Keys({"search": {"brave": {"api_key": "brave-key"}}}))
        with mock.patch("deep_reach.backends.brave.p2_fetch_json", side_effect=fake):
            items = BACKENDS.get("brave-search")(
                action="search",
                params={"query": "desk", "limit": 5},
                timeout=5,
                spec=spec(),
                channel=channel(),
            )

        self.assertEqual(
            captured["url"], "https://api.search.brave.com/res/v1/web/search"
        )
        self.assertEqual(captured["headers"]["X-Subscription-Token"], "brave-key")
        self.assertEqual(captured["params"], {"q": "desk", "count": 5})
        self.assertEqual(items[0]["title"], "Desk")

    def test_missing_web_results_raises(self):
        register_brave_backend(Keys({"search": {"brave": {"api_key": "k"}}}))
        with mock.patch("deep_reach.backends.brave.p2_fetch_json", return_value={}):
            with self.assertRaises(ReachError) as ctx:
                BACKENDS.get("brave-search")(
                    action="search",
                    params={"query": "desk"},
                    timeout=5,
                    spec=spec(),
                    channel=channel(),
                )
        self.assertEqual(ctx.exception.code, UPSTREAM_BROKEN)

    def test_empty_results_are_success(self):
        register_brave_backend(Keys({"search": {"brave": {"api_key": "k"}}}))
        with mock.patch(
            "deep_reach.backends.brave.p2_fetch_json",
            return_value={"web": {"results": []}},
        ):
            items = BACKENDS.get("brave-search")(
                action="search",
                params={"query": "desk"},
                timeout=5,
                spec=spec(),
                channel=channel(),
            )
        self.assertEqual(items, [])


if __name__ == "__main__":
    unittest.main()
