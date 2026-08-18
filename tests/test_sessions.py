"""Live sessions parsed from the pf state table."""

import importlib.util
from pathlib import Path
import sys
import unittest

SOURCE_DIR = Path(__file__).parents[1] / "src/opnsense/scripts/OPNsense/WanQuota"
sys.path.insert(0, str(SOURCE_DIR))
SPEC = importlib.util.spec_from_file_location("wanquota_sessions", SOURCE_DIR / "sessions.py")
SESSIONS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SESSIONS)

# Real shapes taken from `pfctl -vv -ss` on a NAT'd multi-WAN firewall: each
# conversation appears twice, once per translation direction.
SAMPLE = """all tcp 108.138.199.108:443 <- 192.168.1.46:51200       ESTABLISHED:ESTABLISHED
   [2216516182 + 60416] wscale 9  [938825561 + 10485732] wscale 10
   age 01:06:55, expires in 23:59:42, 85:158 pkts, 6539:13489 bytes, rule 98
all tcp 172.16.0.56:2298 (192.168.1.46:51200) -> 108.138.199.108:443       ESTABLISHED:ESTABLISHED
   [938825561 + 10485732] wscale 10  [2216516182 + 60416] wscale 9
   age 01:06:55, expires in 23:59:42, 85:158 pkts, 6539:13489 bytes, rule 90
all udp 142.250.1.1:443 <- 192.168.1.32:60000       MULTIPLE:MULTIPLE
   age 00:00:30, expires in 00:00:20, 10:12 pkts, 1000:2000 bytes, rule 5
all icmp 172.16.1.100:59342 -> 1.1.1.1:8       0:0
   age 00:10:00, expires in 00:00:10, 1:1 pkts, 84:84 bytes, rule 3
all tcp 192.168.1.20:22 <- 192.168.1.99:40000       ESTABLISHED:ESTABLISHED
   age 00:05:00, expires in 23:00:00, 5:5 pkts, 500:500 bytes, rule 7
"""


class ParseTests(unittest.TestCase):
    def setUp(self):
        self.states = SESSIONS.parse_states(SAMPLE)

    def test_nat_duplicate_is_merged_not_counted_twice(self):
        pairs = [(s["device"], s["remote"], s["protocol"]) for s in self.states]
        self.assertEqual(pairs.count(("192.168.1.46", "108.138.199.108", "tcp")), 1)

    def test_internal_address_is_the_lan_side(self):
        state = next(s for s in self.states if s["remote"] == "108.138.199.108")
        self.assertEqual(state["device"], "192.168.1.46")
        self.assertEqual(state["device_port"], 51200)
        self.assertEqual(state["remote_port"], 443)

    def test_bytes_and_packets_are_summed_per_direction(self):
        state = next(s for s in self.states if s["remote"] == "108.138.199.108")
        self.assertEqual(state["bytes"], 6539 + 13489)
        self.assertEqual(state["packets"], 85 + 158)

    def test_age_is_seconds(self):
        state = next(s for s in self.states if s["remote"] == "108.138.199.108")
        self.assertEqual(state["age_seconds"], 1 * 3600 + 6 * 60 + 55)

    def test_udp_state_parsed(self):
        state = next(s for s in self.states if s["protocol"] == "udp")
        self.assertEqual(state["device"], "192.168.1.32")
        self.assertEqual(state["bytes"], 3000)

    def test_icmp_without_meaningful_ports_still_parses(self):
        self.assertTrue(any(s["protocol"] == "icmp" for s in self.states))

    def test_garbage_input_is_not_fatal(self):
        self.assertEqual(SESSIONS.parse_states("not a state table\n\n"), [])
        self.assertEqual(SESSIONS.parse_states(""), [])
        self.assertEqual(SESSIONS.parse_states(None), [])


