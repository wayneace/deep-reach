import unittest

from deep_reach.channels import load_registry
from deep_reach.cli import build_parser


class ProductContractTest(unittest.TestCase):
    def test_visible_channels_have_actions_and_levels(self):
        registry = load_registry()
        self.assertTrue(registry.visible)
        for channel in registry.visible.values():
            self.assertIn(channel.level, {"default", "optional", "experimental"})
            self.assertTrue(channel.actions, channel.name)
            self.assertTrue(channel.description, channel.name)
            for action in channel.actions:
                self.assertIn(action.requires, {"none", "login", "key"})
                self.assertTrue(
                    action.backends or action.ui_fallback,
                    f"{channel.name}/{action.name}",
                )

    def test_registry_has_no_planned_bucket(self):
        registry = load_registry()
        self.assertFalse(hasattr(registry, "planned"))
        self.assertTrue(registry.visible)
        for channel in registry.visible.values():
            self.assertNotEqual(channel.level, "planned", channel.name)

    def test_parser_rejects_removed_and_unknown_channels(self):
        parser = build_parser(load_registry())
        for name in ("roadmap", "kipris", "hackernews"):
            with self.assertRaises(SystemExit):
                parser.parse_args([name, "search", "x"])

    def test_parser_builds_channel_action(self):
        registry = load_registry()
        parser = build_parser(registry)
        args = parser.parse_args(["bilibili", "search", "收纳", "--limit", "2"])
        self.assertEqual(args.channel_name, "bilibili")
        self.assertEqual(args.action_name, "search")
        self.assertEqual(args.query, "收纳")
        self.assertEqual(args.limit, 2)

if __name__ == "__main__":
    unittest.main()
