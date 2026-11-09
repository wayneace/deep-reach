import unittest

from deep_reach.channels import load_registry
from deep_reach.runtime.doctor import build_doctor_report
from deep_reach.runtime.keys import Keys


class FakeClient:
    def version(self):
        return "2.0.3"

    def profile_status(self):
        return {
            "connected": True,
            "context_id": "test-context",
            "extension_version": "1.0.26",
        }


class DoctorTest(unittest.TestCase):
    def test_report_has_next_actions(self):
        registry = load_registry()
        report = build_doctor_report(registry, Keys({}), client=FakeClient())
        rows = {row["name"]: row for row in report["channels"]}
        self.assertEqual(rows["bilibili"]["status"], "ready")
        self.assertEqual(rows["x"]["status"], "needs_login")
        self.assertTrue(rows["x"]["next_action"])
        self.assertIn("planned", report["summary"])

    def test_doctor_text_mentions_next_action(self):
        from deep_reach.runtime.doctor import format_doctor_text

        registry = load_registry()
        text = format_doctor_text(build_doctor_report(registry, Keys({}), client=FakeClient()))
        self.assertIn("deep-reach doctor", text)
        self.assertIn("needs_login", text)
        self.assertIn("→", text)


if __name__ == "__main__":
    unittest.main()
