import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from deep_reach.channels import load_registry
from deep_reach.channels.base import Action, BackendSpec, Channel, Param
from deep_reach.runtime.dispatch import BACKENDS, run_action
from deep_reach.runtime.keys import Keys
from deep_reach.runtime.result import (
    CONFIG_ERROR,
    NEED_LOGIN,
    QUOTA_EXHAUSTED,
    ReachError,
)

DEMO = """
version: 1
channels:
  demo:
    level: default
    status: ready
    category: test
    description: demo channel
    actions:
      search:
        params: [query, limit]
        backends:
          - {label: p2, tier: p2}
          - {label: p1}
          - {label: p0, tier: p0}
"""


class RegistryTierTest(unittest.TestCase):
    def _registry(self, text):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".yaml", delete=False, encoding="utf-8"
        )
        handle.write(text)
        handle.close()
        self.addCleanup(Path(handle.name).unlink, missing_ok=True)
        with mock.patch.dict(os.environ, {"DEEP_REACH_CHANNELS_FILE": handle.name}):
            return load_registry()

    def test_backends_are_sorted_by_tier(self):
        registry = self._registry(DEMO)
        action = registry.visible["demo"].action("search")
        self.assertEqual([b.tier for b in action.backends], ["p0", "p1", "p2"])
        self.assertEqual(registry.visible["demo"].tiers, ("p0", "p1", "p2"))

    def test_default_tier_is_opencli(self):
        registry = self._registry(DEMO)
        action = registry.visible["demo"].action("search")
        self.assertEqual(action.backends[1].label, "p1")
        self.assertEqual(action.backends[1].tier, "p1")

    def test_unknown_tier_is_a_config_error(self):
        with self.assertRaises(ReachError) as ctx:
            self._registry(DEMO.replace("tier: p2", "tier: p9"))
        self.assertEqual(ctx.exception.code, CONFIG_ERROR)
        self.assertIn("unknown tier", ctx.exception.message)

    def test_backend_key_overrides_channel_key(self):
        text = DEMO.replace(
            "{label: p1}", "{label: p1, requires_key: true, key: custom.key}"
        )
        registry = self._registry(text)
        action = registry.visible["demo"].action("search")
        spec = next(b for b in action.backends if b.label == "p1")
        self.assertTrue(spec.requires_key)
        self.assertEqual(spec.key, "custom.key")


class TierFallbackTest(unittest.TestCase):
    def tearDown(self):
        BACKENDS.clear()

    def _channel(self, backends):
        return Channel(
            name="test",
            category="test",
            actions=(
                Action(name="search", params=(Param("query"),), backends=tuple(backends)),
            ),
        )

    def test_quota_exhausted_falls_through(self):
        def quota(**kwargs):
            raise ReachError(QUOTA_EXHAUSTED, "free quota exhausted")

        BACKENDS.register("p0", quota)
        BACKENDS.register("p1", lambda **kwargs: [{"title": "hit"}])
        channel = self._channel(
            [BackendSpec("p0", "search", tier="p0"), BackendSpec("p1", "search")]
        )
        env = run_action(channel, "search", {"query": "x"}, keys=Keys({}))
        self.assertTrue(env["ok"])
        self.assertEqual(env["backend"], "p1")
        self.assertEqual(env["tier"], "p1")
        self.assertEqual(env["meta"]["attempts"][0]["tier"], "p0")
        self.assertTrue(env["meta"]["degraded"])

    def test_login_falls_through_to_p2(self):
        def login(**kwargs):
            raise ReachError(NEED_LOGIN, "log in first")

        BACKENDS.register("p1", login)
        BACKENDS.register("p2", lambda **kwargs: [{"title": "hit"}])
        channel = self._channel(
            [BackendSpec("p1", "search"), BackendSpec("p2", "search", tier="p2")]
        )
        env = run_action(channel, "search", {"query": "x"}, keys=Keys({}))
        self.assertTrue(env["ok"])
        self.assertEqual(env["backend"], "p2")

    def test_error_priority_prefers_login_over_quota(self):
        def quota(**kwargs):
            raise ReachError(QUOTA_EXHAUSTED, "quota")

        def login(**kwargs):
            raise ReachError(NEED_LOGIN, "login")

        BACKENDS.register("p0", quota)
        BACKENDS.register("p1", login)
        channel = self._channel(
            [BackendSpec("p0", "search", tier="p0"), BackendSpec("p1", "search")]
        )
        env = run_action(channel, "search", {"query": "x"}, keys=Keys({}))
        self.assertFalse(env["ok"])
        self.assertEqual(env["error"]["code"], NEED_LOGIN)
        self.assertEqual(len(env["meta"]["attempts"]), 2)

    def test_missing_backend_key_skips_only_that_backend(self):
        BACKENDS.register("p0", lambda **kwargs: [{"title": "hit"}])
        BACKENDS.register("p1", lambda **kwargs: [{"title": "never"}])
        channel = self._channel(
            [
                BackendSpec(
                    "p1", "search", requires_key=True, key="official.demo.api_key"
                ),
                BackendSpec("p0", "search", tier="p0"),
            ]
        )
        env = run_action(channel, "search", {"query": "x"}, keys=Keys({}))
        self.assertTrue(env["ok"])
        self.assertEqual(env["backend"], "p0")


if __name__ == "__main__":
    unittest.main()
