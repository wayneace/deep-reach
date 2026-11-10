import unittest

from deep_reach.runtime.result import (
    UPSTREAM_BROKEN,
    ReachError,
    clear_secrets,
    dump,
    redact_text,
    register_secret,
    sanitize_url,
)


class RedactionTest(unittest.TestCase):
    def setUp(self):
        clear_secrets()

    def tearDown(self):
        clear_secrets()

    def test_error_and_dump_redact_registered_secret(self):
        register_secret("super-secret-token")
        error = ReachError(UPSTREAM_BROKEN, "failed with super-secret-token")
        self.assertNotIn("super-secret-token", error.message)
        self.assertNotIn("super-secret-token", dump({"error": error.message}))

    def test_escaped_secret_is_redacted_before_serialization(self):
        secret = 'a"b\\c\nd'
        register_secret(secret)
        self.assertNotIn("a\\\"b", dump({"value": secret}))

    def test_sanitize_url_redacts_credential_query_params(self):
        url = "https://example.test/x?key=abc123&ok=1&access_token=tok"
        cleaned = sanitize_url(url)
        self.assertNotIn("abc123", cleaned)
        self.assertNotIn("access_token=tok", cleaned)
        self.assertIn("ok=1", cleaned)

    def test_text_summary_and_doctor_text_redact(self):
        from deep_reach.cli import _text_summary
        from deep_reach.runtime.doctor import format_doctor_text

        register_secret("super-secret-token")
        summary = _text_summary(
            {
                "ok": True,
                "channel": "x",
                "action": "search",
                "backend": "b",
                "tier": "p0",
                "items": [{"title": "leak super-secret-token"}],
            }
        )
        self.assertNotIn("super-secret-token", summary)
        report = {
            "opencli": {},
            "profile": {"error": "leak super-secret-token"},
            "keys_file": "/tmp/keys",
            "keys_file_exists": True,
            "channels": [],
            "summary": {"tiers": {}},
            "state": {},
            "quota": {},
        }
        self.assertNotIn("super-secret-token", format_doctor_text(report))

    def test_short_values_are_not_registered(self):
        register_secret("abc")
        self.assertEqual(redact_text("abc"), "abc")


if __name__ == "__main__":
    unittest.main()
