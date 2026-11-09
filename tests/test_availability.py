import unittest

from deep_reach.channels.base import Action, BackendSpec, Channel, Param
from deep_reach.runtime.availability import (
    Environment,
    channel_availability,
)
from deep_reach.runtime.keys import Keys


def channel(declared, backends, name="demo"):
    return Channel(
        name=name,
        category="test",
        status=declared,
        actions=(Action(name="search", params=(Param("query"),), backends=tuple(backends)),),
    )


def env(installed=True, connected=None, data=None):
    return Environment(
        keys=Keys(data or {}),
        opencli_installed=installed,
        browser_connected=connected,
    )


class AvailabilityTest(unittest.TestCase):
    def test_ready_channel_is_ready(self):
        result = channel_availability(
            channel("ready", [BackendSpec("http-read", "search", tier="p0")]),
            env(),
        )
        self.assertEqual(result.status, "ready")
        self.assertTrue(result.runnable)
        self.assertEqual(result.available_actions, ("search",))

    def test_missing_opencli_makes_p1_channel_needs_setup(self):
        result = channel_availability(
            channel("ready", [BackendSpec("opencli-demo", "search")]),
            env(installed=False),
        )
        self.assertEqual(result.status, "needs_setup")
        self.assertFalse(result.runnable)

    def test_partial_actions_are_degraded(self):
        ch = Channel(
            name="amazon",
            category="commerce",
            status="ready",
            actions=(
                Action("search", backends=(BackendSpec("opencli-amazon", "search"),)),
                Action(
                    "product",
                    backends=(
                        BackendSpec("opencli-amazon", "product"),
                        BackendSpec("jina", "product", tier="p2"),
                    ),
                ),
            ),
        )
        result = channel_availability(ch, env(installed=False))
        self.assertEqual(result.status, "degraded")
        self.assertTrue(result.runnable)
        self.assertEqual(result.available_actions, ("product",))
        self.assertIn("search", result.unavailable_actions)

    def test_needs_key_becomes_ready_when_key_present(self):
        ch = channel("needs_key", [BackendSpec("demo-api", "search", tier="p0", requires_key=True)])
        ch.key_path = "official.demo.api_key"
        none = channel_availability(ch, env())
        self.assertEqual(none.status, "needs_key")
        full = channel_availability(
            ch, env(data={"official": {"demo": {"api_key": "secret"}}})
        )
        self.assertEqual(full.status, "ready")

    def test_needs_login_needs_setup_without_opencli(self):
        ch = channel("needs_login", [BackendSpec("opencli-demo", "search")])
        self.assertEqual(channel_availability(ch, env(installed=False)).status, "needs_setup")
        self.assertEqual(
            channel_availability(ch, env(installed=True, connected=True)).status,
            "needs_login",
        )

    def test_experimental_stays_experimental_when_available(self):
        result = channel_availability(
            channel("experimental", [BackendSpec("http-read", "search", tier="p0")]),
            env(),
        )
        self.assertEqual(result.status, "experimental")


if __name__ == "__main__":
    unittest.main()
