"""Upload shaping through ipfw's layer2 hook.

Every rule here is raw ipfw outside the shaper model, and layer2 filtering is a
global switch, so the ordering and the failure paths matter more than usual: getting
them wrong means either an upload cap that silently does nothing or a firewall that
drops frame types it used to pass.
"""

import importlib.util
from pathlib import Path
import sys
import unittest

SOURCE_DIR = Path(__file__).parents[1] / "src/opnsense/scripts/OPNsense/WanQuota"
sys.path.insert(0, str(SOURCE_DIR))
SPEC = importlib.util.spec_from_file_location("wanquota_layer2", SOURCE_DIR / "layer2.py")
LAYER2 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LAYER2)


def recorder(fail_on=None):
    """A fake ipfw that records what it was asked to do."""
    calls = []

    def runner(command):
        calls.append(command)
        if fail_on and any(token in command for token in fail_on):
            return 1, "refused"
        return 0, ""

    return calls, runner


PLAN = {
    "status": "ok",
    "dry_run": False,
    "device_pipes": [
        {"device": "192.168.1.32", "name": "Desktop", "upload_pipe": 22500,
         "upload_layer2": True, "pipe": 22000},
        {"device": "192.168.1.40", "name": "TV", "upload_pipe": None,
         "upload_layer2": False, "pipe": 22001},
    ],
}


class DesiredRuleTests(unittest.TestCase):
    def test_only_devices_needing_the_layer2_path_get_a_rule(self):
        rules = LAYER2.desired_rules(PLAN)
        self.assertEqual([r["device"] for r in rules], ["192.168.1.32"])

    def test_the_rule_targets_the_pipe_the_shaper_created(self):
        rule = LAYER2.desired_rules(PLAN)[0]
        self.assertEqual(rule["pipe"], 22500)
        self.assertIn("layer2", rule["spec"])
        self.assertEqual(rule["spec"][:3], ["pipe", "22500", "ip"])

    def test_rules_sit_below_the_system_layer2_rules(self):
        """The stock set starts at 110 and denies at 150; above that we are never reached."""
        for rule in LAYER2.desired_rules(PLAN):
            self.assertLess(rule["number"], 110)
            self.assertGreaterEqual(rule["number"], LAYER2.RULE_FIRST)

    def test_a_plan_with_nothing_to_do_asks_for_no_rules(self):
        self.assertEqual(LAYER2.desired_rules({"device_pipes": []}), [])
        self.assertEqual(LAYER2.desired_rules(None), [])

    def test_room_runs_out_rather_than_colliding_with_the_stock_rules(self):
        many = {"device_pipes": [
            {"device": f"192.168.1.{n}", "upload_pipe": 22500 + n, "upload_layer2": True}
            for n in range(1, 30)]}
        rules = LAYER2.desired_rules(many)
        self.assertTrue(all(r["number"] < LAYER2.SAFETY_RULE for r in rules))


class ApplyTests(unittest.TestCase):
    def test_the_switch_is_enabled_only_after_the_permit_rule_exists(self):
        """Otherwise there is a window where the stock deny could drop a frame."""
        calls, runner = recorder()
        LAYER2.apply_rules(PLAN, runner)
        joined = [" ".join(call) for call in calls]
        permit = next(i for i, c in enumerate(joined) if "allow ip from any to any layer2" in c)
        switch = next(i for i, c in enumerate(joined) if "net.link.ether.ipfw=1" in c)
        self.assertLess(permit, switch)

    def test_the_permit_rule_is_numbered_after_the_pipe_rules(self):
        """A permit ahead of a pipe rule would end layer2 processing before it matched."""
        rules = LAYER2.desired_rules(PLAN)
        self.assertTrue(all(r["number"] < LAYER2.SAFETY_RULE for r in rules))

    def test_existing_rules_are_cleared_first_so_applying_twice_is_safe(self):
        calls, runner = recorder()
        LAYER2.apply_rules(PLAN, runner)
        deletes = [c for c in calls if "delete" in c]
        self.assertTrue(deletes, "the range must be cleared before installing")

    def test_a_failed_permit_rule_refuses_to_enable_the_switch(self):
        calls, runner = recorder(fail_on=["allow"])
        result = LAYER2.apply_rules(PLAN, runner)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["enabled"])
        joined = [" ".join(call) for call in calls]
        self.assertFalse(any("net.link.ether.ipfw=1" in c for c in joined),
                         "layer2 filtering must never be enabled without the permit rule")
        self.assertTrue(any("net.link.ether.ipfw=0" in c for c in joined),
                        "and the switch must be left off")

    def test_an_empty_plan_removes_everything_and_turns_the_switch_off(self):
        calls, runner = recorder()
        result = LAYER2.apply_rules({"device_pipes": []}, runner)
        self.assertFalse(result["enabled"])
        joined = [" ".join(call) for call in calls]
        self.assertTrue(any("net.link.ether.ipfw=0" in c for c in joined))

    def test_only_this_modules_rule_numbers_are_ever_deleted(self):
        calls, runner = recorder()
        LAYER2.apply_rules(PLAN, runner)
        for call in calls:
            if "delete" in call:
                number = int(call[call.index("delete") + 1])
                self.assertTrue(LAYER2.RULE_FIRST <= number <= LAYER2.RULE_LAST, number)


