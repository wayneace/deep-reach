import json
import unittest

from deep_reach.backends.xueqiu import (
    _parse_hot_posts,
    _parse_smartbox,
    _quote_time,
    _tencent_code,
    _xueqiu_symbol,
)
from deep_reach.runtime.result import BAD_INPUT, ReachError


class SymbolTest(unittest.TestCase):
    def test_tencent_codes(self):
        self.assertEqual(_tencent_code("SH600519"), "sh600519")
        self.assertEqual(_tencent_code("600519"), "sh600519")
        self.assertEqual(_tencent_code("000001"), "sz000001")
        self.assertEqual(_tencent_code("430047"), "bj430047")
        self.assertEqual(_tencent_code("920001"), "bj920001")
        self.assertEqual(_tencent_code("HK00700"), "hk00700")
        self.assertEqual(_tencent_code("00700"), "hk00700")
        self.assertEqual(_tencent_code("AAPL"), "usAAPL")

    def test_bad_symbol(self):
        with self.assertRaises(ReachError) as ctx:
            _tencent_code("???")
        self.assertEqual(ctx.exception.code, BAD_INPUT)

    def test_xueqiu_symbol(self):
        self.assertEqual(_xueqiu_symbol("sh600519"), "SH600519")
        self.assertEqual(_xueqiu_symbol("hk00700"), "00700")
        self.assertEqual(_xueqiu_symbol("usAAPL"), "AAPL")
        self.assertEqual(_xueqiu_symbol("usBRK.B"), "BRK")

    def test_quote_time_normalizes_to_utc(self):
        self.assertEqual(_quote_time("20261106161458"), "2026-11-06T08:14:58Z")
        self.assertIsNone(_quote_time("nope"))


class ParseTest(unittest.TestCase):
    def test_smartbox(self):
        text = (
            'v_hint="sh~600519~贵州茅台~GP-A~沪深~1'
            "^sz~000858~五粮液~GP-A~沪深~1\";"
        )
        rows = _parse_smartbox(text)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["market"], "sh")
        self.assertEqual(rows[0]["code"], "600519")
        self.assertEqual(rows[0]["name"], "贵州茅台")

    def test_smartbox_empty(self):
        self.assertEqual(_parse_smartbox('v_hint="N";'), [])

    def test_hot_posts(self):
        post = {
            "title": "标题",
            "text": "<p>正文</p>",
            "user": {"screen_name": "alice"},
            "target": "/123/456",
            "like_count": 7,
        }
        payload = {"list": [{"data": json.dumps(post, ensure_ascii=False)}]}
        items = _parse_hot_posts(payload, 10)
        self.assertEqual(items[0]["author"], "alice")
        self.assertEqual(items[0]["url"], "https://xueqiu.com/123/456")
        self.assertIn("正文", items[0]["text"])
        self.assertEqual(items[0]["metrics"]["likes"], 7)


if __name__ == "__main__":
    unittest.main()