class LocalSessionTests(unittest.TestCase):
    NETWORK = SESSIONS.ipaddress.ip_network("192.168.1.0/24")
    ROUTER = "192.168.1.1"

    def rows(self, **kw):
        return SESSIONS.local_sessions(
            SESSIONS.parse_states(SAMPLE), self.NETWORK, self.ROUTER,
            kw.get("names", {"192.168.1.46": "DESKTOP"}),
            kw.get("domains", {"108.138.199.108": "cdn.example"}),
            kw.get("limit", 500))

    def test_only_lan_originated_wan_sessions(self):
        devices = {r["device"] for r in self.rows()}
        self.assertEqual(devices, {"192.168.1.46", "192.168.1.32"})

    def test_router_own_traffic_is_excluded(self):
        self.assertNotIn(self.ROUTER, {r["device"] for r in self.rows()})

    def test_lan_to_lan_is_excluded(self):
        # 192.168.1.99 -> 192.168.1.20 never crossed the WAN.
        self.assertNotIn("192.168.1.99", {r["device"] for r in self.rows()})

    def test_names_and_domains_are_resolved(self):
        row = next(r for r in self.rows() if r["device"] == "192.168.1.46")
        self.assertEqual(row["name"], "DESKTOP")
        self.assertEqual(row["remote_domain"], "cdn.example")

    def test_unnamed_destination_is_still_listed(self):
        # The point of this view: a state exists whether or not DNS named it.
        row = next(r for r in self.rows() if r["device"] == "192.168.1.32")
        self.assertIsNone(row["remote_domain"])

    def test_service_label_comes_from_the_transport(self):
        row = next(r for r in self.rows() if r["device"] == "192.168.1.32")
        self.assertEqual(row["service"], "Quic UDP Connection")

    def test_ranked_by_bytes(self):
        totals = [r["bytes"] for r in self.rows()]
        self.assertEqual(totals, sorted(totals, reverse=True))

    def test_limit_is_respected(self):
        self.assertEqual(len(self.rows(limit=1)), 1)


class DocumentTests(unittest.TestCase):
    def test_pfctl_failure_is_reported_not_raised(self):
        def boom():
            raise OSError("pfctl missing")
        got = SESSIONS.document(runner=boom)
        self.assertEqual(got["status"], "failed")
        self.assertEqual(got["sessions"], [])
        self.assertIn("pfctl missing", got["error"])


if __name__ == "__main__":
    unittest.main()


class CapHintTests(unittest.TestCase):
    """A cap target the planner would refuse must not be offered as if it worked.

    Offering it is worse than offering nothing: the reader only finds out after choosing
    a service and applying, and a shared CDN would throttle unrelated traffic.
    """

    CATALOG = {
        "netflix": {"label": "Netflix", "suffixes": ("nflxvideo.net", "nflxso.net")},
        "youtube": {"label": "YouTube", "suffixes": ("googlevideo.com",),
                    "co_delivery": ("gvt1.com",)},
    }

    def owners(self):
        return SESSIONS.cap_targets(self.CATALOG)

    def test_a_new_domain_can_be_capped(self):
        hint = SESSIONS.cap_hint("media.viber.com", self.owners())
        self.assertTrue(hint["allowed"])
        self.assertEqual(hint["domain"], "viber.com")

    def test_a_shared_cdn_is_refused_with_the_reason(self):
        hint = SESSIONS.cap_hint("x.gw.samsungapps.com.cdn.cloudflare.net", self.owners())
        self.assertFalse(hint["allowed"])
        self.assertIn("throttle unrelated traffic", hint["reason"])

    def test_a_domain_a_service_already_claims_says_which(self):
        hint = SESSIONS.cap_hint("occ-0-1.nflxso.net", self.owners())
        self.assertFalse(hint["allowed"])
        self.assertEqual(hint["service"], "Netflix")
        self.assertIn("already part of Netflix", hint["reason"])

    def test_a_co_delivery_domain_counts_as_claimed(self):
        hint = SESSIONS.cap_hint("rr4.sn-x.gvt1.com", self.owners())
        self.assertFalse(hint["allowed"])
        self.assertEqual(hint["service"], "YouTube")

    def test_a_destination_with_no_name_has_no_hint(self):
        self.assertIsNone(SESSIONS.cap_hint(None, self.owners()))
        self.assertIsNone(SESSIONS.cap_hint("", self.owners()))

    def test_owners_are_built_once_from_suffixes_and_co_delivery(self):
        owners = self.owners()
        self.assertEqual(owners["nflxso.net"], "Netflix")
        self.assertEqual(owners["gvt1.com"], "YouTube")
        self.assertNotIn("", owners)
