import gzip
import unittest
import zlib

from deep_reach.backends.http import _decompress
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

    def test_gzip_bomb_is_rejected(self):
        raw = gzip.compress(b"0" * 20_000_000)
        with self.assertRaises(ReachError) as ctx:
            _decompress(raw, "gzip")
        self.assertEqual(ctx.exception.code, UPSTREAM_BROKEN)


if __name__ == "__main__":
    unittest.main()
