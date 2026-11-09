import unittest

from deep_reach.channels import load_registry
from deep_reach.cli import build_parser
from deep_reach.runtime.availability import Environment, channel_availability
from deep_reach.runtime.keys import Keys


class P2RegistryTest(unittest.TestCase):
    def test_web_search_backends_in_order(self):
        action = load_registry().visible["web"].action("search")
        self.assertEqual(
            [b.label for b in action.backends],
            ["tavily-search", "brave-search", "firecrawl-search", "brightdata-serp"],
        )
        self.assertTrue(all(b.tier == "p2" for b in action.backends))
        self.assertTrue(all(b.requires_key for b in action.backends))

    def test_web_search_parser(self):
        args = build_parser(load_registry()).parse_args(
            ["web", "search", "desk", "--limit", "5"]
        )
        self.assertEqual(args.channel_name, "web")
        self.assertEqual(args.action_name, "search")
        self.assertEqual(args.query, "desk")
        self.assertEqual(args.limit, 5)

    def test_web_search_needs_key_without_keys(self):
        channel = load_registry().visible["web"]
        env = Environment(keys=Keys({}), opencli_installed=False)
        result = channel_availability(channel, env)
        self.assertIn("search", result.unavailable_actions)
        self.assertIn("read", result.available_actions)

    def test_web_search_ready_with_one_key(self):
        channel = load_registry().visible["web"]
        keys = Keys({"search": {"tavily": {"api_key": "tvly-test"}}})
        env = Environment(keys=keys, opencli_installed=False)
        result = channel_availability(channel, env)
        self.assertIn("search", result.available_actions)


if __name__ == "__main__":
    unittest.main()
