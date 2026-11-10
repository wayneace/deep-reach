import unittest
from unittest import mock

from deep_reach.backends.bsk_guard import run_bsk
from deep_reach.channels import load_registry
from deep_reach.cli import build_parser, main
from deep_reach.runtime.keys import Keys


class CliBskTest(unittest.TestCase):
    def test_parser_passes_bsk_args_through(self):
        args = build_parser(load_registry()).parse_args(
            ["bsk", "session", "start", "--json"]
        )
        self.assertEqual(args.command, "bsk")
        self.assertEqual(args.bsk_args, ["session", "start", "--json"])

    def test_main_dispatches_to_guard(self):
        with mock.patch(
            "deep_reach.cli._load_keys", return_value=Keys({})
        ), mock.patch("deep_reach.cli.run_bsk", return_value=0) as run:
            self.assertEqual(main(["bsk", "status"]), 0)
        run.assert_called_once_with(["status"], guard=True)

    def test_bsk_subprocess_gets_sanitized_env(self):
        with mock.patch("deep_reach.backends.bsk_guard.subprocess.run") as run, \
             mock.patch.dict("os.environ", {"DEEP_REACH_OFFICIAL_GITHUB_TOKEN": "x"}):
            run.return_value.returncode = 0
            run_bsk(["status"])
        env = run.call_args.kwargs["env"]
        self.assertNotIn("DEEP_REACH_OFFICIAL_GITHUB_TOKEN", env)


if __name__ == "__main__":
    unittest.main()
