"""Per-device enforcement: who is a member, and who can never be.

This is the only part of the plugin that can take a device off the network, so
the membership rules are tested directly and pf is never invoked.
"""

import importlib.util
from pathlib import Path
import sys
import unittest

SOURCE_DIR = Path(__file__).parents[1] / "src/opnsense/scripts/OPNsense/WanQuota"
sys.path.insert(0, str(SOURCE_DIR))
SPEC = importlib.util.spec_from_file_location("wanquota_devices", SOURCE_DIR / "devices.py")
DEVICES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEVICES)

ROUTER = "192.168.1.1"


def host(ip, total, name=None, mac="", hostname=""):
    return {"ip": ip, "total": total, "name": name or ip, "mac": mac, "hostname": hostname}


class MembershipTests(unittest.TestCase):
    def members(self, hosts, devices=(), groups=()):
        index = DEVICES.intelligence.policy_index(list(devices))
        return DEVICES.over_budget(hosts, index, list(groups), ROUTER)

    def test_device_over_its_budget_is_a_member(self):
        members, _ = self.members(
            [host("192.168.1.20", 60e9, "Laptop")],
            [{"address": "192.168.1.20", "budget_gb": 50}])
        self.assertEqual([m["device"] for m in members], ["192.168.1.20"])
        self.assertAlmostEqual(members[0]["over_by"], 10e9)

    def test_device_under_budget_is_not(self):
        members, _ = self.members(
            [host("192.168.1.20", 10e9)], [{"address": "192.168.1.20", "budget_gb": 50}])
        self.assertEqual(members, [])

    def test_device_with_no_budget_is_never_a_member(self):
        members, _ = self.members([host("192.168.1.20", 900e9)], [])
        self.assertEqual(members, [])

    def test_zero_budget_is_treated_as_unset_not_as_block_everything(self):
        members, _ = self.members(
            [host("192.168.1.20", 900e9)], [{"address": "192.168.1.20", "budget_gb": 0}])
        self.assertEqual(members, [])

    def test_the_router_is_never_a_member(self):
        members, skipped = self.members(
            [host(ROUTER, 900e9, "firewall")], [{"address": ROUTER, "budget_gb": 1}])
        self.assertEqual(members, [])
        self.assertEqual(skipped[0]["reason"], "router")

    def test_an_excluded_device_is_never_a_member(self):
        members, skipped = self.members(
            [host("192.168.1.20", 900e9)],
            [{"address": "192.168.1.20", "budget_gb": 1, "exclude": True}])
        self.assertEqual(members, [])
        self.assertIn("excluded", skipped[0]["reason"])

    def test_protected_infrastructure_is_never_a_member(self):
        members, skipped = self.members(
            [host("192.168.1.10", 900e9, "TRUENAS")],
            [{"address": "192.168.1.10", "budget_gb": 1}],
            [{"name": "Protected Infrastructure", "members": ["192.168.1.0/28"]}])
        self.assertEqual(members, [])
        self.assertIn("protected group", skipped[0]["reason"])

    def test_budget_matched_by_mac_still_applies(self):
        members, _ = self.members(
            [host("192.168.1.99", 60e9, "Roamer", mac="aa:bb:cc:dd:ee:ff")],
            [{"mac": "AA:BB:CC:DD:EE:FF", "budget_gb": 50}])
        self.assertEqual([m["device"] for m in members], ["192.168.1.99"])

    def test_non_literal_address_is_skipped(self):
        members, skipped = self.members(
            [host("not-an-ip", 60e9)], [{"address": "not-an-ip", "budget_gb": 1}])
        self.assertEqual(members, [])
        self.assertIn("literal", skipped[0]["reason"])

    def test_hosts_without_an_address_are_ignored(self):
        members, _ = self.members([{"total": 900e9}], [])
        self.assertEqual(members, [])


class TableTests(unittest.TestCase):
    class FakeResult:
        def __init__(self, returncode=0, stderr=""):
            self.returncode = returncode
            self.stderr = stderr

    def test_replace_is_a_single_atomic_call(self):
        calls = []

        def runner(args):
            calls.append(args)
            return self.FakeResult()

        ok, error = DEVICES.apply_table(["192.168.1.20", "192.168.1.21"], runner=runner)
        self.assertTrue(ok)
        self.assertEqual(error, "")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][:5], [DEVICES.PFCTL, "-t", DEVICES.TABLE, "-T", "replace"])
        self.assertEqual(calls[0][5:], ["192.168.1.20", "192.168.1.21"])

    def test_flush_replaces_with_nothing(self):
        calls = []

        def runner(args):
            calls.append(args)
            return self.FakeResult()

        DEVICES.flush(runner=runner)
        self.assertEqual(calls[0], [DEVICES.PFCTL, "-t", DEVICES.TABLE, "-T", "replace"])

    def test_pfctl_failure_is_reported_not_raised(self):
        ok, error = DEVICES.apply_table(
            ["192.168.1.20"], runner=lambda args: self.FakeResult(1, "no such table"))
        self.assertFalse(ok)
        self.assertIn("no such table", error)


if __name__ == "__main__":
    unittest.main()
