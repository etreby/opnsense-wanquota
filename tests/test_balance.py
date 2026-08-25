"""Renewal-aware WAN balance: the ratio, the floor, and who is excluded.

The balancer is the only feature that changes routing without anyone asking at the
moment it happens, so the arithmetic is tested directly and no gateway is touched.
"""

import importlib.util
from pathlib import Path
import sys
import unittest

SOURCE_DIR = Path(__file__).parents[1] / "src/opnsense/scripts/OPNsense/WanQuota"
sys.path.insert(0, str(SOURCE_DIR))
SPEC = importlib.util.spec_from_file_location("wanquota_balance", SOURCE_DIR / "balance.py")
BALANCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BALANCE)

GB = 1e9


def provider(name, interface, remaining_gb, days_left, percent=50.0, available=True):
    return {"name": name, "logical_interface": interface, "remaining": remaining_gb * GB,
            "days_left": days_left, "percent": percent, "available": available,
            "end": "2026-09-01"}


INVENTORY = {
    "gateways": [
        {"name": "ETISALAT_DHCP", "interface": "wan", "ipprotocol": "inet",
         "weight": 3, "disabled": "0", "configured": True},
        {"name": "MOBINIL_DHCP", "interface": "opt1", "ipprotocol": "inet",
         "weight": 1, "disabled": "0", "configured": True},
        {"name": "ETISALAT_DHCP6", "interface": "wan", "ipprotocol": "inet6",
         "weight": 1, "disabled": "0", "configured": False},
    ],
    "groups": [{"name": "DUAL_WAN", "members": ["ETISALAT_DHCP", "MOBINIL_DHCP"],
                "tiers": {"item": ["ETISALAT_DHCP", "MOBINIL_DHCP"]},
                "poolopts": "round-robin sticky-address"}],
}

CFG = {"reserve_gb": 0, "balance_max_weight": 10, "balance_group": ""}


class UrgencyTests(unittest.TestCase):
    def test_urgency_is_headroom_per_remaining_day(self):
        self.assertAlmostEqual(
            BALANCE.urgency(provider("A", "wan", 60, 2)), 30 * GB)

    def test_the_reserve_is_held_back(self):
        """The balancer must not spend the buffer the guardrails depend on."""
        self.assertAlmostEqual(
            BALANCE.urgency(provider("A", "wan", 60, 2), 10 * GB), 25 * GB)

    def test_a_reserve_larger_than_the_remainder_scores_zero(self):
        self.assertEqual(BALANCE.urgency(provider("A", "wan", 5, 2), 10 * GB), 0)

    def test_an_exhausted_provider_scores_zero(self):
        self.assertEqual(BALANCE.urgency(provider("A", "wan", 0, 5)), 0)

    def test_the_last_day_of_a_cycle_does_not_divide_by_zero(self):
        self.assertAlmostEqual(BALANCE.urgency(provider("A", "wan", 20, 0)), 20 * GB)


class WeightTests(unittest.TestCase):
    def weights(self, rows, max_weight=10):
        return [row["weight"] for row in BALANCE.weights(rows, max_weight)]

    def test_the_most_urgent_provider_gets_the_ceiling(self):
        self.assertEqual(
            self.weights([{"urgency": 30 * GB}, {"urgency": 15 * GB}]), [10, 5])

    def test_equal_urgency_gives_equal_weights(self):
        self.assertEqual(
            self.weights([{"urgency": 10 * GB}, {"urgency": 10 * GB}]), [10, 10])

    def test_a_link_is_never_starved(self):
        """A weight of zero would be the balancer taking a link out of service, which
        is the guardrail's decision and not its own."""
        self.assertEqual(self.weights([{"urgency": 100 * GB}, {"urgency": 1}]), [10, 1])

    def test_all_zero_returns_to_equal_sharing(self):
        self.assertEqual(self.weights([{"urgency": 0}, {"urgency": 0}]), [1, 1])

    def test_the_ceiling_softens_the_ratio(self):
        self.assertEqual(
            self.weights([{"urgency": 30 * GB}, {"urgency": 15 * GB}], max_weight=4), [4, 2])

    def test_the_ceiling_is_clamped_to_what_the_model_allows(self):
        self.assertEqual(self.weights([{"urgency": 1}], max_weight=99), [10])
        self.assertEqual(self.weights([{"urgency": 1}], max_weight=0), [10])

    def test_an_excluded_provider_holds_weight_one(self):
        rows = BALANCE.weights([{"urgency": 30 * GB, "excluded": True},
                                {"urgency": 15 * GB}])
        self.assertEqual([row["weight"] for row in rows], [1, 10])

    def test_an_excluded_provider_does_not_set_the_ceiling(self):
        """Otherwise a cut-off link with a huge remainder would flatten everyone else
        to weight 1 while carrying nothing itself."""
        rows = BALANCE.weights([{"urgency": 1000 * GB, "excluded": True},
                                {"urgency": 30 * GB}, {"urgency": 15 * GB}])
        self.assertEqual([row["weight"] for row in rows], [1, 10, 5])


