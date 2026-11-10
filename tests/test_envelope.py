import json
import unittest

from deep_reach.runtime.result import (
    BAD_INPUT,
    DEFAULT_HINTS,
    FINAL_CODES,
    KEY_MISSING,
    NEED_UI,
    ReachError,
    dump,
    envelope,
    make_item,
)


class EnvelopeTest(unittest.TestCase):
    def test_key_missing_hint_mentions_doctor(self):
        self.assertIn("deep-reach doctor", DEFAULT_HINTS[KEY_MISSING])

    def test_make_item_shape(self):
        item = make_item(
            source="youtube",
            category="social",
            platform="youtube",
            title="Example",
            url="https://example.com",
            author="alice",
            text="hello",
            backend="youtube-api",
            raw={"id": "1"},
        )
        self.assertEqual(item["source"], "youtube")
        self.assertEqual(item["title"], "Example")
        self.assertEqual(item["raw"], {"id": "1"})
        self.assertIn("fetched_at", item)

    def test_success_envelope(self):
        item = make_item(source="github", title="repo")
        env = envelope(
            channel="github",
            action="search",
            backend="github-api",
            items=[item],
            attempts=[{"backend": "github-api", "result": "ok"}],
        )
        self.assertTrue(env["ok"])
        self.assertEqual(env["backend"], "github-api")
        self.assertEqual(len(env["items"]), 1)
        self.assertFalse(env["meta"]["degraded"])
        self.assertIsNone(env["error"])

    def test_error_envelope(self):
        env = envelope(
            channel="youtube",
            action="search",
            elapsed_ms=12,
            attempts=[{"backend": "youtube-api", "result": BAD_INPUT}],
            error=ReachError(BAD_INPUT, "bad query"),
        )
        self.assertFalse(env["ok"])
        self.assertEqual(env["error"]["code"], BAD_INPUT)
        self.assertTrue(env["meta"]["degraded"])

    def test_dump_is_json(self):
        env = envelope(channel="x", action="search")
        self.assertEqual(json.loads(dump(env))["schema_version"], 1)

    def test_need_ui_is_final_and_hint_mentions_bsk(self):
        self.assertIn(NEED_UI, FINAL_CODES)
        self.assertIn("deep-reach bsk", DEFAULT_HINTS[NEED_UI])

    def test_envelope_merges_extra_meta(self):
        env = envelope(
            channel="x",
            action="search",
            tier="p3",
            error=ReachError(NEED_UI, "use bsk"),
            extra_meta={"fallback": "bsk-ui", "risk": "high"},
        )
        self.assertEqual(env["tier"], "p3")
        self.assertEqual(env["meta"]["fallback"], "bsk-ui")
        self.assertEqual(env["meta"]["risk"], "high")


if __name__ == "__main__":
    unittest.main()
