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


class DrainDecisionTests(unittest.TestCase):
    """When sharing itself is what wastes the allowance.

    Drain concentrates all traffic on one provider. That is a bigger act than
    changing a ratio, so the condition is tested from both sides: it must engage
    when sharing guarantees waste, and must stand down in every case where it
    could do harm.
    """

    def row(self, name, urgency_gb, excluded=False, gateway="GW", online=True):
        return {"name": name, "urgency": urgency_gb * GB, "excluded": excluded,
                "gateway": gateway, "online": online}

    def test_household_rate_is_the_sum_across_providers(self):
        """Traffic moved to another link is the same traffic, so what a link could
        absorb is compared against total demand, not the demand it already sees."""
        self.assertAlmostEqual(
            BALANCE.household_rate([{"daily_average": 2.27 * GB},
                                    {"daily_average": 15.18 * GB}]),
            17.45 * GB)

    def test_a_negative_average_does_not_reduce_demand(self):
        self.assertAlmostEqual(
            BALANCE.household_rate([{"daily_average": -5 * GB},
                                    {"daily_average": 10 * GB}]), 10 * GB)

    def test_engages_when_all_the_traffic_still_cannot_exhaust_the_link(self):
        """The measured case: ETISALAT could spend 17.6 GB/day, the household uses
        17.4, so any share smaller than all of it leaves allowance to expire."""
        decision = BALANCE.drain_decision(
            [self.row("ETISALAT", 17.6, gateway="ETISALAT_DHCP"),
             self.row("MOBINIL", 10.9, gateway="MOBINIL_DHCP")], 17.4 * GB)
        self.assertTrue(decision["engaged"])
        self.assertEqual(decision["target"], "ETISALAT")
        self.assertIn("will not exhaust it before renewal", decision["reason"])

    def test_stands_down_when_a_share_is_enough_to_fill_it(self):
        """After a renewal the allowance resets and the per-day figure collapses, so
        this is also how drain releases itself with nothing scheduled."""
        decision = BALANCE.drain_decision(
            [self.row("ETISALAT", 7.3, gateway="ETISALAT_DHCP"),
             self.row("MOBINIL", 13.0, gateway="MOBINIL_DHCP")], 17.4 * GB)
        self.assertFalse(decision["engaged"])
        self.assertIsNone(decision["target"])
        self.assertIn("a share of the traffic is enough", decision["reason"])

    def test_the_release_band_stops_it_flapping_at_the_boundary(self):
        """Sitting exactly at the household rate would otherwise engage and release on
        alternating runs, rewriting the gateway group every five minutes."""
        rows = [self.row("A", 15.7, gateway="A_GW"), self.row("B", 9.0, gateway="B_GW")]
        # Below the engage threshold, so a fresh decision says no...
        self.assertFalse(BALANCE.drain_decision(rows, 16 * GB, draining=False)["engaged"])
        # ...but once engaged it holds until it falls clearly below.
        self.assertTrue(BALANCE.drain_decision(rows, 16 * GB, draining=True)["engaged"])

    def test_never_engages_while_the_guardrail_is_acting(self):
        """Overuse beats underuse, and the guardrail owns tiers while it acts."""
        decision = BALANCE.drain_decision(
            [self.row("ETISALAT", 40, gateway="ETISALAT_DHCP"),
             self.row("MOBINIL", 5, excluded=True, gateway="MOBINIL_DHCP")], 10 * GB)
        self.assertFalse(decision["engaged"])
        self.assertIn("the guardrail is acting on MOBINIL", decision["reason"])

    def test_never_promotes_a_link_that_is_down(self):
        decision = BALANCE.drain_decision(
            [self.row("ETISALAT", 40, gateway="ETISALAT_DHCP", online=False),
             self.row("MOBINIL", 5, gateway="MOBINIL_DHCP")], 10 * GB)
        # MOBINIL is the only usable link, so there is nothing to concentrate onto.
        self.assertFalse(decision["engaged"])
        self.assertIn("fewer than two usable providers", decision["reason"])

    def test_a_single_provider_is_never_drained(self):
        decision = BALANCE.drain_decision([self.row("ONLY", 99, gateway="GW")], 1 * GB)
        self.assertFalse(decision["engaged"])
        self.assertIn("nothing to concentrate", decision["reason"])

    def test_no_measured_traffic_means_no_decision(self):
        """With no demand figure, every allowance looks infinitely under-spent."""
        decision = BALANCE.drain_decision(
            [self.row("A", 20, gateway="A_GW"), self.row("B", 10, gateway="B_GW")], 0)
        self.assertFalse(decision["engaged"])
        self.assertIn("no measured household traffic", decision["reason"])

    def test_a_provider_with_no_gateway_cannot_be_the_target(self):
        decision = BALANCE.drain_decision(
            [self.row("SPARE", 99, gateway=""), self.row("A", 20, gateway="A_GW"),
             self.row("B", 10, gateway="B_GW")], 15 * GB)
        self.assertEqual(decision["target"], "A")


