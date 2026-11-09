import unittest

from deep_reach.backends.opencli_compat import (
    classify_opencli_error,
    opencli_items,
    parse_envelope,
)
from deep_reach.runtime.result import (
    NEED_LOGIN,
    NOT_FOUND,
    PLATFORM_BLOCKED,
    RATE_LIMITED,
    UPSTREAM_BROKEN,
)


class OpenCLICompatTest(unittest.TestCase):
    def test_parse_envelope_with_warning_prefix(self):
        payload = parse_envelope(
            'Node warning: something\n{"ok": true, "data": [{"title": "hit"}]}'
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"][0]["title"], "hit")

    def test_parse_invalid_json(self):
        with self.assertRaises(Exception):
            parse_envelope("not json")

    def test_classify_login(self):
        err = classify_opencli_error(
            {"ok": False, "error": {"code": "AUTH_REQUIRED", "message": "please log in"}}
        )
        self.assertEqual(err.code, NEED_LOGIN)

    def test_classify_rate_limit(self):
        err = classify_opencli_error(
            {"ok": False, "error": {"code": "RATE_LIMITED", "message": "HTTP 429"}}
        )
        self.assertEqual(err.code, RATE_LIMITED)

    def test_classify_captcha(self):
        err = classify_opencli_error(
            {"ok": False, "error": {"code": "CAPTCHA_REQUIRED", "message": "验证码"}}
        )
        self.assertEqual(err.code, PLATFORM_BLOCKED)

    def test_classify_not_found(self):
        err = classify_opencli_error(
            {"ok": False, "error": {"code": "NOT_FOUND", "message": "missing"}}
        )
        self.assertEqual(err.code, NOT_FOUND)

    def test_classify_unknown(self):
        err = classify_opencli_error(
            {"ok": False, "error": {"code": "WEIRD", "message": "boom"}}
        )
        self.assertEqual(err.code, UPSTREAM_BROKEN)

    def test_opencli_items_from_list(self):
        items = opencli_items(
            [{"title": "a", "url": "u", "author": {"name": "alice"}, "likes": 3}],
            source="x",
            category="social",
            platform="twitter",
            backend="opencli-twitter",
        )
        self.assertEqual(items[0]["title"], "a")
        self.assertEqual(items[0]["author"], "alice")
        self.assertEqual(items[0]["metrics"]["likes"], 3)
        self.assertEqual(items[0]["backend"], "opencli-twitter")

    def test_opencli_items_from_wrapped_dict(self):
        items = opencli_items(
            {
                "note": {"title": "note", "content": "body"},
                "comments": [{"text": "reply", "parent_id": "1"}],
            },
            source="xiaohongshu",
            category="social",
            platform="xiaohongshu",
            backend="opencli-xiaohongshu",
        )
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["title"], "note")
        self.assertEqual(items[1]["parent_id"], "1")


if __name__ == "__main__":
    unittest.main()
