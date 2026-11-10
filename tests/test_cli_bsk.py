import unittest
from unittest import mock

from deep_reach.channels import load_registry
from deep_reach.cli import build_parser, main


class CliBskTest(unittest.TestCase):
    def test_parser_passes_bsk_args_through(self):
        args = build_parser(load_registry()).parse_args(
            ["bsk", "session", "start", "--json"]
        )
        self.assertEqual(args.command, "bsk")
        self.assertEqual(args.bsk_args, ["session", "start", "--json"])

    def test_main_dispatches_to_guard(self):
        with mock.patch("deep_reach.cli.run_bsk", return_value=0) as run:
            self.assertEqual(main(["bsk", "status"]), 0)
        run.assert_called_once_with(["status"], guard=True)


if __name__ == "__main__":
    unittest.main()
