import importlib.util
from pathlib import Path
import sys
import unittest

SOURCE_DIR = Path(__file__).parents[1] / "src/opnsense/scripts/OPNsense/WanQuota"
sys.path.insert(0, str(SOURCE_DIR))
SPEC = importlib.util.spec_from_file_location("wanquota_intelligence", SOURCE_DIR / "intelligence.py")
INTELLIGENCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INTELLIGENCE)


class IntelligenceTests(unittest.TestCase):
    def test_longest_domain_suffix_category(self):
        categories = {"Video": ("youtube.com",), "Other service": ("example.net",)}
        # The builtin taxonomy was renamed to app-oriented labels: what the
        # traffic is for, rather than which service operates it.
        self.assertEqual(INTELLIGENCE.suffix_category("r1.googlevideo.com", INTELLIGENCE.BUILTIN_CATEGORIES), "Media Streaming")
        self.assertEqual(INTELLIGENCE.suffix_category("cdn.example.net", categories), "Other service")

    def test_device_group_accepts_host_and_cidr(self):
        groups = [{"name": "Infrastructure", "members": ["192.0.2.1", "198.51.100.0/24"]}]
        self.assertEqual(INTELLIGENCE.group_for("198.51.100.20", groups), "Infrastructure")
        self.assertEqual(INTELLIGENCE.group_for("203.0.113.5", groups), "Ungrouped")

    def test_policy_applies_nothing_by_default(self):
        item = {"percent": 95, "remaining": 5e9}
        cfg = {"reserve_gb": 1, "enforcement": False, "dry_run": True, "policy": "observe"}
        decision = INTELLIGENCE.policy_decision(item, cfg)
        self.assertEqual(decision["recommended"], "failover")
        self.assertEqual(decision["applied"], "none")
        self.assertFalse(decision["enforcing"])

    def test_each_reason_for_not_enforcing_is_named_separately(self):
        """One word for three situations is how "enforcement off" came to read as
        "dry run", which a user then read as their live setting having been reverted."""
        item = {"percent": 95, "remaining": 5e9}
        cases = {
            "off": {"enforcement": False, "dry_run": False, "policy": "failover"},
            "dry_run": {"enforcement": True, "dry_run": True, "policy": "failover"},
            "observe_only": {"enforcement": True, "dry_run": False, "policy": "observe"},
            "live": {"enforcement": True, "dry_run": False, "policy": "failover"},
        }
        for expected, extra in cases.items():
            cfg = {"reserve_gb": 1, **extra}
            decision = INTELLIGENCE.policy_decision(item, cfg)
            self.assertEqual(decision["state"], expected, extra)
            self.assertEqual(decision["enforcing"], expected == "live", extra)

    def test_dry_run_now_means_the_dry_run_setting_only(self):
        item = {"percent": 95, "remaining": 5e9}
        off = INTELLIGENCE.policy_decision(
            item, {"reserve_gb": 1, "enforcement": False, "dry_run": False, "policy": "cutoff"})
        self.assertFalse(off["dry_run"], "enforcement being off is not dry run")
        self.assertEqual(off["state"], "off")

    def test_override_expires_and_can_reduce_action(self):
        item = {"percent": 100, "remaining": 0}
        cfg = {"reserve_gb": 1, "enforcement": True, "dry_run": False, "policy": "cutoff"}
        decision = INTELLIGENCE.policy_decision(item, cfg, {"mode": "observe", "expires": 9999999999})
        self.assertEqual(decision["applied"], "observe")

    def test_custom_guardrail_thresholds_drive_recommendation(self):
        item = {"percent": 72, "remaining": 20e9}
        cfg = {"reserve_gb": 1, "enforcement": False, "dry_run": True, "policy": "cutoff", "thresholds": [40, 60, 80, 95]}
        decision = INTELLIGENCE.policy_decision(item, cfg)
        self.assertEqual(decision["recommended"], "deprioritize")
        self.assertEqual(decision["thresholds"], [40, 60, 80, 95])


if __name__ == "__main__":
    unittest.main()
