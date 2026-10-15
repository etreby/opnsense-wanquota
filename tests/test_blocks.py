"""Manual internet blocks: who gets blocked, who can never be, and what expires.

This is the bluntest thing the plugin can do to a device, so every refusal is
tested by name and pf is never invoked. Expiry is tested separately from refusal
because the two mean different things to the caller: an expired block did its job,
a refused one did not happen.
"""

import importlib.util
from pathlib import Path
import sys
import unittest

SOURCE_DIR = Path(__file__).parents[1] / "src/opnsense/scripts/OPNsense/WanQuota"
sys.path.insert(0, str(SOURCE_DIR))
SPEC = importlib.util.spec_from_file_location("wanquota_blocks", SOURCE_DIR / "blocks.py")
BLOCKS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BLOCKS)

ROUTER = "192.168.1.1"
NOW = 1_800_000_000

KNOWN = [
    {"address": "192.168.1.1", "name": "OPNsense", "mac": "00:11:22:33:44:55", "hostname": "opnsense"},
    {"address": "192.168.1.20", "name": "Laptop", "mac": "aa:bb:cc:dd:ee:ff", "hostname": "laptop"},
    {"address": "192.168.1.30", "name": "Tablet", "mac": "11:22:33:44:55:66", "hostname": "tablet"},
]


class MembershipTests(unittest.TestCase):
    def members(self, blocks, policies=(), groups=(), known=KNOWN):
        index = BLOCKS.intelligence.policy_index(list(policies))
        return BLOCKS.members(blocks, known, index, list(groups), ROUTER, now=NOW)

    def test_an_address_is_blocked(self):
        chosen, skipped, expired = self.members([{"device": "192.168.1.20"}])
        self.assertEqual([item["device"] for item in chosen], ["192.168.1.20"])
        self.assertEqual((skipped, expired), ([], []))

    def test_a_mac_resolves_to_the_current_address(self):
        chosen, _, _ = self.members([{"device": "aa:bb:cc:dd:ee:ff"}])
        self.assertEqual(chosen[0]["device"], "192.168.1.20")
        self.assertEqual(chosen[0]["matched"], "aa:bb:cc:dd:ee:ff")

    def test_a_hostname_resolves_too(self):
        chosen, _, _ = self.members([{"device": "tablet"}])
        self.assertEqual(chosen[0]["device"], "192.168.1.30")

    def test_the_reason_is_carried_through(self):
        chosen, _, _ = self.members([{"device": "laptop", "reason": "homework"}])
        self.assertEqual(chosen[0]["reason"], "homework")

    def test_the_firewall_itself_is_never_blocked(self):
        chosen, skipped, _ = self.members([{"device": "192.168.1.1"}])
        self.assertEqual(chosen, [])
        self.assertIn("firewall itself", skipped[0]["reason"])

    def test_the_firewall_is_refused_even_when_it_is_not_in_the_device_list(self):
        """The real situation: the device list comes from DHCP leases and ARP, and the
        firewall is in neither. A check that ran only on a matched row refused it with
        "no device matches" — true, and reading like a typo rather than a guarantee."""
        chosen, skipped, _ = BLOCKS.members(
            [{"device": ROUTER}], KNOWN[1:], {}, [], ROUTER, now=NOW)
        self.assertEqual(chosen, [])
        self.assertIn("firewall itself", skipped[0]["reason"])

    def test_the_firewall_is_refused_by_mac_as_well(self):
        """A refusal that only recognises the address is a refusal with a way round it."""
        chosen, skipped, _ = self.members([{"device": "00:11:22:33:44:55"}])
        self.assertEqual(chosen, [])
        self.assertIn("firewall itself", skipped[0]["reason"])

    def test_an_excluded_device_is_never_blocked(self):
        chosen, skipped, _ = self.members(
            [{"device": "192.168.1.20"}],
            policies=[{"address": "192.168.1.20", "exclude": True}])
        self.assertEqual(chosen, [])
        self.assertEqual(skipped[0]["reason"], "excluded by policy")

    def test_a_protected_group_member_is_never_blocked(self):
        chosen, skipped, _ = self.members(
            [{"device": "192.168.1.20"}],
            groups=[{"name": "Protected Infrastructure", "members": ["192.168.1.0/24"]}])
        self.assertEqual(chosen, [])
        self.assertIn("protected group", skipped[0]["reason"])

    def test_an_unknown_device_is_refused_with_a_reason(self):
        chosen, skipped, _ = self.members([{"device": "192.168.9.9"}])
        self.assertEqual(chosen, [])
        self.assertIn("no device on the network matches", skipped[0]["reason"])

    def test_an_unnamed_entry_is_refused(self):
        chosen, skipped, _ = self.members([{"device": "  "}])
        self.assertEqual(chosen, [])
        self.assertEqual(skipped[0]["device"], "(unnamed)")

    def test_one_device_named_twice_is_blocked_once(self):
        chosen, skipped, _ = self.members(
            [{"device": "192.168.1.20"}, {"device": "aa:bb:cc:dd:ee:ff"}])
        self.assertEqual(len(chosen), 1)
        self.assertIn("already blocked", skipped[0]["reason"])


