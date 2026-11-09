import unittest
from unittest import mock

from deep_reach.channels import load_registry
from deep_reach.runtime.doctor import build_doctor_report, format_doctor_text
from deep_reach.runtime.keys import Keys


class FakeClient:
    def __init__(self, connected=True):
        self.connected = connected

    def version(self):
        return "2.0.3"

    def profile_status(self):
        if not self.connected:
            return {"connected": False, "error": "opencli is not installed"}
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
        registry = load_registry()
        text = format_doctor_text(build_doctor_report(registry, Keys({}), client=FakeClient()))
        self.assertIn("deep-reach doctor", text)
        self.assertIn("needs_login", text)
        self.assertIn("→", text)


class DoctorEnvironmentTest(unittest.TestCase):
    def test_missing_opencli_marks_channels_needs_setup(self):
        with mock.patch("deep_reach.runtime.availability.shutil.which", return_value=None):
            report = build_doctor_report(
                load_registry(), Keys({}), client=FakeClient(connected=False)
            )
        rows = {row["name"]: row for row in report["channels"]}
        self.assertEqual(rows["youtube"]["status"], "needs_setup")
        self.assertEqual(rows["weibo"]["status"], "needs_setup")
        self.assertEqual(rows["amazon"]["status"], "degraded")
        self.assertEqual(rows["x"]["status"], "needs_setup")
        self.assertEqual(rows["ebay"]["status"], "needs_key")
        self.assertEqual(rows["bilibili"]["status"], "degraded")
        self.assertEqual(rows["github"]["status"], "ready")
        self.assertEqual(rows["youtube"]["declared_status"], "ready")
        self.assertEqual(report["summary"]["needs_setup"], 8)
        self.assertEqual(report["summary"]["runnable"], 9)


if __name__ == "__main__":
    unittest.main()
