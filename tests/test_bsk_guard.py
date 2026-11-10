import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from deep_reach.backends import bsk_guard
from deep_reach.runtime.result import NEED_SETUP, POLICY_BLOCKED


class BskGuardTest(unittest.TestCase):
    def _run(self, args, returncode=0):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch(
            "deep_reach.backends.bsk_guard.subprocess.run"
        ) as run, redirect_stdout(out), redirect_stderr(err):
            run.return_value = mock.Mock(returncode=returncode)
            code = bsk_guard.run_bsk(args, bin_path="bsk")
        return code, out.getvalue(), err.getvalue(), run

    def _assert_blocked(self, args):
        code, stdout, _, run = self._run(args)
        self.assertEqual(code, 1)
        run.assert_not_called()
        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], POLICY_BLOCKED)
        return payload

    def test_debug_replay_is_blocked(self):
        self._assert_blocked(["debug", "replay", "--session", "s1"])

    def test_evaluate_fetch_is_blocked(self):
        self._assert_blocked(["evaluate", "fetch('/api/x')"])

    def test_evaluate_xhr_is_blocked(self):
        self._assert_blocked(["evaluate", "new XMLHttpRequest()"])

    def test_evaluate_dom_read_is_allowed(self):
        code, _, _, run = self._run(["evaluate", "document.title"])
        self.assertEqual(code, 0)
        run.assert_called_once_with(["bsk", "evaluate", "document.title"])

    def test_debug_requests_is_allowed(self):
        code, _, _, run = self._run(["debug", "requests"])
        self.assertEqual(code, 0)
        run.assert_called_once_with(["bsk", "debug", "requests"])

    def test_network_read_is_allowed(self):
        code, _, _, run = self._run(["network"])
        self.assertEqual(code, 0)
        run.assert_called_once_with(["bsk", "network"])

    def test_click_is_allowed(self):
        code, _, _, run = self._run(["click", "@e1"])
        self.assertEqual(code, 0)
        run.assert_called_once_with(["bsk", "click", "@e1"])

    def test_write_is_allowed_with_warning(self):
        code, _, stderr, run = self._run(["post", "hello"])
        self.assertEqual(code, 0)
        run.assert_called_once_with(["bsk", "post", "hello"])
        self.assertIn("write operation", stderr)

    def test_rule_add_warns_but_runs(self):
        code, _, stderr, run = self._run(
            ["debug", "rule_add", "--rule-file", "rules.json"]
        )
        self.assertEqual(code, 0)
        run.assert_called_once()
        self.assertIn("rule_add", stderr)

    def test_child_exit_code_is_passed_through(self):
        code, _, _, run = self._run(["status"], returncode=7)
        self.assertEqual(code, 7)
        run.assert_called_once_with(["bsk", "status"])

    def test_missing_bsk_returns_need_setup(self):
        out = io.StringIO()
        with mock.patch(
            "deep_reach.backends.bsk_guard.subprocess.run",
            side_effect=FileNotFoundError("bsk"),
        ), redirect_stdout(out):
            code = bsk_guard.run_bsk(["status"], bin_path="bsk")
        self.assertEqual(code, 1)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["error"]["code"], NEED_SETUP)


if __name__ == "__main__":
    unittest.main()