class ExpiryTests(unittest.TestCase):
    def members(self, blocks):
        return BLOCKS.members(blocks, KNOWN, {}, [], ROUTER, now=NOW)

    def test_zero_means_indefinite(self):
        chosen, _, expired = self.members([{"device": "192.168.1.20", "until": 0}])
        self.assertEqual(len(chosen), 1)
        self.assertEqual(expired, [])

    def test_a_future_deadline_still_blocks(self):
        chosen, _, expired = self.members([{"device": "192.168.1.20", "until": NOW + 3600}])
        self.assertEqual(len(chosen), 1)
        self.assertEqual(expired, [])

    def test_a_past_deadline_is_expired_not_refused(self):
        chosen, skipped, expired = self.members([{"device": "192.168.1.20", "until": NOW - 1}])
        self.assertEqual(chosen, [])
        self.assertEqual(skipped, [])
        self.assertEqual(expired[0]["device"], "192.168.1.20")

    def test_the_deadline_is_inclusive_of_now(self):
        """A block whose deadline is this second has finished, not one second left."""
        chosen, _, expired = self.members([{"device": "192.168.1.20", "until": NOW}])
        self.assertEqual(chosen, [])
        self.assertEqual(len(expired), 1)

    def test_a_nonsense_deadline_is_refused_rather_than_ignored(self):
        chosen, skipped, expired = self.members([{"device": "192.168.1.20", "until": "soon"}])
        self.assertEqual((chosen, expired), ([], []))
        self.assertIn("Unix timestamp", skipped[0]["reason"])


class TableTests(unittest.TestCase):
    """pfctl reports success on stderr, so only the exit status may mean failure."""

    class Result:
        def __init__(self, returncode, stderr, stdout=""):
            self.returncode = returncode
            self.stderr = stderr
            self.stdout = stdout

    def test_a_success_message_on_stderr_is_not_an_error(self):
        ok, error, detail, _ = BLOCKS.apply_table(
            ["192.168.1.20"], runner=lambda args: self.Result(0, "1 addresses added."))
        self.assertTrue(ok)
        self.assertEqual(error, "")
        self.assertEqual(detail, "1 addresses added.")

    def test_a_failure_is_reported(self):
        ok, error, _, _ = BLOCKS.apply_table(
            ["192.168.1.20"], runner=lambda args: self.Result(1, "no such table"))
        self.assertFalse(ok)
        self.assertEqual(error, "no such table")

    def test_flush_replaces_with_nothing(self):
        calls = []

        def runner(args):
            calls.append(args)
            return self.Result(0, "")

        BLOCKS.flush(runner=runner)
        replace = [c for c in calls if "replace" in c][0]
        self.assertEqual(replace[-1], "replace")
        self.assertEqual(replace[2], BLOCKS.TABLE)

    def test_flush_kills_nothing(self):
        """Releasing a device should let its traffic resume, not tear anything down."""
        calls = []
        BLOCKS.flush(runner=lambda args: (calls.append(args), self.Result(0, ""))[1])
        self.assertEqual([c for c in calls if "-k" in c], [])


