import gzip
import unittest
import zlib
from email.message import Message
from unittest import mock

from deep_reach.backends.http import _decompress, fetch
from deep_reach.runtime.result import UPSTREAM_BROKEN, ReachError


class DecompressTest(unittest.TestCase):
    def test_gzip_round_trip(self):
        raw = gzip.compress(b"hello world")
        self.assertEqual(_decompress(raw, "gzip"), b"hello world")

    def test_multi_member_gzip(self):
        raw = gzip.compress(b"abc") + gzip.compress(b"def")
        self.assertEqual(_decompress(raw, "gzip"), b"abcdef")

    def test_truncated_gzip_is_rejected(self):
        raw = gzip.compress(b"hello")[:-4]
        with self.assertRaises(ReachError) as ctx:
            _decompress(raw, "gzip")
        self.assertEqual(ctx.exception.code, UPSTREAM_BROKEN)

    def test_deflate_round_trip(self):
        compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
        raw = compressor.compress(b"hello world") + compressor.flush()
        self.assertEqual(_decompress(raw, "deflate"), b"hello world")

    def test_zlib_wrapped_deflate(self):
        raw = zlib.compress(b"hello world")
        self.assertEqual(_decompress(raw, "deflate"), b"hello world")

    def test_gzip_bomb_is_rejected(self):
        raw = gzip.compress(b"0" * 20_000_000)
        with self.assertRaises(ReachError) as ctx:
            _decompress(raw, "gzip")
        self.assertEqual(ctx.exception.code, UPSTREAM_BROKEN)


class FetchDecompressTest(unittest.TestCase):
    def test_fetch_decompresses_gzip_body(self):
        class FakeResponse:
            status = 200

            def __init__(self):
                self.headers = Message()
                self.headers["Content-Encoding"] = "gzip"
                self.headers["Content-Type"] = "text/plain; charset=utf-8"

            def read(self, limit):
                return gzip.compress(b"hello world")

            def geturl(self):
                return "https://example.com/"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with mock.patch(
            "deep_reach.backends.http._OPENER.open",
            return_value=FakeResponse(),
        ), mock.patch(
            "deep_reach.backends.http._host_is_private", return_value=False
        ):
            response = fetch("https://example.com/", timeout=1)
        self.assertEqual(response.text, "hello world")


if __name__ == "__main__":
    unittest.main()
