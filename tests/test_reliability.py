import time
import unittest
from unittest import mock

from deep_reach.channels.base import Action, BackendSpec, Channel, Param
from deep_reach.runtime import health, state
from deep_reach.runtime.clock import Clock
from deep_reach.runtime.dispatch import BACKENDS, run_action
from deep_reach.runtime.keys import Keys
from deep_reach.runtime.limits import acquire_request, pace
from deep_reach.runtime.result import (
    BUSY,
    NEED_LOGIN,
    RATE_LIMITED,
    UPSTREAM_BROKEN,
    ReachError,
)


def make_channel(backends):
    return Channel(
        name="test",
        category="test",
        actions=(
            Action(name="search", params=(Param("query"),), backends=tuple(backends)),
        ),
    )


class ReliabilityTest(unittest.TestCase):
    def tearDown(self):
        BACKENDS.clear()

    def test_channel_cooldown_blocks_before_any_backend(self):
        channel = make_channel([BackendSpec("ok", "search")])
        health.remember(
            "test",
            "search",
            "ok",
            ReachError(RATE_LIMITED, "limited"),
            health.fingerprint(channel),
        )
        calls = []
        BACKENDS.register("ok", lambda **kwargs: calls.append(1) or [])
        env = run_action(channel, "search", {"query": "x"}, keys=Keys({}))
        self.assertFalse(env["ok"])
        self.assertEqual(env["error"]["code"], RATE_LIMITED)
        self.assertEqual(calls, [])

    def test_paused_backend_is_skipped(self):
        channel = make_channel(
            [BackendSpec("broken", "search"), BackendSpec("ok", "search")]
        )
        health.remember(
            "test",
            "search",
            "broken",
            ReachError(UPSTREAM_BROKEN, "boom"),
            health.fingerprint(channel),
        )
        calls = []
        BACKENDS.register("broken", lambda **kwargs: calls.append("broken") or [])
        BACKENDS.register("ok", lambda **kwargs: calls.append("ok") or [{"title": "hit"}])
        env = run_action(channel, "search", {"query": "x"}, keys=Keys({}))
        self.assertTrue(env["ok"])
        self.assertEqual(calls, ["ok"])
        first = env["meta"]["attempts"][0]
        self.assertTrue(first["skipped"])
        self.assertEqual(first["result"], UPSTREAM_BROKEN)
        self.assertIn("retry_after_seconds", first)

    def test_success_clears_saved_pause(self):
        channel = make_channel([BackendSpec("flaky", "search")])
        fingerprint = health.fingerprint(channel)
        health.remember(
            "test",
            "search",
            "flaky",
            ReachError(UPSTREAM_BROKEN, "boom"),
            fingerprint,
        )
        self.assertIsNotNone(
            health.backend_pause("test", "search", "flaky", fingerprint)
        )
        health.clear_backend("test", "search", "flaky")
        self.assertIsNone(health.backend_pause("test", "search", "flaky", fingerprint))

    def test_rate_limited_stops_fallback_and_cools_channel(self):
        channel = make_channel(
            [BackendSpec("limited", "search"), BackendSpec("ok", "search")]
        )
        calls = []

        def limited(**kwargs):
            raise ReachError(RATE_LIMITED, "limited")

        BACKENDS.register("limited", limited)
        BACKENDS.register("ok", lambda **kwargs: calls.append("ok") or [])
        env = run_action(channel, "search", {"query": "x"}, keys=Keys({}))
        self.assertFalse(env["ok"])
        self.assertEqual(env["error"]["code"], RATE_LIMITED)
        self.assertEqual(calls, [])
        self.assertIsNotNone(health.cooldown("test"))

    def test_busy_stops_fallback(self):
        channel = make_channel(
            [BackendSpec("opencli-test", "search"), BackendSpec("ok", "search")]
        )
        calls = []

        def busy(**kwargs):
            raise ReachError(BUSY, "browser full")

        BACKENDS.register("opencli-test", busy)
        BACKENDS.register("ok", lambda **kwargs: calls.append("ok") or [])
        env = run_action(channel, "search", {"query": "x"}, keys=Keys({}))
        self.assertFalse(env["ok"])
        self.assertEqual(env["error"]["code"], BUSY)
        self.assertEqual(calls, [])

    def test_login_is_not_a_backend_pause(self):
        channel = make_channel([BackendSpec("opencli-test", "search")])
        fingerprint = health.fingerprint(channel)
        health.remember(
            "test",
            "search",
            "opencli-test",
            ReachError(NEED_LOGIN, "login"),
            fingerprint,
        )
        self.assertIsNone(
            health.backend_pause("test", "search", "opencli-test", fingerprint)
        )

    def test_pacing_waits_between_searches(self):
        state.mutate(
            lambda data: data.setdefault("request_starts", {}).__setitem__(
                "test", time.time()
            )
        )
        clock = Clock(5)
        with mock.patch("deep_reach.runtime.limits.BROWSER_SEARCH_INTERVAL", 0.2):
            started = time.monotonic()
            pace("test", "search", clock)
            elapsed = time.monotonic() - started
        self.assertGreaterEqual(elapsed, 0.15)

    def test_site_request_limit_is_shared_across_callers(self):
        # Two sequential calls stand in for two processes: the window lives in
        # state.json, not in process memory, so they share one budget.
        with mock.patch("deep_reach.runtime.limits.SITE_REQUEST_LIMIT", 2):
            acquire_request("test", Clock(5))
            acquire_request("test", Clock(5))
            with self.assertRaises(ReachError) as ctx:
                acquire_request("test", Clock(0.1))
            self.assertEqual(ctx.exception.code, BUSY)
            # Another channel has its own window.
            acquire_request("other", Clock(0.1))

    def test_default_site_request_limit_is_40(self):
        from deep_reach.runtime import limits

        self.assertEqual(limits.SITE_REQUEST_LIMIT, 40)

    def test_clock_pause_does_not_spend_budget(self):
        clock = Clock(0.5)
        clock.pause()
        time.sleep(0.3)
        self.assertGreater(clock.remaining(), 0.4)
        clock.resume()
        self.assertLessEqual(clock.remaining(), 0.6)


if __name__ == "__main__":
    unittest.main()
