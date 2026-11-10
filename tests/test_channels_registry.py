import unittest

from deep_reach.channels import load_registry


class ChannelsRegistryModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = load_registry()

    def _action(self, channel, action):
        return self.registry.visible[channel].action(action)

    def _labels(self, channel, action):
        return [backend.label for backend in self._action(channel, action).backends]

    def test_web_read_is_public_first(self):
        action = self._action("web", "read")
        self.assertEqual(
            [backend.label for backend in action.backends],
            [
                "http-read",
                "jina",
                "firecrawl-scrape",
                "tavily-extract",
                "brightdata-unlocker",
            ],
        )
        self.assertEqual(
            [backend.tier for backend in action.backends],
            ["p1", "p1", "p2", "p2", "p2"],
        )

    def test_login_only_social_actions_have_no_opencli(self):
        targets = {
            "x": ("search", "read"),
            "reddit": ("search", "read"),
            "xiaohongshu": ("search", "read", "comments"),
            "zhihu": ("search", "read"),
            "douyin": ("search", "videos", "detail"),
        }
        for channel, actions in targets.items():
            for name in actions:
                action = self._action(channel, name)
                self.assertEqual(action.backends, (), (channel, name))
                self.assertTrue(action.ui_fallback, (channel, name))
                self.assertEqual(action.risk, "high", (channel, name))

    def test_login_only_public_opencli_actions_become_fallbacks(self):
        for channel, name in (("weibo", "search"), ("bilibili", "subtitle")):
            action = self._action(channel, name)
            self.assertEqual(action.backends, (), (channel, name))
            self.assertTrue(action.ui_fallback, (channel, name))
            self.assertEqual(action.risk, "high", (channel, name))

    def test_xueqiu_login_actions_keep_p0_and_drop_opencli(self):
        for name in ("hot", "hot_stocks"):
            action = self._action("xueqiu", name)
            labels = [backend.label for backend in action.backends]
            self.assertIn("xueqiu-api", labels, name)
            self.assertNotIn("opencli-xueqiu", labels, name)
            self.assertTrue(action.ui_fallback, name)
            self.assertEqual(action.risk, "high", name)
            api = next(
                backend for backend in action.backends if backend.label == "xueqiu-api"
            )
            self.assertTrue(api.supports_login, name)

    def test_public_opencli_backends_are_preserved(self):
        targets = (
            ("bilibili", "search"),
            ("bilibili", "read"),
            ("bilibili", "comments"),
            ("weibo", "hot"),
            ("weibo", "read"),
            ("weibo", "comments"),
            ("xueqiu", "quote"),
            ("xueqiu", "search"),
            ("xueqiu", "comments"),
            ("amazon", "search"),
            ("producthunt", "hot"),
        )
        for channel, name in targets:
            labels = self._labels(channel, name)
            self.assertTrue(
                any(label.startswith("opencli-") for label in labels),
                (channel, name, labels),
            )

    def test_all_opencli_backends_are_p1(self):
        for channel in self.registry.channels.values():
            for action in channel.actions:
                for backend in action.backends:
                    if backend.label.startswith("opencli-"):
                        self.assertEqual(
                            backend.tier, "p1", (channel.name, action.name, backend.label)
                        )

    def test_jina_is_always_public_tier(self):
        for channel in self.registry.channels.values():
            for action in channel.actions:
                for backend in action.backends:
                    if backend.label == "jina":
                        self.assertEqual(
                            backend.tier, "p1", (channel.name, action.name)
                        )


if __name__ == "__main__":
    unittest.main()