class GatewayMatchTests(unittest.TestCase):
    def test_matched_on_interface_and_protocol(self):
        gateway = BALANCE.gateway_for("wan", INVENTORY["gateways"])
        self.assertEqual(gateway["name"], "ETISALAT_DHCP")

    def test_the_ipv6_gateway_on_the_same_interface_is_not_chosen(self):
        gateway = BALANCE.gateway_for("wan", INVENTORY["gateways"], protocol="inet6")
        self.assertEqual(gateway["name"], "ETISALAT_DHCP6")

    def test_a_disabled_gateway_is_not_chosen(self):
        gateways = [{"name": "OFF", "interface": "wan", "ipprotocol": "inet", "disabled": "1"},
                    {"name": "ON", "interface": "wan", "ipprotocol": "inet", "disabled": "0"}]
        self.assertEqual(BALANCE.gateway_for("wan", gateways)["name"], "ON")

    def test_an_interface_with_no_gateway_returns_nothing(self):
        self.assertIsNone(BALANCE.gateway_for("opt7", INVENTORY["gateways"]))


class PlanTests(unittest.TestCase):
    def build(self, providers, cfg=None, inventory=None, decisions=None):
        return BALANCE.build(providers, {**CFG, **(cfg or {})},
                             inventory or INVENTORY, decisions)

    def test_the_provider_closer_to_renewal_is_favoured(self):
        plan = self.build([provider("ETISALAT", "wan", 60, 2),
                           provider("MOBINIL", "opt1", 250, 16)])
        weights = {row["name"]: row["weight"] for row in plan["providers"]}
        self.assertGreater(weights["ETISALAT"], weights["MOBINIL"])

    def test_changes_name_the_gateway_and_both_weights(self):
        plan = self.build([provider("ETISALAT", "wan", 60, 2),
                           provider("MOBINIL", "opt1", 250, 16)])
        change = next(item for item in plan["changes"] if item["gateway"] == "ETISALAT_DHCP")
        self.assertEqual((change["from"], change["to"]), (3, 10))

    def test_a_plan_matching_the_current_weights_proposes_no_change(self):
        """The hysteresis: without this a five-minute cron would rewrite the
        configuration 288 times a day for a ratio that had not moved."""
        inventory = {**INVENTORY, "gateways": [
            {**INVENTORY["gateways"][0], "weight": 10},
            {**INVENTORY["gateways"][1], "weight": 5},
            INVENTORY["gateways"][2]]}
        plan = self.build([provider("ETISALAT", "wan", 60, 2),
                           provider("MOBINIL", "opt1", 240, 16)], inventory=inventory)
        self.assertEqual(plan["changes"], [])

    def test_a_cut_off_provider_is_excluded_and_says_why(self):
        plan = self.build(
            [provider("ETISALAT", "wan", 60, 2), provider("MOBINIL", "opt1", 250, 16)],
            decisions={"ETISALAT": {"applied": "cutoff", "recommended": "cutoff"}})
        etisalat = next(row for row in plan["providers"] if row["name"] == "ETISALAT")
        self.assertTrue(etisalat["excluded"])
        self.assertEqual(etisalat["weight"], 1)
        self.assertIn("overuse takes precedence", etisalat["excluded_reason"])

    def test_a_deprioritized_provider_is_still_balanced(self):
        """Deprioritize is the guardrail asking for less, not for none, and the
        balancer's weights are how less is expressed."""
        plan = self.build(
            [provider("ETISALAT", "wan", 60, 2), provider("MOBINIL", "opt1", 250, 16)],
            decisions={"ETISALAT": {"applied": "deprioritize", "recommended": "deprioritize"}})
        etisalat = next(row for row in plan["providers"] if row["name"] == "ETISALAT")
        self.assertFalse(etisalat["excluded"])

    def test_an_unavailable_provider_is_left_out_entirely(self):
        plan = self.build([provider("ETISALAT", "wan", 60, 2, available=False),
                           provider("MOBINIL", "opt1", 250, 16)])
        self.assertEqual([row["name"] for row in plan["providers"]], ["MOBINIL"])

    def test_no_gateway_group_is_a_problem_not_a_silent_no_op(self):
        plan = self.build([provider("ETISALAT", "wan", 60, 2)],
                          inventory={**INVENTORY, "groups": []})
        self.assertTrue(any("no gateway group" in item for item in plan["problems"]))

    def test_several_groups_need_one_naming_which(self):
        inventory = {**INVENTORY, "groups": INVENTORY["groups"] + [
            {"name": "BACKUP_WAN", "members": ["MOBINIL_DHCP"], "tiers": {}}]}
        plan = self.build([provider("ETISALAT", "wan", 60, 2)], inventory=inventory)
        self.assertTrue(any("more than one gateway group" in item for item in plan["problems"]))

    def test_naming_the_group_resolves_that(self):
        inventory = {**INVENTORY, "groups": INVENTORY["groups"] + [
            {"name": "BACKUP_WAN", "members": ["MOBINIL_DHCP"], "tiers": {}}]}
        plan = self.build([provider("ETISALAT", "wan", 60, 2),
                           provider("MOBINIL", "opt1", 250, 16)],
                          cfg={"balance_group": "DUAL_WAN"}, inventory=inventory)
        self.assertEqual(plan["problems"], [])
        self.assertEqual(plan["group"], "DUAL_WAN")

    def test_a_provider_with_no_gateway_is_reported(self):
        plan = self.build([provider("SPARE", "opt5", 60, 2)])
        self.assertTrue(any("no gateway uses opt5" in item for item in plan["problems"]))

    def test_a_gateway_outside_the_group_is_reported(self):
        inventory = {**INVENTORY,
                     "groups": [{"name": "DUAL_WAN", "members": ["ETISALAT_DHCP"],
                                 "tiers": {}}]}
        plan = self.build([provider("ETISALAT", "wan", 60, 2),
                           provider("MOBINIL", "opt1", 250, 16)], inventory=inventory)
        self.assertTrue(any("not a member of DUAL_WAN" in item for item in plan["problems"]))


if __name__ == "__main__":
    unittest.main()
