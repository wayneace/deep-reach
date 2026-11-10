import os
import unittest
from unittest import mock

from deep_reach.runtime.child_env import child_env


class ChildEnvTest(unittest.TestCase):
    def test_strips_deep_reach_and_credential_names(self):
        with mock.patch.dict(
            os.environ,
            {
                "DEEP_REACH_OFFICIAL_GITHUB_TOKEN": "a",
                "DEEP_REACH_OPENCLI_BIN": "/bin/opencli",
                "GITHUB_TOKEN": "b",
                "MY_API_KEY": "c",
                "NPM_CONFIG__AUTHTOKEN": "d",
                "PATH": "/bin",
                "HOME": "/tmp",
            },
            clear=False,
        ):
            env = child_env()
        self.assertNotIn("DEEP_REACH_OFFICIAL_GITHUB_TOKEN", env)
        self.assertNotIn("DEEP_REACH_OPENCLI_BIN", env)
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertNotIn("MY_API_KEY", env)
        self.assertNotIn("NPM_CONFIG__AUTHTOKEN", env)
        self.assertEqual(env["PATH"], "/bin")
        self.assertEqual(env["HOME"], "/tmp")

    def test_extra_values_are_added(self):
        env = child_env({"OPENCLI_WINDOW": "background"})
        self.assertEqual(env["OPENCLI_WINDOW"], "background")


if __name__ == "__main__":
    unittest.main()
