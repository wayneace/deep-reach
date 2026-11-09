import json
import unittest
from unittest import mock

from deep_reach.backends.brightdata import register_brightdata_backends
from deep_reach.channels.base import BackendSpec, Channel
from deep_reach.runtime.dispatch import BACKENDS
from deep_reach.runtime.keys import Keys
from deep_reach.runtime.result import (
    BAD_INPUT,
    NEED_SETUP,
    UPSTREAM_BROKEN,
    ReachError,
)

KEYS = Keys(
    {
        "search": {
            "brightdata": {
                "api_token": "bd-token",
                "serp_zone": "serp1",
                "unlocker_zone": "unlocker1",
            }
        }
    }
)


def channel():
    return Channel(name="web", category="web", actions=())


def spec(label):
    return BackendSpec(label, "search", tier="p2", requires_key=True)


class BrightDataTest(unittest.TestCase):
    def tearDown(self):
        BACKENDS.clear()

    def test_serp_request_shape_and_organic_items(self):
        captured = {}

        def fake(url, **kwargs):
            captured.update(url=url, **kwargs)
            return {"organic": [{"title": "T", "link": "https://x", "description": "D"}]}

        register_brightdata_backends(KEYS)
        with mock.patch("deep_reach.backends.brightdata.p2_fetch_json", side_effect=fake):
            items = BACKENDS.get("brightdata-serp")(
                action="search",
                params={"query": "desk organizer", "limit": 5},
                timeout=5,
                spec=spec("brightdata-serp"),
                channel=channel(),
            )

        self.assertEqual(captured["url"], "https://api.brightdata.com/request")
        body = json.loads(captured["data"])
        self.assertEqual(body["zone"], "serp1")
        self.assertEqual(body["format"], "raw")
        self.assertIn("brd_json=json", body["url"])
        self.assertEqual(items[0]["url"], "https://x")

    def test_serp_accepts_wrapped_body(self):
        wrapped = json.dumps({"organic": [{"title": "T", "link": "https://x"}]})

        def fake(url, **kwargs):
            return {"status_code": 200, "body": wrapped}

        register_brightdata_backends(KEYS)
        with mock.patch("deep_reach.backends.brightdata.p2_fetch_json", side_effect=fake):
            items = BACKENDS.get("brightdata-serp")(
                action="search",
                params={"query": "desk"},
                timeout=5,
                spec=spec("brightdata-serp"),
                channel=channel(),
            )
        self.assertEqual(items[0]["url"], "https://x")

    def test_serp_without_organic_raises(self):
        register_brightdata_backends(KEYS)
        with mock.patch(
            "deep_reach.backends.brightdata.p2_fetch_json",
            return_value={"unexpected": []},
        ):
            with self.assertRaises(ReachError) as ctx:
                BACKENDS.get("brightdata-serp")(
                    action="search",
                    params={"query": "desk"},
                    timeout=5,
                    spec=spec("brightdata-serp"),
                    channel=channel(),
                )
        self.assertEqual(ctx.exception.code, UPSTREAM_BROKEN)

    def test_empty_organic_is_success(self):
        register_brightdata_backends(KEYS)
        with mock.patch(
            "deep_reach.backends.brightdata.p2_fetch_json",
            return_value={"organic": []},
        ):
            items = BACKENDS.get("brightdata-serp")(
                action="search",
                params={"query": "desk"},
                timeout=5,
                spec=spec("brightdata-serp"),
                channel=channel(),
            )
        self.assertEqual(items, [])

    def test_unlocker_converts_html(self):
        def fake(url, **kwargs):
            return {
                "status_code": 200,
                "body": (
                    "<html><head><title>Hello</title></head><body>"
                    "<p>World content here. This page was unlocked successfully.</p>"
                    "</body></html>"
                ),
            }

        register_brightdata_backends(KEYS)
        with mock.patch("deep_reach.backends.brightdata.p2_fetch_json", side_effect=fake):
            items = BACKENDS.get("brightdata-unlocker")(
                action="read",
                params={"target": "https://example.com"},
                timeout=5,
                spec=spec("brightdata-unlocker"),
                channel=channel(),
            )

        self.assertEqual(items[0]["title"], "Hello")
        self.assertIn("World content here", items[0]["text"])

    def test_unlocker_rejects_private_url(self):
        register_brightdata_backends(KEYS)
        with self.assertRaises(ReachError) as ctx:
            BACKENDS.get("brightdata-unlocker")(
                action="read",
                params={"target": "http://127.0.0.1/"},
                timeout=5,
                spec=spec("brightdata-unlocker"),
                channel=channel(),
            )
        self.assertEqual(ctx.exception.code, BAD_INPUT)

    def test_missing_zone_raises_need_setup(self):
        register_brightdata_backends(Keys({"search": {"brightdata": {"api_token": "t"}}}))
        with self.assertRaises(ReachError) as ctx:
            BACKENDS.get("brightdata-serp")(
                action="search",
                params={"query": "desk"},
                timeout=5,
                spec=spec("brightdata-serp"),
                channel=channel(),
            )
        self.assertEqual(ctx.exception.code, NEED_SETUP)


if __name__ == "__main__":
    unittest.main()
