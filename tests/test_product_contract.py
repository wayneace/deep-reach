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

    def test_planned_channels_are_not_visible(self):
        registry = load_registry()
        for channel in registry.planned.values():
            self.assertEqual(channel.level, "planned")
            self.assertNotIn(channel.name, registry.visible)

    def test_deferred_channels_are_not_planned(self):
        planned = load_registry().planned
        for name in ("1688", "sellersprite", "tieba", "hupu"):
            self.assertNotIn(name, planned)

    def test_parser_builds_channel_action(self):
        registry = load_registry()
        parser = build_parser(registry)
        args = parser.parse_args(["bilibili", "search", "收纳", "--limit", "2"])
        self.assertEqual(args.channel_name, "bilibili")
        self.assertEqual(args.action_name, "search")
        self.assertEqual(args.query, "收纳")
        self.assertEqual(args.limit, 2)

    def test_parser_has_no_planned_channel(self):
        registry = load_registry()
        parser = build_parser(registry)
        with self.assertRaises(SystemExit):
            parser.parse_args(["kipris", "search", "x"])


if __name__ == "__main__":
    unittest.main()
