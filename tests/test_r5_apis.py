import unittest
from unittest import mock

from deep_reach.backends.ebay import _item_ref, _item_summary
from deep_reach.backends.etsy import _listing, _listing_id, _price
from deep_reach.backends.producthunt import _map_error, _node_item
from deep_reach.channels import load_registry
from deep_reach.runtime import quota
from deep_reach.runtime.result import (
    BAD_INPUT,
    QUOTA_EXHAUSTED,
    RATE_LIMITED,
    UPSTREAM_BROKEN,
    ReachError,
)


class EbayParseTest(unittest.TestCase):
    def test_item_ref(self):
        self.assertEqual(
            _item_ref("https://www.ebay.com/itm/123456789012")[0], "123456789012"
        )
        self.assertEqual(_item_ref("123456789012"), ("123456789012", True))
        self.assertEqual(_item_ref("v1|123|0"), ("v1|123|0", False))
        with self.assertRaises(ReachError) as ctx:
            _item_ref("nope")
        self.assertEqual(ctx.exception.code, BAD_INPUT)

    def test_item_summary(self):
        row = {
            "title": "desk organizer",
            "itemWebUrl": "https://www.ebay.com/itm/1",
            "price": {"value": "19.99", "currency": "USD"},
            "seller": {"username": "seller"},
            "image": {"imageUrl": "https://img"},
            "itemLocation": {"country": "US"},
            "condition": "New",
            "itemCreationDate": "2026-01-01T00:00:00Z",
        }
        item = _item_summary(row)
        self.assertEqual(item["source"], "ebay")
        self.assertEqual(item["metrics"]["price"], 19.99)
        self.assertEqual(item["metrics"]["currency"], "USD")
        self.assertEqual(item["author"], "seller")


class EtsyParseTest(unittest.TestCase):
    def test_price(self):
        self.assertEqual(
            _price({"amount": 1999, "divisor": 100, "currency_code": "USD"}), 19.99
        )
        self.assertIsNone(_price(None))

    def test_listing_id(self):
        self.assertEqual(_listing_id("https://www.etsy.com/listing/123/title"), "123")
        self.assertEqual(_listing_id("123"), "123")

    def test_listing(self):
        row = {
            "listing_id": 123,
            "title": "handmade tray",
            "price": {"amount": 1999, "divisor": 100, "currency_code": "USD"},
            "creation_timestamp": 1700000000,
            "views": 5,
            "num_favorers": 2,
        }
        item = _listing(row)
        self.assertEqual(item["url"], "https://www.etsy.com/listing/123")
        self.assertEqual(item["metrics"]["price"], 19.99)
        self.assertEqual(item["metrics"]["favorites"], 2)
        self.assertEqual(item["published_at"], "2023-11-14T22:13:20Z")


class ProductHuntParseTest(unittest.TestCase):
    def test_node_item(self):
        node = {
            "name": "Product",
            "tagline": "does a thing",
            "url": "https://www.producthunt.com/posts/x",
            "votesCount": 42,
            "createdAt": "2026-11-09T00:00:00Z",
        }
        item = _node_item(node)
        self.assertEqual(item["source"], "producthunt")
        self.assertEqual(item["metrics"]["votes"], 42)

    def test_error_mapping_does_not_match_moderated(self):
        err = _map_error(ReachError(UPSTREAM_BROKEN, "post was moderated"))
        self.assertEqual(err.code, UPSTREAM_BROKEN)

    def test_error_mapping_matches_rate_limit(self):
        err = _map_error(ReachError(UPSTREAM_BROKEN, "rate limit exceeded"))
        self.assertEqual(err.code, RATE_LIMITED)

    def test_rate_limit_wins_over_access_token_words(self):
        err = _map_error(
            ReachError(UPSTREAM_BROKEN, "rate limit exceeded for your access token")
        )
        self.assertEqual(err.code, RATE_LIMITED)

    def test_hyphenated_rate_limit(self):
        err = _map_error(ReachError(UPSTREAM_BROKEN, "rate-limit exceeded"))
        self.assertEqual(err.code, RATE_LIMITED)


class QuotaTest(unittest.TestCase):
    def test_reserve_and_exhaust(self):
        limits = {"test-api": {"daily": 2, "costs": {"search": 1}}}
        with mock.patch.dict(quota.LIMITS, limits, clear=False):
            quota.reserve("test-api", "search")
            quota.reserve("test-api", "search")
            with self.assertRaises(ReachError) as ctx:
                quota.reserve("test-api", "search")
            self.assertEqual(ctx.exception.code, QUOTA_EXHAUSTED)

    def test_youtube_search_costs_100_units(self):
        self.assertEqual(quota.cost_for("youtube-api", "search"), 100)
        self.assertEqual(quota.cost_for("youtube-api", "read"), 1)


class RegistryTest(unittest.TestCase):
    def test_new_channels(self):
        registry = load_registry()
        self.assertIn("ebay", registry.visible)
        self.assertIn("etsy", registry.visible)
        self.assertEqual(registry.visible["ebay"].status, "needs_key")
        self.assertIn("p0", registry.visible["ebay"].tiers)
        producthunt = registry.visible["producthunt"]
        self.assertEqual(producthunt.tiers, ("p0", "p1"))
        labels = [b.label for b in producthunt.action("hot").backends]
        self.assertEqual(labels, ["producthunt-api", "opencli-producthunt"])


if __name__ == "__main__":
    unittest.main()
