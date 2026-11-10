import os
import unittest
from unittest import mock

from deep_reach.channels.base import Action, BackendSpec, Channel, Param
from deep_reach.runtime.dispatch import BACKENDS, run_action
from deep_reach.runtime.keys import Keys
from deep_reach.runtime.result import (
    BAD_INPUT,
    NEED_LOGIN,
    NEED_UI,
    POLICY_BLOCKED,
    UPSTREAM_BROKEN,
    ReachError,
)


class DispatchTest(unittest.TestCase):
    def tearDown(self):
        BACKENDS.clear()

    def _channel(self, backends):
        return Channel(
            name="test",
            category="test",
            actions=(
                Action(
                    name="search",
                    params=(Param("query"), Param("limit", required=False, type=int, default=20)),
                    backends=tuple(backends),
                ),
            ),
        )

    def test_success(self):
        BACKENDS.register("ok", lambda **kw: [{"title": "hit"}])
        channel = self._channel([BackendSpec("ok", "search")])
        env = run_action(channel, "search", {"query": "x"}, keys=Keys({}))
        self.assertTrue(env["ok"])
        self.assertEqual(env["backend"], "ok")
        self.assertEqual(len(env["items"]), 1)

    def test_retryable_error_falls_back(self):
        def broken(**kw):
            raise ReachError(UPSTREAM_BROKEN, "boom")

        BACKENDS.register("broken", broken)
        BACKENDS.register("ok", lambda **kw: [{"title": "hit"}])
        channel = self._channel(
            [BackendSpec("broken", "search"), BackendSpec("ok", "search")]
        )
        env = run_action(channel, "search", {"query": "x"}, keys=Keys({}))
        self.assertTrue(env["ok"])
        self.assertEqual([a["result"] for a in env["meta"]["attempts"]], [UPSTREAM_BROKEN, "ok"])

    def test_final_error_stops_fallback(self):
        calls = {"second": 0}

        def bad(**kw):
            raise ReachError(BAD_INPUT, "bad")

        def second(**kw):
            calls["second"] += 1
            return []

        BACKENDS.register("bad", bad)
        BACKENDS.register("second", second)
        channel = self._channel(
            [BackendSpec("bad", "search"), BackendSpec("second", "search")]
        )
        env = run_action(channel, "search", {"query": "x"}, keys=Keys({}))
        self.assertFalse(env["ok"])
        self.assertEqual(env["error"]["code"], BAD_INPUT)
        self.assertEqual(calls["second"], 0)

    def test_missing_key_skips_keyed_backend(self):
        BACKENDS.register("keyed", lambda **kw: [{"title": "should not run"}])
        BACKENDS.register("fallback", lambda **kw: [{"title": "fallback"}])
        channel = self._channel(
            [
                BackendSpec("keyed", "search", requires_key=True),
                BackendSpec("fallback", "search"),
            ]
        )
        channel.key_path = "official.test.api_key"
        env = run_action(channel, "search", {"query": "x"}, keys=Keys({}))
        self.assertTrue(env["ok"])
        self.assertEqual(env["backend"], "fallback")
        self.assertEqual(env["meta"]["attempts"][0]["result"], "KEY_MISSING")

    def test_partial_multi_key_skips_keyed_backend(self):
        BACKENDS.register("multi", lambda **kw: [{"title": "should not run"}])
        BACKENDS.register("fallback", lambda **kw: [{"title": "fallback"}])
        channel = self._channel(
            [
                BackendSpec(
                    "multi",
                    "search",
                    requires_key=True,
                    keys=("official.test.a", "official.test.b"),
                ),
                BackendSpec("fallback", "search"),
            ]
        )
        keys = Keys({"official": {"test": {"a": "one"}}})
        env = run_action(channel, "search", {"query": "x"}, keys=keys)
        self.assertTrue(env["ok"])
        self.assertEqual(env["backend"], "fallback")
        self.assertEqual(env["meta"]["attempts"][0]["result"], "KEY_MISSING")
        self.assertIn("official.test.b", env["meta"]["attempts"][0]["message"])

    def test_bad_param_returns_envelope(self):
        channel = self._channel([BackendSpec("ok", "search")])
        env = run_action(channel, "search", {}, keys=Keys({}))
        self.assertFalse(env["ok"])
        self.assertEqual(env["error"]["code"], BAD_INPUT)

    def _login_channel(self, backends, ui_fallback=True):
        return Channel(
            name="test",
            category="test",
            actions=(
                Action(
                    name="search",
                    params=(Param("query"),),
                    backends=tuple(backends),
                    requires="login",
                    ui_fallback=ui_fallback,
                    risk="high",
                ),
            ),
        )

    def test_login_action_skips_public_backends(self):
        calls = {"public": 0, "login": 0}

        def public(**kw):
            calls["public"] += 1
            return [{"title": "public"}]

        def login(**kw):
            calls["login"] += 1
            return [{"title": "login"}]

        BACKENDS.register("public", public)
        BACKENDS.register("login", login)
        channel = self._login_channel(
            [
                BackendSpec("public", "search"),
                BackendSpec("login", "search", supports_login=True),
            ]
        )
        env = run_action(channel, "search", {"query": "x"}, keys=Keys({}))
        self.assertTrue(env["ok"])
        self.assertEqual(env["backend"], "login")
        self.assertEqual(calls, {"public": 0, "login": 1})

    def test_login_without_login_backend_returns_need_ui(self):
        calls = {"public": 0}

        def public(**kw):
            calls["public"] += 1
            return [{"title": "public"}]

        BACKENDS.register("public", public)
        channel = self._login_channel([BackendSpec("public", "search")])
        env = run_action(channel, "search", {"query": "x"}, keys=Keys({}))
        self.assertFalse(env["ok"])
        self.assertEqual(env["error"]["code"], NEED_UI)
        self.assertEqual(calls["public"], 0)
        self.assertEqual(env["tier"], "p3")
        self.assertEqual(env["meta"]["fallback"], "bsk-ui")
        self.assertEqual(env["meta"]["profile"], "main")
        self.assertEqual(env["meta"]["risk"], "high")
        self.assertIn("direct fetch/XHR", env["meta"]["policy"]["forbid"][0])
        self.assertIn("deep-reach bsk", env["error"]["hint"])

    def test_all_backends_fail_with_ui_fallback_returns_need_ui(self):
        def broken(**kw):
            raise ReachError(UPSTREAM_BROKEN, "boom")

        BACKENDS.register("broken", broken)
        channel = Channel(
            name="test",
            category="test",
            actions=(
                Action(
                    name="search",
                    params=(Param("query"),),
                    backends=(BackendSpec("broken", "search"),),
                    ui_fallback=True,
                    risk="medium",
                ),
            ),
        )
        env = run_action(channel, "search", {"query": "x"}, keys=Keys({}))
        self.assertFalse(env["ok"])
        self.assertEqual(env["error"]["code"], NEED_UI)
        self.assertEqual(env["meta"]["attempts"][0]["result"], UPSTREAM_BROKEN)
        self.assertEqual(env["meta"]["risk"], "medium")
        self.assertIn("deep-reach bsk", env["error"]["hint"])

    def test_ui_fallback_false_keeps_original_error(self):
        def broken(**kw):
            raise ReachError(UPSTREAM_BROKEN, "boom")

        BACKENDS.register("broken", broken)
        channel = self._channel([BackendSpec("broken", "search")])
        env = run_action(channel, "search", {"query": "x"}, keys=Keys({}))
        self.assertFalse(env["ok"])
        self.assertEqual(env["error"]["code"], UPSTREAM_BROKEN)

    def test_login_backend_failure_returns_need_ui(self):
        def login(**kw):
            raise ReachError(NEED_LOGIN, "login first")

        BACKENDS.register("login", login)
        channel = self._login_channel(
            [BackendSpec("login", "search", supports_login=True)]
        )
        env = run_action(channel, "search", {"query": "x"}, keys=Keys({}))
        self.assertFalse(env["ok"])
        self.assertEqual(env["error"]["code"], NEED_UI)
        self.assertEqual(env["meta"]["attempts"][0]["result"], NEED_LOGIN)

    def test_need_ui_hint_mentions_bsk_install_when_missing(self):
        channel = self._login_channel([])
        with mock.patch(
            "deep_reach.runtime.dispatch.shutil.which", return_value=None
        ), mock.patch.dict(os.environ, {"DEEP_REACH_BSK_BIN": ""}):
            env = run_action(channel, "search", {"query": "x"}, keys=Keys({}))
        self.assertEqual(env["error"]["code"], NEED_UI)
        self.assertIn("bsk 未安装", env["error"]["hint"])
        self.assertIn("AGENT_INSTALL.md", env["error"]["hint"])

    def test_high_risk_action_can_be_disabled(self):
        channel = self._login_channel([])
        keys = Keys({"risk": {"allow_high": False}})
        env = run_action(channel, "search", {"query": "x"}, keys=keys)
        self.assertFalse(env["ok"])
        self.assertEqual(env["error"]["code"], POLICY_BLOCKED)
        self.assertIn("risk.allow_high", env["error"]["message"])


if __name__ == "__main__":
    unittest.main()
