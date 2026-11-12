import io
import unittest
from contextlib import redirect_stdout

from deep_reach.cli import main


class UpdateOutputTest(unittest.TestCase):
    def test_update_explains_cherry_installed_and_source_paths(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["update"])
        text = out.getvalue()
        self.assertEqual(code, 0)
        for phrase in (
            "Cherry Studio",
            "cli_install",
            "pipx:wayneace/deep-reach",
            "uv tool install",
            "git pull",
            "skill marketplace",
            "deep-reach skill install",
        ):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
