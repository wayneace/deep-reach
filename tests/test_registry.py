import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from deep_reach.channels import load_registry
from deep_reach.channels.base import Action, BackendSpec
from deep_reach.runtime.result import CONFIG_ERROR, ReachError

DEMO = """
version: 1
channels:
  demo:
    level: default
    status: ready
    category: test
    description: demo channel
    actions:
      search:
        requires: login
        ui_fallback: true
        risk: high
        params: [query]
        backends:
          - {label: bsk-ui, supports_login: true, risk: high}
"""


class RegistryAccessModelTest(unittest.TestCase):
    def _registry(self, text):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".yaml", delete=False, encoding="utf-8"
        )
        handle.write(text)
        handle.close()
        self.addCleanup(Path(handle.name).unlink, missing_ok=True)
        with mock.patch.dict(os.environ, {"DEEP_REACH_CHANNELS_FILE": handle.name}):
            return load_registry()

    def test_defaults_are_backward_compatible(self):
        backend = BackendSpec("p0", "search", tier="p0")
        self.assertFalse(backend.supports_login)
        self.assertEqual(backend.risk, "low")
        action = Action("search")
        self.assertFalse(action.ui_fallback)
        self.assertEqual(action.risk, "")

    def test_registry_parses_login_risk_and_ui_fallback(self):
        action = self._registry(DEMO).visible["demo"].action("search")
        self.assertTrue(action.ui_fallback)
        self.assertEqual(action.risk, "high")
        backend = action.backends[0]
        self.assertTrue(backend.supports_login)
        self.assertEqual(backend.risk, "high")
        self.assertNotIn("supports_login", backend.options)
        self.assertNotIn("risk", backend.options)

    def test_p3_is_not_a_backend_tier(self):
        with self.assertRaises(ReachError) as ctx:
            self._registry(DEMO.replace("supports_login: true", "tier: p3"))
        self.assertEqual(ctx.exception.code, CONFIG_ERROR)
        self.assertIn("p3", ctx.exception.message)

    def test_unknown_backend_risk_is_a_config_error(self):
        with self.assertRaises(ReachError) as ctx:
            self._registry(DEMO.replace("risk: high}", "risk: extreme}"))
        self.assertEqual(ctx.exception.code, CONFIG_ERROR)
        self.assertIn("risk", ctx.exception.message)

    def test_unknown_action_risk_is_a_config_error(self):
        with self.assertRaises(ReachError) as ctx:
            self._registry(DEMO.replace("risk: high\n        params", "risk: extreme\n        params"))
        self.assertEqual(ctx.exception.code, CONFIG_ERROR)
        self.assertIn("risk", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