class StateKillTests(unittest.TestCase):
    """A rule only governs new connections; open states are what make a block look
    like it did nothing. Measured: an ESP32 on one long-lived session to its vendor's
    cloud kept using it while the block rule sat at 0 packets after 23,000
    evaluations."""

    class Result:
        def __init__(self, returncode=0, stderr="", stdout=""):
            self.returncode = returncode
            self.stderr = stderr
            self.stdout = stdout

    def run_with(self, existing):
        calls = []

        def runner(args):
            calls.append(args)
            if "show" in args:
                return self.Result(stdout="\n".join("   " + a for a in existing))
            return self.Result()

        return calls, runner

    def test_a_newly_blocked_device_has_its_states_killed(self):
        calls, runner = self.run_with([])
        BLOCKS.apply_table(["192.168.1.128"], runner=runner)
        self.assertIn(["/sbin/pfctl", "-k", "192.168.1.128"],
                      [c for c in calls if "-k" in c])

    def test_a_device_already_blocked_is_not_killed_again(self):
        """Killing every run would reset the device's permitted local connections
        every five minutes for as long as the block lasted."""
        calls, runner = self.run_with(["192.168.1.128"])
        BLOCKS.apply_table(["192.168.1.128"], runner=runner)
        self.assertEqual([c for c in calls if "-k" in c], [])

    def test_only_the_new_address_is_killed(self):
        calls, runner = self.run_with(["192.168.1.20"])
        BLOCKS.apply_table(["192.168.1.20", "192.168.1.128"], runner=runner)
        killed = [c[-1] for c in calls if "-k" in c]
        self.assertEqual(killed, ["192.168.1.128"])

    def test_a_failed_replace_kills_nothing(self):
        calls = []

        def runner(args):
            calls.append(args)
            if "show" in args:
                return self.Result(stdout="")
            return self.Result(returncode=1, stderr="no such table")

        BLOCKS.apply_table(["192.168.1.128"], runner=runner)
        self.assertEqual([c for c in calls if "-k" in c], [])


class ServiceBlockTests(unittest.TestCase):
    CATALOG = {
        "playstation": {
            "label": "PlayStation",
            "suffixes": ("playstation.net", "playstation.com", "gaikai.com"),
        },
        "xbox": {
            "label": "Xbox",
            "suffixes": ("xboxlive.com", "xbox.com"),
        },
    }

    def test_playstation_service_is_blocked(self):
        resolver = lambda name: ["198.51.100.10"] if "playstation" in name else []
        chosen, skipped, expired, addrs = BLOCKS.service_members(
            [{"service": "playstation", "reason": "Parental control"}],
            catalog=self.CATALOG, mappings=[], now=NOW, resolver=resolver)
        self.assertEqual(len(chosen), 1)
        self.assertEqual(chosen[0]["service"], "playstation")
        self.assertEqual(chosen[0]["label"], "PlayStation")
        self.assertEqual(chosen[0]["reason"], "Parental control")
        self.assertEqual(skipped, [])
        self.assertEqual(expired, [])
        self.assertIn("198.51.100.10", addrs)

    def test_unknown_service_is_skipped(self):
        chosen, skipped, expired, addrs = BLOCKS.service_members(
            [{"service": "unknown_app"}],
            catalog=self.CATALOG, mappings=[], now=NOW)
        self.assertEqual(chosen, [])
        self.assertEqual(len(skipped), 1)
        self.assertIn("unknown service", skipped[0]["reason"])

    def test_expired_service_is_reported_for_pruning(self):
        chosen, skipped, expired, addrs = BLOCKS.service_members(
            [{"service": "playstation", "until": NOW - 100}],
            catalog=self.CATALOG, mappings=[], now=NOW)
        self.assertEqual(chosen, [])
        self.assertEqual(skipped, [])
        self.assertEqual(len(expired), 1)
        self.assertEqual(expired[0]["service"], "playstation")

    def test_service_table_replace_and_state_killing(self):
        calls = []

        def runner(args):
            calls.append(args)
            if "show" in args:
                return TableTests.Result(0, "", stdout="198.51.100.5\n")
            return TableTests.Result(0, "")

        ok, error, detail, killed = BLOCKS.apply_table(
            ["198.51.100.5", "198.51.100.10"], table=BLOCKS.SERVICE_TABLE, runner=runner)
        self.assertTrue(ok)
        replace_call = [c for c in calls if "replace" in c][0]
        self.assertEqual(replace_call[2], BLOCKS.SERVICE_TABLE)
        self.assertIn("198.51.100.10", replace_call)
        # 198.51.100.10 was newly added, so its states were killed
        kill_call = [c for c in calls if "-k" in c]
        self.assertEqual(len(kill_call), 1)
        self.assertIn("198.51.100.10", kill_call[0])


if __name__ == "__main__":
    unittest.main()
