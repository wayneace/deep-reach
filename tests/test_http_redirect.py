import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from deep_reach.backends.http import fetch


class _Recorder(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.records.append(
            (self.path, {name.lower(): value for name, value in self.headers.items()})
        )
        route = self.path.split("?", 1)[0]
        if route == "/start":
            self.send_response(302)
            self.send_header(
                "Location",
                f"http://127.0.0.1:{self.server.other_port}/target?key=SECRET&ok=1",
            )
            self.end_headers()
            return
        if route == "/same":
            self.send_response(302)
            self.send_header("Location", "/same-target?key=SECRET&ok=1")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        pass


class RedirectHeaderTest(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(
            os.environ, {"DEEP_REACH_ALLOW_PRIVATE_URLS": "1"}
        )
        self.env.start()
        self.addCleanup(self.env.stop)

        self.server_b = ThreadingHTTPServer(("127.0.0.1", 0), _Recorder)
        self.server_b.records = []
        self.port_b = self.server_b.server_address[1]

        self.server_a = ThreadingHTTPServer(("127.0.0.1", 0), _Recorder)
        self.server_a.records = []
        self.server_a.other_port = self.port_b
        self.port_a = self.server_a.server_address[1]

        self.threads = []
        for server in (self.server_b, self.server_a):
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.threads.append(thread)

    def tearDown(self):
        for server in (self.server_a, self.server_b):
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join(timeout=2)

    def _headers(self):
        return {
            "Authorization": "Bearer secret",
            "X-Subscription-Token": "secret",
            "X-Goog-Api-Key": "secret",
            "Cookie": "session=secret",
            "X-Public": "keep",
        }

    def test_cross_origin_redirect_strips_credentials(self):
        fetch(
            f"http://127.0.0.1:{self.port_a}/start",
            timeout=5,
            headers=self._headers(),
        )
        path, headers = self.server_b.records[-1]
        self.assertEqual(headers.get("x-public"), "keep")
        for name in (
            "authorization",
            "x-subscription-token",
            "x-goog-api-key",
            "cookie",
        ):
            self.assertNotIn(name, headers)
        self.assertNotIn("key=SECRET", path)
        self.assertIn("ok=1", path)

    def test_same_origin_redirect_keeps_credentials(self):
        fetch(
            f"http://127.0.0.1:{self.port_a}/same",
            timeout=5,
            headers=self._headers(),
        )
        path, headers = self.server_a.records[-1]
        self.assertEqual(headers.get("x-public"), "keep")
        self.assertEqual(headers.get("authorization"), "Bearer secret")
        self.assertEqual(headers.get("x-subscription-token"), "secret")
        self.assertEqual(headers.get("x-goog-api-key"), "secret")
        self.assertIn("key=SECRET", path)
        self.assertIn("ok=1", path)


if __name__ == "__main__":
    unittest.main()