class TierPlanTests(unittest.TestCase):
    GROUP = {"name": "DUAL_WAN", "members": ["ETISALAT_DHCP", "MOBINIL_DHCP"],
             "tiers": {"item": ["ETISALAT_DHCP", "MOBINIL_DHCP"], "item2": []}}

    def rows(self):
        return [{"name": "ETISALAT", "gateway": "ETISALAT_DHCP"},
                {"name": "MOBINIL", "gateway": "MOBINIL_DHCP"}]

    def test_the_target_goes_first_and_the_rest_become_failover(self):
        plan = BALANCE.tier_plan(self.rows(), {"engaged": True, "target": "ETISALAT"},
                                 self.GROUP)
        self.assertEqual(plan["wanted"],
                         {"ETISALAT_DHCP": "item", "MOBINIL_DHCP": "item2"})
        self.assertEqual([m["gateway"] for m in plan["moves"]], ["MOBINIL_DHCP"])

    def test_not_engaged_proposes_nothing(self):
        plan = BALANCE.tier_plan(self.rows(), {"engaged": False, "target": None},
                                 self.GROUP)
        self.assertEqual(plan["wanted"], {})
        self.assertEqual(plan["moves"], [])

    def test_an_already_drained_group_proposes_no_move(self):
        """The hysteresis: recomputing the same answer must not rewrite the group."""
        group = {**self.GROUP,
                 "tiers": {"item": ["ETISALAT_DHCP"], "item2": ["MOBINIL_DHCP"]}}
        plan = BALANCE.tier_plan(self.rows(), {"engaged": True, "target": "ETISALAT"},
                                 group)
        self.assertEqual(plan["moves"], [])

    def test_a_gateway_outside_the_group_is_left_alone(self):
        plan = BALANCE.tier_plan(
            self.rows() + [{"name": "OTHER", "gateway": "SOMEWHERE_ELSE"}],
            {"engaged": True, "target": "ETISALAT"}, self.GROUP)
        self.assertNotIn("SOMEWHERE_ELSE", plan["wanted"])


class ReleaseTests(unittest.TestCase):
    """Letting go has to undo a change, not merely stop asking for one.

    The first implementation only stopped proposing a tier move when the drain
    condition lapsed, so a drain that engaged before a cycle renewal stayed engaged
    after it — the decision flipped, the plan proposed nothing, and the group
    remained concentrated on one link indefinitely.
    """

    def test_release_is_needed_when_drained_and_no_longer_engaged(self):
        self.assertTrue(BALANCE.release_needed({"engaged": False}, {"drained": True}))

    def test_no_release_while_still_engaged(self):
        self.assertFalse(BALANCE.release_needed({"engaged": True}, {"drained": True}))

    def test_no_release_when_nothing_was_ever_drained(self):
        self.assertFalse(BALANCE.release_needed({"engaged": False}, {"drained": False}))

    def test_leaving_drain_mode_releases_what_it_moved(self):
        """Turning the mode off must not leave the tiers it changed behind."""
        plan = BALANCE.build(
            [provider("ETISALAT", "wan", 60, 2), provider("MOBINIL", "opt1", 250, 16)],
            {**CFG, "balance_mode": "weights"},
            {**INVENTORY, "drained": True})
        self.assertTrue(plan["tiers"]["release"])
