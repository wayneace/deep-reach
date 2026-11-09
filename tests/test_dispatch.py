import unittest

from deep_reach.channels.base import Action, BackendSpec, Channel, Param
from deep_reach.runtime.dispatch import BACKENDS, run_action
from deep_reach.runtime.keys import Keys
from deep_reach.runtime.result import BAD_INPUT, UPSTREAM_BROKEN, ReachError


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

    def test_bad_param_returns_envelope(self):
        channel = self._channel([BackendSpec("ok", "search")])
        env = run_action(channel, "search", {}, keys=Keys({}))
        self.assertFalse(env["ok"])
        self.assertEqual(env["error"]["code"], BAD_INPUT)


if __name__ == "__main__":
    unittest.main()
