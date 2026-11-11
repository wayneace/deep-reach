import json
import os
import signal
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

from deep_reach.backends.opencli import (
    OpenCLIClient,
    make_opencli_handler,
    register_opencli_backends,
    version_status,
)
from deep_reach.channels.base import Action, BackendSpec, Channel, Param
from deep_reach.runtime.dispatch import BACKENDS, run_action
from deep_reach.runtime.keys import Keys
from deep_reach.runtime.result import NEED_SETUP, ReachError


class FakeClient(OpenCLIClient):
    def __init__(self):
        super().__init__(bin_path="fake-opencli")

    def _run(self, argv, timeout, with_profile=True):
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


class OpenCLIAutoLaunchTest(unittest.TestCase):
    def _client(self, profile="ctx-1234", auto_launch=True):
        return OpenCLIClient(
            bin_path=sys.executable,
            profile=profile,
            auto_launch=auto_launch,
        )

    def test_ensure_browser_skips_when_connected(self):
        client = self._client()
        with mock.patch.object(
            client, "profile_status", return_value={"connected": True}
        ), mock.patch("deep_reach.runtime.profile.launch") as launch:
            client.ensure_browser()
        launch.assert_not_called()

    def test_ensure_browser_launches_dedicated_profile(self):
        client = self._client()
        with mock.patch.object(
            client,
            "profile_status",
            side_effect=[{"connected": False}, {"connected": True}],
        ), mock.patch(
            "deep_reach.runtime.profile.launch", return_value={"ok": True}
        ) as launch, mock.patch("deep_reach.backends.opencli.time.sleep"):
            client.ensure_browser()
        launch.assert_called_once_with(page=None)

    def test_ensure_browser_raises_when_launch_fails(self):
        client = self._client()
        with mock.patch.object(
            client, "profile_status", return_value={"connected": False}
        ), mock.patch(
            "deep_reach.runtime.profile.launch",
            return_value={"ok": False, "error": "chrome missing"},
        ):
            with self.assertRaises(ReachError) as ctx:
                client.ensure_browser()
        self.assertEqual(ctx.exception.code, NEED_SETUP)
        self.assertIn("chrome missing", ctx.exception.message)

    def test_ensure_browser_raises_after_timeout(self):
        client = self._client()
        client.connect_timeout = 0
        with mock.patch.object(
            client, "profile_status", return_value={"connected": False}
        ), mock.patch(
            "deep_reach.runtime.profile.launch", return_value={"ok": True}
        ):
            with self.assertRaises(ReachError) as ctx:
                client.ensure_browser()
        self.assertEqual(ctx.exception.code, NEED_SETUP)

    def test_ensure_browser_skips_without_profile(self):
        client = self._client(profile="")
        with mock.patch.object(client, "profile_status") as status, mock.patch(
            "deep_reach.runtime.profile.launch"
        ) as launch:
            client.ensure_browser()
        status.assert_not_called()
        launch.assert_not_called()

    def test_ensure_browser_skips_without_opencli(self):
        client = OpenCLIClient(
            bin_path="/no/such/opencli", profile="ctx-1234", auto_launch=True
        )
        with mock.patch.object(client, "profile_status") as status, mock.patch(
            "deep_reach.runtime.profile.launch"
        ) as launch:
            client.ensure_browser()
        status.assert_not_called()
        launch.assert_not_called()

    def test_ensure_browser_is_off_by_default(self):
        client = OpenCLIClient(
            bin_path=sys.executable, profile="ctx-1234"
        )
        with mock.patch.object(client, "profile_status") as status, mock.patch(
            "deep_reach.runtime.profile.launch"
        ) as launch:
            client.ensure_browser()
        status.assert_not_called()
        launch.assert_not_called()

    def test_close_browser_is_off_by_default(self):
        client = OpenCLIClient(bin_path=sys.executable, profile="ctx-1234")
        with mock.patch("deep_reach.runtime.profile.close") as close:
            client.close_browser()
        close.assert_not_called()

    def test_close_browser_closes_dedicated_profile(self):
        client = self._client()
        with mock.patch("deep_reach.runtime.profile.close") as close:
            client.close_browser()
        close.assert_called_once_with()

    def test_handler_closes_browser_after_success(self):
        client = self._client()
        client.ensure_browser = mock.Mock()
        client.run = mock.Mock(return_value={"items": []})
        client.close_browser = mock.Mock()
        handler = make_opencli_handler(client)
        spec = BackendSpec("opencli-demo", "search", options={"site": "demo"})
        channel = Channel("demo", "social", ())
        with mock.patch(
            "deep_reach.backends.opencli.opencli_items", return_value=[]
        ):
            handler(
                action="search",
                params={},
                timeout=5,
                spec=spec,
                channel=channel,
            )
        client.close_browser.assert_called_once_with()

    def test_handler_closes_browser_after_failure(self):
        client = self._client()
        client.ensure_browser = mock.Mock()
        client.run = mock.Mock(side_effect=ReachError(NEED_SETUP, "boom"))
        client.close_browser = mock.Mock()
        handler = make_opencli_handler(client)
        spec = BackendSpec("opencli-demo", "search", options={"site": "demo"})
        channel = Channel("demo", "social", ())
        with self.assertRaises(ReachError):
            handler(
                action="search",
                params={},
                timeout=5,
                spec=spec,
                channel=channel,
            )
        client.close_browser.assert_called_once_with()


