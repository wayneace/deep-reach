import os
import signal
import unittest
from types import SimpleNamespace
from unittest import mock

from deep_reach.backends.opencli import (
    OpenCLIClient,
    register_opencli_backends,
)
from deep_reach.channels.base import Action, BackendSpec, Channel, Param
from deep_reach.runtime.dispatch import BACKENDS, run_action
from deep_reach.runtime.keys import Keys
from deep_reach.runtime.result import WRITE_BLOCKED, ReachError


class FakeClient(OpenCLIClient):
    def __init__(self):
        super().__init__(bin_path="fake-opencli")

    def _run(self, argv, timeout):
        if argv[0] == "list":
            return SimpleNamespace(
                stdout=(
                    '{"ok":true,"data":{"commands":['
                    '{"command":"twitter search","access":"read"},'
                    '{"command":"twitter post","access":"write"}'
                    "]}}"
                ),
                stderr="",
                returncode=0,
            )
        if argv[0] == "twitter" and argv[1] == "search":
            return SimpleNamespace(
                stdout=(
                    '{"ok":true,"data":['
                    '{"title":"hit","url":"https://x.com/1","text":"hello"}'
                    "]}"
                ),
                stderr="",
                returncode=0,
            )
        return SimpleNamespace(
            stdout='{"ok":false,"error":{"code":"NOT_FOUND","message":"missing"}}',
            stderr="",
            returncode=1,
        )


class OpenCLIBackendTest(unittest.TestCase):
    def tearDown(self):
        BACKENDS.clear()

    def test_read_command_allowed(self):
        client = FakeClient()
        self.assertTrue(client.is_read("twitter", "search"))

    def test_write_command_blocked(self):
        client = FakeClient()
        self.assertFalse(client.is_read("twitter", "post"))
        with self.assertRaises(ReachError) as ctx:
            client.run("twitter", "post", [], timeout=5)
        self.assertEqual(ctx.exception.code, WRITE_BLOCKED)

    def test_posix_kill_tree_uses_process_group(self):
        if os.name == "nt":
            self.skipTest("POSIX only")
        client = OpenCLIClient(bin_path="fake-opencli")
        proc = mock.Mock(pid=1234)
        with mock.patch(
            "deep_reach.backends.opencli.os.getpgid", return_value=1234
        ), mock.patch("deep_reach.backends.opencli.os.killpg") as killpg:
            client._kill_tree(proc)
        killpg.assert_called_once_with(1234, signal.SIGKILL)

    def test_run_starts_new_session_on_posix(self):
        if os.name == "nt":
            self.skipTest("POSIX only")
        client = OpenCLIClient(bin_path="fake-opencli")
        fake = mock.Mock()
        fake.communicate.return_value = ("", "")
        fake.returncode = 0
        with mock.patch(
            "deep_reach.backends.opencli.subprocess.Popen", return_value=fake
        ) as popen:
            client._run(["doctor"], timeout=1, with_profile=False)
        self.assertTrue(popen.call_args.kwargs.get("start_new_session"))

    def test_posix_kill_tree_ignores_os_errors(self):
        if os.name == "nt":
            self.skipTest("POSIX only")
        client = OpenCLIClient(bin_path="fake-opencli")
        proc = mock.Mock(pid=1234)
        with mock.patch(
            "deep_reach.backends.opencli.os.getpgid",
            side_effect=PermissionError("denied"),
        ):
            client._kill_tree(proc)

    def test_keyboard_interrupt_kills_process_group(self):
        client = OpenCLIClient(bin_path="fake-opencli")
        fake = mock.Mock()
        fake.communicate.side_effect = [KeyboardInterrupt(), ("", "")]
        fake.returncode = 0
        with mock.patch(
            "deep_reach.backends.opencli.subprocess.Popen", return_value=fake
        ), mock.patch.object(client, "_kill_tree") as kill:
            with self.assertRaises(KeyboardInterrupt):
                client._run(["doctor"], timeout=1, with_profile=False)
        kill.assert_called_once_with(fake)

    def test_handler_normalizes_items(self):
        client = FakeClient()
        register_opencli_backends(client, labels=("opencli-twitter",))
        channel = Channel(
            name="x",
            category="social",
            actions=(
                Action(
                    name="search",
                    params=(Param("query"), Param("limit", required=False, type=int, default=20)),
                    backends=(
                        BackendSpec(
                            label="opencli-twitter",
                            method="search",
                            options={
                                "site": "twitter",
                                "command": "search",
                                "args": ["{query}"],
                                "limit": True,
                            },
                        ),
                    ),
                ),
            ),
        )
        env = run_action(
            channel,
            "search",
            {"query": "ai", "limit": 5},
            keys=Keys({}),
        )
        self.assertTrue(env["ok"])
        self.assertEqual(env["backend"], "opencli-twitter")
        self.assertEqual(env["items"][0]["title"], "hit")
        self.assertEqual(env["items"][0]["source"], "x")


if __name__ == "__main__":
    unittest.main()
