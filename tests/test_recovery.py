import datetime as dt
import importlib.util
from pathlib import Path
import sys
import unittest


SCRIPT_DIR = Path(__file__).parents[1] / "src/opnsense/scripts/OPNsense/WanQuota"
sys.path.insert(0, str(SCRIPT_DIR))
SPEC = importlib.util.spec_from_file_location("wanquota_recovery", SCRIPT_DIR / "recovery.py")
RECOVERY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECOVERY)


class RecoveryDecisionTests(unittest.TestCase):
    def setUp(self):
        self.provider = {"logical_interface": "wan", "enabled": True}
        self.options = {"failures": 3, "cooldown_minutes": 360, "daily_limit": 2, "minimum_remaining_gb": 1}
        self.quota = {"available": True, "remaining": 10_000_000_000}
        self.now = dt.datetime(2026, 8, 16, 3, 0, tzinfo=dt.timezone.utc)
        self.state = {}

    def decide(self, internet=False, alternate=True, quota=None):
        return RECOVERY.decision(self.provider, self.options, self.quota if quota is None else quota, internet, alternate, self.now, self.state)

    def test_requires_consecutive_failures(self):
        self.assertEqual(self.decide(), "confirming-failure")
        self.assertEqual(self.decide(), "confirming-failure")
        self.assertEqual(self.decide(), "recover")

    def test_healthy_probe_clears_failure_count(self):
        self.decide()
        self.assertEqual(self.decide(internet=True), "healthy")
        self.assertEqual(self.state["wan"]["failures"], 0)

    def test_never_recovers_when_alternate_is_down(self):
        for _ in range(4):
            result = self.decide(alternate=False)
        self.assertEqual(result, "alternate-unavailable")

    def test_never_recovers_without_available_quota(self):
        for _ in range(3):
            result = self.decide(quota={"available": False, "remaining": 0})
        self.assertEqual(result, "quota-unavailable")

    def test_never_recovers_when_quota_is_exhausted(self):
        for _ in range(3):
            result = self.decide(quota={"available": True, "remaining": 0})
        self.assertEqual(result, "quota-exhausted")

    def test_cooldown_blocks_repeated_action(self):
        self.state = {"wan": {"failures": 2, "last_attempt": int(self.now.timestamp()) - 60, "attempts": []}}
        self.assertEqual(self.decide(), "cooldown")

    def test_daily_limit_blocks_action(self):
        day = self.now.date().isoformat()
        self.state = {"wan": {"failures": 2, "last_attempt": 0, "attempts": [{"day": day}, {"day": day}]}}
        self.assertEqual(self.decide(), "daily-limit")


if __name__ == "__main__":
    unittest.main()
