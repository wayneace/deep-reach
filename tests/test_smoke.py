import importlib.util
import unittest
from pathlib import Path

from deep_reach.channels import load_registry

ROOT = Path(__file__).resolve().parents[1]


def _load_smoke_module():
    spec = importlib.util.spec_from_file_location(
        "deep_reach_smoke", ROOT / "scripts" / "smoke.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SmokeProfileTest(unittest.TestCase):
    def test_opencli_only_detection(self):
        smoke = _load_smoke_module()
        registry = load_registry()
        self.assertTrue(smoke._opencli_only(registry.visible["weibo"], "hot"))
        self.assertFalse(smoke._opencli_only(registry.visible["bilibili"], "search"))


if __name__ == "__main__":
    unittest.main()