class OpenCLIBackendTest(unittest.TestCase):
    def tearDown(self):
        BACKENDS.clear()

    def test_read_command_allowed(self):
        client = FakeClient()
        self.assertTrue(client.is_read("twitter", "search"))

    def test_write_command_allowed(self):
        client = FakeClient()
        self.assertFalse(client.is_read("twitter", "post"))
        result = SimpleNamespace(
            stdout='{"ok":true,"data":{"posted":true}}', stderr="", returncode=0
        )
        with mock.patch.object(client, "_run", return_value=result) as run:
            data = client.run("twitter", "post", [], timeout=5)
        self.assertEqual(data, {"posted": True})
        run.assert_called_once()

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

    def test_missing_binary_error_gives_install_command(self):
        client = OpenCLIClient(bin_path="deep-reach-test-opencli-missing")
        with self.assertRaises(ReachError) as ctx:
            client.version()
        self.assertEqual(ctx.exception.code, NEED_SETUP)
        self.assertIn("npm install -g @jackwener/opencli", ctx.exception.message)
        self.assertIn("cli_install", ctx.exception.message)
        self.assertIn("npm:@jackwener/opencli", ctx.exception.message)

    def test_no_profile_is_need_setup(self):
        client = OpenCLIClient(bin_path="fake-opencli", profile="")
        with self.assertRaises(ReachError) as ctx:
            client._run(["bilibili", "search", "x"], timeout=5)
        self.assertEqual(ctx.exception.code, NEED_SETUP)
        self.assertIn("dedicated", ctx.exception.message.lower())

    def test_auto_is_treated_as_unconfigured(self):
        client = OpenCLIClient(bin_path="fake-opencli", profile="auto")
        self.assertEqual(client.profile, "")

    def test_legacy_env_does_not_set_profile(self):
        with mock.patch.dict(os.environ, {"DEEP_REACH_OPENCLI_PROFILE": "ctx-1234"}):
            client = OpenCLIClient(bin_path="fake-opencli")
        self.assertEqual(client.profile, "")

    def test_profile_status_reports_selected_context(self):
        client = OpenCLIClient(bin_path="fake-opencli", profile="ctx-1234")
        payload = {
            "ok": True,
            "data": {
                "extensionConnected": True,
                "profiles": [
                    {"contextId": "main-999", "extensionVersion": "1.0"},
                    {"contextId": "ctx-1234", "extensionVersion": "2.0"},
                ],
            },
        }
        with mock.patch.object(
            client,
            "_run",
            return_value=SimpleNamespace(
                stdout=json.dumps(payload), stderr="", returncode=0
            ),
        ):
            status = client.profile_status()
        self.assertTrue(status["configured"])
        self.assertTrue(status["connected"])
        self.assertEqual(status["context_id"], "ctx-1234")
        self.assertEqual(status["profile_ids"], ["main-999", "ctx-1234"])

    def test_version_status_outdated_gives_npm_upgrade(self):
        status = version_status("2.0.1")
        self.assertFalse(status["up_to_date"])
        self.assertIn("npm install -g @jackwener/opencli", status["action"])


if __name__ == "__main__":
    unittest.main()
