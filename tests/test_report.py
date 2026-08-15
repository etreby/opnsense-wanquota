import datetime as dt
import importlib.util
from pathlib import Path
import unittest


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


if __name__ == "__main__":
    unittest.main()