class SyncTests(unittest.TestCase):
    LISTING_OK = ("00090 0 0 pipe 22500 ip from 192.168.1.32 to any layer2\n"
                  "00099 0 0 allow ip from any to any layer2\n")
    LISTING_GONE = "65533 0 0 allow ip from any to any\n"

    def test_a_healthy_set_is_left_alone(self):
        calls, runner = recorder()
        original = LAYER2._listing
        LAYER2._listing = lambda runner=None: self.LISTING_OK
        try:
            result = LAYER2.sync(PLAN, runner)
        finally:
            LAYER2._listing = original
        self.assertEqual(result["action"], "none")
        self.assertEqual(calls, [], "a healthy set must not be touched")

    def test_rules_removed_by_an_ipfw_reload_are_reinstalled(self):
        calls, runner = recorder()
        original = LAYER2._listing
        LAYER2._listing = lambda runner=None: self.LISTING_GONE
        try:
            result = LAYER2.sync(PLAN, runner)
        finally:
            LAYER2._listing = original
        self.assertEqual(result["action"], "installed")
        self.assertTrue(any("add" in call for call in calls))

    def test_a_dry_run_plan_installs_nothing(self):
        calls, runner = recorder()
        original = LAYER2._listing
        LAYER2._listing = lambda runner=None: self.LISTING_GONE
        try:
            plan = dict(PLAN, dry_run=True)
            result = LAYER2.sync(plan, runner)
        finally:
            LAYER2._listing = original
        self.assertEqual(result["action"], "none")
        self.assertFalse(any("add" in call for call in calls))

    def test_a_disabled_plan_releases_what_is_installed(self):
        calls, runner = recorder()
        original = LAYER2._listing
        LAYER2._listing = lambda runner=None: self.LISTING_OK
        try:
            result = LAYER2.sync({"status": "disabled"}, runner)
        finally:
            LAYER2._listing = original
        self.assertEqual(result["action"], "removed")
        joined = [" ".join(call) for call in calls]
        self.assertTrue(any("net.link.ether.ipfw=0" in c for c in joined))

    def test_installed_rules_are_recognised_only_in_our_range(self):
        listing = ("00089 0 0 pipe 1 ip from any to any layer2\n"
                   "00090 0 0 pipe 22500 ip from 192.168.1.32 to any layer2\n"
                   "00150 0 0 deny layer2 not mac-type 0x0800\n")
        self.assertEqual(LAYER2.installed_rules(listing), [90])

    def test_an_unreadable_ipfw_does_not_raise_into_the_collector(self):
        def broken(command):
            return 1, "ipfw: not found"
        result = LAYER2.sync({"status": "disabled"}, broken)
        self.assertEqual(result["status"], "ok")


if __name__ == "__main__":
    unittest.main()


class SwitchReleaseTests(unittest.TestCase):
    """Turning the feature off must turn the global switch off.

    Found on a live firewall: after removing the last upload cap, the rules were gone
    but net.link.ether.ipfw was still 1. An ipfw reload had already flushed the rules,
    so sync saw none present and returned without touching the switch — leaving layer2
    filtering enabled with no permit rule, which makes the system's stock layer2 deny
    reachable for every frame. That is the exact state the install ordering exists to
    prevent, reached by the release path instead.
    """

    def runner_with_switch(self, value, listing=""):
        calls = []

        def runner(command):
            calls.append(command)
            if command[:2] == ["/sbin/sysctl", "-n"]:
                return 0, f"{value}\n"
            if command[:3] == ["/sbin/ipfw", "-a", "list"]:
                return 0, listing
            return 0, ""

        return calls, runner

    def test_the_switch_is_turned_off_even_when_no_rules_remain(self):
        calls, runner = self.runner_with_switch("1")
        original = LAYER2._listing
        LAYER2._listing = lambda runner=None: ""
        try:
            result = LAYER2.sync({"status": "disabled"}, runner)
        finally:
            LAYER2._listing = original
        self.assertEqual(result["action"], "removed")
        joined = [" ".join(call) for call in calls]
        self.assertTrue(any("net.link.ether.ipfw=0" in c for c in joined),
                        "a flushed rule set must not leave the switch on")

    def test_an_already_clean_firewall_is_left_untouched(self):
        calls, runner = self.runner_with_switch("0")
        original = LAYER2._listing
        LAYER2._listing = lambda runner=None: ""
        try:
            result = LAYER2.sync({"status": "disabled"}, runner)
        finally:
            LAYER2._listing = original
        self.assertEqual(result["action"], "none")
        self.assertFalse(any("delete" in call for call in calls),
                         "nothing to do means no work every five minutes")

    def test_the_switch_state_is_read_not_assumed(self):
        _calls, runner = self.runner_with_switch("1")
        self.assertTrue(LAYER2.switch_enabled(runner))
        _calls, runner = self.runner_with_switch("0")
        self.assertFalse(LAYER2.switch_enabled(runner))

    def test_an_unreadable_sysctl_does_not_claim_it_is_on(self):
        def broken(command):
            return 1, "sysctl: unknown oid"
        self.assertFalse(LAYER2.switch_enabled(broken))
