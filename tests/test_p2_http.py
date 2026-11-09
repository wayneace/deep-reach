import io
import unittest
import urllib.error
from unittest import mock

from deep_reach.backends.http import fetch, fetch_json
from deep_reach.runtime.result import (
    NEED_SETUP,
    NOT_FOUND,
    QUOTA_EXHAUSTED,
    ReachError,
)


def http_error(status: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://example.com", status, "err", {}, io.BytesIO(b"denied")
    )


class CodeMapTest(unittest.TestCase):
    def test_code_map_overrides_401(self):
        with mock.patch("deep_reach.backends.http.validate_url"), mock.patch(
            "deep_reach.backends.http._OPENER.open", side_effect=http_error(401)
        ):
            with self.assertRaises(ReachError) as ctx:
                fetch("https://example.com", timeout=1, code_map={401: NEED_SETUP})
        self.assertEqual(ctx.exception.code, NEED_SETUP)

    def test_code_map_overrides_429_for_json(self):
        with mock.patch("deep_reach.backends.http.validate_url"), mock.patch(
            "deep_reach.backends.http._OPENER.open", side_effect=http_error(429)
        ):
            with self.assertRaises(ReachError) as ctx:
                fetch_json(
                    "https://example.com", timeout=1, code_map={429: QUOTA_EXHAUSTED}
                )
        self.assertEqual(ctx.exception.code, QUOTA_EXHAUSTED)

    def test_default_mapping_is_unchanged(self):
        with mock.patch("deep_reach.backends.http.validate_url"), mock.patch(
            "deep_reach.backends.http._OPENER.open", side_effect=http_error(404)
        ):
            with self.assertRaises(ReachError) as ctx:
                fetch("https://example.com", timeout=1)
        self.assertEqual(ctx.exception.code, NOT_FOUND)


if __name__ == "__main__":
    unittest.main()
