import datetime as dt
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SOURCE = Path(__file__).parents[1] / "src/opnsense/scripts/OPNsense/WanQuota/report.py"
SPEC = importlib.util.spec_from_file_location("wanquota_report", SOURCE)
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)


class BillingCycleTests(unittest.TestCase):
    def test_cycle_starts_this_month(self):
        self.assertEqual(
            REPORT.cycle_bounds(dt.date(2026, 8, 15), 1),
            (dt.date(2026, 8, 1), dt.date(2026, 9, 1)),
        )

    def test_cycle_starts_previous_month(self):
        self.assertEqual(
            REPORT.cycle_bounds(dt.date(2026, 8, 14), 15),
            (dt.date(2026, 7, 15), dt.date(2026, 8, 15)),
        )

    def test_month_end_is_clamped(self):
        self.assertEqual(
            REPORT.cycle_bounds(dt.date(2026, 2, 28), 31),
            (dt.date(2026, 2, 28), dt.date(2026, 3, 28)),
        )

    def test_bounded_integer_rejects_invalid_input(self):
        self.assertEqual(REPORT.bounded_int("invalid", 80, 1, 100), 80)
        self.assertEqual(REPORT.bounded_int("500", 80, 1, 100), 100)

    def test_configuration_supports_four_and_skips_disabled_providers(self):
        xml = """<opnsense><interfaces><wan><if>wan0</if></wan><opt1><if>wan1</if></opt1><opt2><if>wan2</if></opt2><opt3><if>wan3</if></opt3></interfaces><OPNsense><WanQuota><general><provider1_enabled>1</provider1_enabled><provider2_enabled>0</provider2_enabled><provider3_enabled>1</provider3_enabled><provider3_name>Backup LTE</provider3_name><provider3_interface>opt2</provider3_interface><provider4_enabled>1</provider4_enabled><provider4_interface>opt3</provider4_interface></general></WanQuota></OPNsense></opnsense>"""
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as handle:
            handle.write(xml); handle.flush()
            with mock.patch.object(REPORT, "CONFIG_PATH", handle.name):
                enabled, providers = REPORT.configuration()
        self.assertTrue(enabled)
        self.assertEqual([item["interface"] for item in providers], ["wan0", "wan2", "wan3"])
        self.assertEqual(providers[1]["name"], "Backup LTE")

    def test_alerts_are_deduplicated(self):
        document = {"providers": [{
            "name": "ISP 1", "logical_interface": "wan", "start": "2026-08-01",
            "available": True, "percent": 85, "warning_percent": 80,
            "projected": 90_000_000_000, "quota": 100_000_000_000,
            "remaining": 15_000_000_000,
        }]}
        with mock.patch.object(REPORT, "alert_configuration", return_value={"enabled": True, "projection": True, "repeat_hours": 24}), \
             mock.patch.object(REPORT, "load_alert_state", return_value={}), \
             mock.patch.object(REPORT, "save_alert_state") as save:
            result = REPORT.evaluate_alerts(document, now=100_000, emit=False)
        self.assertEqual([event["condition"] for event in result["events"]], ["threshold"])
        save.assert_called_once()

    def test_projection_alert(self):
        document = {"providers": [{
            "name": "ISP 2", "logical_interface": "opt1", "start": "2026-08-15",
            "available": True, "percent": 40, "warning_percent": 80,
            "projected": 120_000_000_000, "quota": 100_000_000_000,
            "remaining": 60_000_000_000,
        }]}
        with mock.patch.object(REPORT, "alert_configuration", return_value={"enabled": True, "projection": True, "repeat_hours": 24}), \
             mock.patch.object(REPORT, "load_alert_state", return_value={}), \
             mock.patch.object(REPORT, "save_alert_state"):
            result = REPORT.evaluate_alerts(document, now=100_000, emit=False)
        self.assertEqual(result["events"][0]["condition"], "projection")


if __name__ == "__main__":
    unittest.main()
