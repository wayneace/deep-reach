import os
import unittest
from unittest import mock

from deep_reach.backends.http import validate_url
from deep_reach.runtime.result import BAD_INPUT, ReachError


class UrlGuardTest(unittest.TestCase):
    def assert_blocked(self, url):
        with self.assertRaises(ReachError) as ctx:
            validate_url(url)
        self.assertEqual(ctx.exception.code, BAD_INPUT)

    def test_rejects_non_http_schemes(self):
        self.assert_blocked("file:///etc/passwd")
        self.assert_blocked("ftp://example.com/file")
        self.assert_blocked("example.com/no-scheme")

    def test_rejects_private_and_local_ip_literals(self):
        for url in (
            "http://127.0.0.1:8080/",
            "http://10.0.0.5/",
            "http://192.168.1.10/",
            "http://169.254.169.254/latest/meta-data/",
            "http://[::1]/",
            "http://0.0.0.0/",
        ):
            self.assert_blocked(url)

    def test_rejects_localhost_names(self):
        self.assert_blocked("http://localhost:3000/")
        self.assert_blocked("http://api.localhost/")

    def test_allows_public_https(self):
        with mock.patch(
            "deep_reach.backends.http.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("93.184.216.34", 0))],
        ):
            self.assertEqual(
                validate_url("https://example.com/a?b=1"),
                "https://example.com/a?b=1",
            )

    def test_allows_proxy_benchmarking_ranges(self):
        with mock.patch(
            "deep_reach.backends.http.socket.getaddrinfo",
            return_value=[
                (2, 1, 6, "", ("198.18.1.102", 0)),
                (10, 1, 6, "", ("2001:2::166", 0, 0, 0)),
            ],
        ):
            self.assertEqual(
                validate_url("https://proxy-benchmark.test/"),
                "https://proxy-benchmark.test/",
            )

    def test_env_override_allows_private_but_not_file(self):
        with mock.patch.dict(os.environ, {"DEEP_REACH_ALLOW_PRIVATE_URLS": "1"}):
            self.assertEqual(
                validate_url("http://127.0.0.1:8080/"), "http://127.0.0.1:8080/"
            )
            self.assert_blocked("file:///etc/passwd")


if __name__ == "__main__":
    unittest.main()
