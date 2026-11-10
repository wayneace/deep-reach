import tempfile
import unittest
from pathlib import Path
from unittest import mock

from deep_reach.channels import load_registry
from deep_reach.runtime.doctor import build_doctor_report, format_doctor_text
from deep_reach.runtime.keys import Keys
from deep_reach.runtime.result import NEED_SETUP, ReachError


class FakeClient:
    def __init__(self, connected=True):
        self.connected = connected

    def version(self):
        return "2.0.3"

    def profile_status(self):
        if not self.connected:
            return {
                "setting": "",
                "configured": False,
                "connected": False,
                "context_id": None,
                "profile_ids": [],
                "profiles": [],
                "window": "background",
                "error": "opencli is not installed",
            }
        return {
            "setting": "test-context",
            "configured": True,
            "connected": True,
            "context_id": "test-context",
            "profile_ids": ["test-context"],
            "profiles": [
                {"contextId": "test-context", "extensionVersion": "1.0.26"}
            ],
            "window": "background",
            "extension_version": "1.0.26",
            "error": "",
        }


class MissingClient(FakeClient):
    def version(self):
        raise ReachError(NEED_SETUP, "opencli is not installed")


class DoctorTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch(
            "deep_reach.runtime.availability.bsk_available", return_value=True
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_report_has_next_actions(self):
        registry = load_registry()
        report = build_doctor_report(registry, Keys({}), client=FakeClient())
        rows = {row["name"]: row for row in report["channels"]}
        self.assertEqual(rows["bilibili"]["status"], "degraded")
        self.assertIn("subtitle", rows["bilibili"]["next_action"])
        self.assertEqual(rows["x"]["status"], "fallback")
        self.assertTrue(rows["x"]["next_action"])
        self.assertNotIn("planned", report["summary"])
        self.assertFalse(report["opencli"]["missing"])

    def test_doctor_text_mentions_next_action(self):
        registry = load_registry()
        text = format_doctor_text(build_doctor_report(registry, Keys({}), client=FakeClient()))
        self.assertIn("deep-reach doctor", text)
        self.assertIn("fallback", text)
        self.assertNotIn("PLANNED", text)
        self.assertIn("→", text)

    def test_bsk_current_profile_and_warning_are_reported(self):
        registry = load_registry()
        report = build_doctor_report(registry, Keys({}), client=FakeClient())
        self.assertEqual(report["bsk"]["profile"], "current")
        self.assertTrue(report["bsk"]["guard"])
        self.assertTrue(report["bsk"]["installed"])
        self.assertIn("write", report["bsk"]["warning"])
        rows = {row["name"]: row for row in report["channels"]}
        self.assertEqual(rows["xiaohongshu"]["risk"], "high")
        self.assertIn("search", rows["xiaohongshu"]["ui_fallback_actions"])
        self.assertGreaterEqual(report["summary"]["tiers"]["p3"], 6)
        text = format_doctor_text(report)
        self.assertIn("bsk:", text)
        self.assertIn("profile current", text)
        self.assertIn("warning:", text)
        self.assertIn("p3", text)

    def test_doctor_reports_keys_mode_and_profile_schema(self):
        registry = load_registry()
        report = build_doctor_report(registry, Keys({}), client=FakeClient())
        self.assertIn("keys_file_mode", report)
        self.assertIn("keys_file_secure", report)
        profile = report["profile"]
        for name in (
            "setting",
            "configured",
            "connected",
            "context_id",
            "profile_ids",
            "profiles",
            "window",
            "error",
            "next",
        ):
            self.assertIn(name, profile)
        self.assertEqual(profile["window"], "background")

    def test_doctor_text_warns_when_profile_is_unconfigured(self):
        report = build_doctor_report(
            load_registry(), Keys({}), client=FakeClient(connected=False)
        )
        text = format_doctor_text(report)
        self.assertIn("not configured", text)
        self.assertIn("profile launch", text)

    def test_bsk_guard_can_be_disabled(self):
        registry = load_registry()
        keys = Keys(
            {
                "browser": {"bsk_guard": False},
                "risk": {"allow_high": False},
            }
        )
        report = build_doctor_report(registry, keys, client=FakeClient())
        self.assertFalse(report["bsk"]["guard"])
        self.assertFalse(report["bsk"]["allow_high_risk"])


class DoctorEnvironmentTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch(
            "deep_reach.runtime.availability.bsk_available", return_value=True
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_missing_opencli_marks_channels_needs_setup_without_bsk(self):
        with mock.patch(
            "deep_reach.runtime.availability.shutil.which", return_value=None
        ), mock.patch(
            "deep_reach.runtime.availability.bsk_available", return_value=False
        ), mock.patch.dict("os.environ", {"DEEP_REACH_OPENCLI_BIN": ""}):
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
        self.assertEqual(report["summary"]["fallback"], 0)
        self.assertEqual(report["summary"]["runnable"], 9)

    def test_bsk_installed_marks_bsk_only_channels_fallback(self):
        with mock.patch(
            "deep_reach.runtime.availability.shutil.which", return_value=None
        ), mock.patch.dict("os.environ", {"DEEP_REACH_OPENCLI_BIN": ""}):
            report = build_doctor_report(
                load_registry(), Keys({}), client=FakeClient(connected=False)
            )
        rows = {row["name"]: row for row in report["channels"]}
        self.assertEqual(rows["x"]["status"], "fallback")
        self.assertEqual(rows["reddit"]["status"], "fallback")
        self.assertEqual(rows["youtube"]["status"], "needs_setup")
        self.assertEqual(report["summary"]["fallback"], 5)
        self.assertEqual(report["summary"]["needs_setup"], 3)
        self.assertEqual(report["summary"]["runnable"], 14)

    def test_missing_opencli_text_shows_install_command(self):
        with mock.patch(
            "deep_reach.runtime.availability.shutil.which", return_value=None
        ), mock.patch.dict("os.environ", {"DEEP_REACH_OPENCLI_BIN": ""}):
            report = build_doctor_report(
                load_registry(), Keys({}), client=MissingClient(connected=False)
            )
        text = format_doctor_text(report)
        self.assertIn("not installed", text)
        self.assertIn("npm install -g @jackwener/opencli", text)
        self.assertTrue(report["opencli"]["missing"])
        rows = {row["name"]: row for row in report["channels"]}
        self.assertIn("npm install -g @jackwener/opencli", rows["weibo"]["next_action"])

    def test_disconnected_browser_points_to_extension_not_reinstall(self):
        with mock.patch(
            "deep_reach.runtime.availability.shutil.which",
            return_value="/usr/local/bin/opencli",
        ), mock.patch.dict("os.environ", {"DEEP_REACH_OPENCLI_BIN": ""}):
            report = build_doctor_report(
                load_registry(), Keys({}), client=FakeClient(connected=False)
            )
        rows = {row["name"]: row for row in report["channels"]}
        self.assertIn("Browser Bridge", rows["weibo"]["next_action"])
        self.assertNotIn("npm install", rows["weibo"]["next_action"])

    def test_missing_keys_file_text_shows_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            key_path = Path(tmp) / "keys.yaml"
            with mock.patch(
                "deep_reach.runtime.availability.shutil.which", return_value=None
            ), mock.patch.dict("os.environ", {"DEEP_REACH_OPENCLI_BIN": ""}):
                report = build_doctor_report(
                    load_registry(),
                    Keys({}, path=key_path),
                    client=FakeClient(connected=False),
                )
        text = format_doctor_text(report)
        self.assertIn(str(key_path), text)
        self.assertIn("→ Create it from", text)
        self.assertTrue(report["keys_hint"].startswith("Create it from"))
        self.assertTrue(str(report["keys_template"]).endswith("keys.example.yaml"))


if __name__ == "__main__":
    unittest.main()
