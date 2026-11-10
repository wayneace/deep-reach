import os
import unittest
from pathlib import Path
from unittest import mock

from deep_reach.channels import load_registry
from deep_reach.channels.base import Action, BackendSpec, Channel, Param
from deep_reach.runtime.availability import (
    Environment,
    action_risk,
    channel_availability,
    channel_risk,
    detect_environment,
    next_action_for,
)
from deep_reach.runtime.keys import Keys


def channel(declared, backends, name="demo"):
    return Channel(
        name=name,
        category="test",
        status=declared,
        actions=(Action(name="search", params=(Param("query"),), backends=tuple(backends)),),
    )


def env(installed=True, connected=None, data=None, bsk=False, profile_configured=True):
    return Environment(
        keys=Keys(data or {}),
        opencli_installed=installed,
        browser_connected=connected,
        bsk_installed=bsk,
        opencli_profile_configured=profile_configured,
    )


def bsk_only_channel():
    return Channel(
        name="x",
        category="social",
        status="needs_login",
        actions=(
            Action(
                "search",
                requires="login",
                ui_fallback=True,
                risk="high",
                backends=(),
            ),
            Action(
                "read",
                requires="login",
                ui_fallback=True,
                risk="high",
                backends=(),
            ),
        ),
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

    def test_opencli_without_profile_is_needs_setup(self):
        result = channel_availability(
            channel("ready", [BackendSpec("opencli-demo", "search")]),
            env(installed=True, profile_configured=False),
        )
        self.assertEqual(result.status, "needs_setup")
        self.assertFalse(result.runnable)

    def test_opencli_with_profile_and_connection_is_ready(self):
        result = channel_availability(
            channel("ready", [BackendSpec("opencli-demo", "search")]),
            env(installed=True, connected=True, profile_configured=True),
        )
        self.assertEqual(result.status, "ready")

    def test_env_only_profile_counts_as_configured(self):
        with mock.patch.dict(
            os.environ, {"DEEP_REACH_BROWSER_OPENCLI_PROFILE": "ctx-1234"}
        ):
            detected = detect_environment(
                Keys({"browser": {"opencli_profile": ""}})
            )
        self.assertTrue(detected.opencli_profile_configured)

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

    def test_bsk_only_channel_is_fallback_when_bsk_installed(self):
        result = channel_availability(bsk_only_channel(), env(installed=False, bsk=True))
        self.assertEqual(result.status, "fallback")
        self.assertTrue(result.runnable)
        self.assertEqual(result.available_actions, ())
        self.assertEqual(result.ui_fallback_actions, ("search", "read"))

    def test_bsk_only_channel_needs_setup_without_bsk(self):
        result = channel_availability(
            bsk_only_channel(), env(installed=False, bsk=False)
        )
        self.assertEqual(result.status, "needs_setup")
        self.assertFalse(result.runnable)

    def test_next_action_for_fallback_mentions_bsk(self):
        ch = bsk_only_channel()
        environment = env(installed=False, bsk=True)
        result = channel_availability(ch, environment)
        hint = next_action_for(ch, result, environment)
        self.assertIn("deep-reach bsk", hint)
        self.assertIn("当前浏览器 profile", hint)
        self.assertNotIn("OpenCLI", hint)

    def test_next_action_for_needs_setup_mentions_bsk_install_when_missing(self):
        ch = bsk_only_channel()
        environment = env(installed=False, bsk=False)
        result = channel_availability(ch, environment)
        hint = next_action_for(ch, result, environment)
        self.assertIn("安装 bsk", hint)
        self.assertIn("AGENT_INSTALL.md", hint)

    def test_experimental_stays_experimental_when_available(self):
        result = channel_availability(
            channel("experimental", [BackendSpec("http-read", "search", tier="p0")]),
            env(),
        )
        self.assertEqual(result.status, "experimental")

    def test_xueqiu_hot_requires_cookie(self):
        xueqiu = load_registry().visible["xueqiu"]
        result = channel_availability(xueqiu, env(installed=False))
        self.assertNotIn("hot", result.available_actions)
        self.assertNotIn("hot_stocks", result.available_actions)
        self.assertIn("quote", result.available_actions)

    def test_partial_multi_key_is_needs_key(self):
        ebay = load_registry().visible["ebay"]
        partial = Environment(
            keys=Keys({"official": {"ebay": {"client_id": "id"}}}),
            opencli_installed=False,
        )
        self.assertEqual(channel_availability(ebay, partial).status, "needs_key")
        full = Environment(
            keys=Keys(
                {"official": {"ebay": {"client_id": "id", "client_secret": "secret"}}}
            ),
            opencli_installed=False,
        )
        self.assertEqual(channel_availability(ebay, full).status, "ready")

    def test_multi_key_channel_requires_every_key(self):
        ch = channel(
            "needs_key",
            [
                BackendSpec(
                    "demo-api",
                    "search",
                    tier="p0",
                    requires_key=True,
                    keys=("official.demo.a", "official.demo.b"),
                )
            ],
        )
        partial = Environment(
            keys=Keys({"official": {"demo": {"a": "one"}}}), opencli_installed=False
        )
        self.assertEqual(channel_availability(ch, partial).status, "needs_key")

    def test_next_action_for_needs_setup_mentions_opencli(self):
        ch = channel("ready", [BackendSpec("opencli-demo", "search")])
        ch.next_action = "search 需要登录"
        result = channel_availability(ch, env(installed=False))
        hint = next_action_for(ch, result)
        self.assertIn("OpenCLI", hint)
        self.assertIn("deep-reach doctor", hint)
        self.assertIn("安装后", hint)

    def test_next_action_for_missing_opencli_gives_install_command(self):
        ch = channel("ready", [BackendSpec("opencli-demo", "search")])
        environment = env(installed=False)
        result = channel_availability(ch, environment)
        hint = next_action_for(ch, result, environment)
        self.assertIn("npm install -g @jackwener/opencli", hint)
        self.assertIn("deep-reach doctor", hint)

    def test_next_action_for_disconnected_browser_mentions_extension(self):
        ch = channel("ready", [BackendSpec("opencli-demo", "search")])
        environment = env(installed=True, connected=False)
        result = channel_availability(ch, environment)
        hint = next_action_for(ch, result, environment)
        self.assertIn("Browser Bridge", hint)
        self.assertNotIn("npm install", hint)

    def test_next_action_for_degraded_key_missing_gives_keys_file(self):
        ch = Channel(
            name="xueqiu",
            category="social",
            status="ready",
            actions=(
                Action("hot", backends=(BackendSpec("opencli-demo", "hot"),)),
                Action(
                    "hot_stocks",
                    backends=(
                        BackendSpec(
                            "xueqiu-api",
                            "hot_stocks",
                            tier="p0",
                            requires_key=True,
                            key="xueqiu.cookie",
                        ),
                    ),
                ),
            ),
        )
        key_path = Path("/nonexistent/deep-reach-keys.yaml")
        environment = Environment(
            keys=Keys({}, path=key_path),
            opencli_installed=True,
            browser_connected=True,
            opencli_profile_configured=True,
        )
        result = channel_availability(ch, environment)
        self.assertEqual(result.status, "degraded")
        hint = next_action_for(ch, result, environment)
        self.assertIn(str(key_path), hint)
        self.assertIn("keys.example.yaml", hint)

    def test_next_action_for_needs_key_gives_keys_file_and_template(self):
        ch = channel(
            "needs_key",
            [BackendSpec("demo-api", "search", tier="p0", requires_key=True)],
        )
        ch.key_path = "official.demo.api_key"
        ch.next_action = "申请 demo key"
        key_path = Path("/tmp/deep-reach-keys.yaml")
        environment = Environment(
            keys=Keys({}, path=key_path),
            opencli_installed=False,
        )
        result = channel_availability(ch, environment)
        hint = next_action_for(ch, result, environment)
        self.assertIn(str(key_path), hint)
        self.assertIn("keys.example.yaml", hint)
        self.assertIn("申请 demo key", hint)

    def test_next_action_for_degraded_lists_unavailable_actions(self):
        ch = Channel(
            name="amazon",
            category="commerce",
            status="ready",
            actions=(
                Action("search", backends=(BackendSpec("opencli-amazon", "search"),)),
                Action("product", backends=(BackendSpec("jina", "product", tier="p2"),)),
            ),
        )
        result = channel_availability(ch, env(installed=False))
        hint = next_action_for(ch, result)
        self.assertIn("search", hint)
        self.assertIn("不可用", hint)

    def test_login_action_skips_public_only_backend(self):
        ch = Channel(
            name="x",
            category="social",
            status="needs_login",
            actions=(
                Action(
                    "search",
                    requires="login",
                    backends=(BackendSpec("public", "search"),),
                ),
            ),
        )
        result = channel_availability(ch, env(installed=True, connected=True))
        self.assertNotIn("search", result.available_actions)
        self.assertIn("does not support login", " ".join(result.unavailable_actions["search"]))

    def test_action_risk_uses_highest_backend_risk(self):
        action = Action(
            "search",
            backends=(
                BackendSpec("demo", "search", risk="medium"),
                BackendSpec("other", "search", risk="high"),
            ),
        )
        self.assertEqual(action_risk(action), "high")

    def test_action_risk_keeps_higher_action_risk(self):
        action = Action(
            "search",
            risk="high",
            backends=(BackendSpec("demo", "search", risk="low"),),
        )
        self.assertEqual(action_risk(action), "high")

    def test_channel_risk_uses_backend_risk(self):
        ch = Channel(
            name="demo",
            category="test",
            status="ready",
            actions=(
                Action(
                    "search",
                    backends=(BackendSpec("demo", "search", risk="high"),),
                ),
            ),
        )
        self.assertEqual(channel_risk(ch), "high")

    def test_login_action_accepts_supports_login_backend(self):
        ch = Channel(
            name="xueqiu",
            category="social",
            status="needs_login",
            actions=(
                Action(
                    "hot",
                    requires="login",
                    backends=(
                        BackendSpec(
                            "xueqiu-api",
                            "hot",
                            tier="p0",
                            supports_login=True,
                        ),
                    ),
                ),
            ),
        )
        result = channel_availability(ch, env(installed=False))
        self.assertIn("hot", result.available_actions)


if __name__ == "__main__":
    unittest.main()
