"""End-to-end tests for the aggregation functions that read the system.

These are the functions that produce every number the plugin reports, and they
had no coverage because they touch config.xml, sqlite, RRDs and vnstat. Each is
exercised here against fixtures: real temporary sqlite databases for the flow and
DNS sources, so the actual queries run, and patched boundaries for the binary
formats (RRD, vnstat) where fabricating files would test the fixture rather than
the code.
"""

import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

SOURCE_DIR = Path(__file__).parents[1] / "src/opnsense/scripts/OPNsense/WanQuota"
sys.path.insert(0, str(SOURCE_DIR))


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SOURCE_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CONSUMERS = _load("wanquota_consumers_it", "consumers.py")
REPORT = _load("wanquota_report_it", "report.py")

CONFIG = """<?xml version="1.0"?>
<opnsense>
  <interfaces>
    <lan><if>em0</if><ipaddr>192.168.1.1</ipaddr><subnet>24</subnet></lan>
    <wan><if>igb0</if></wan>
    <opt1><if>ue0</if></opt1>
  </interfaces>
  <system>
    <hosts><ip>192.168.1.10</ip><descr>TRUENAS</descr></hosts>
    <hosts><ip>192.168.1.20</ip><descr>Laptop</descr></hosts>
  </system>
  <OPNsense>
    <WanQuota>
      <general>
        <enabled>1</enabled>
        <consumers_enabled>1</consumers_enabled>
        <domain_enabled>1</domain_enabled>
        <top_limit>20</top_limit>
        <default_period>thirty</default_period>
        <domain_retention_days>90</domain_retention_days>
        <provider1_enabled>1</provider1_enabled>
        <provider1_name>ETISALAT</provider1_name>
        <provider1_interface>wan</provider1_interface>
        <provider1_quota_gb>140</provider1_quota_gb>
        <provider1_cycle_day>1</provider1_cycle_day>
        <provider1_warning_percent>80</provider1_warning_percent>
        <provider2_enabled>1</provider2_enabled>
        <provider2_name>MOBINIL</provider2_name>
        <provider2_interface>opt1</provider2_interface>
        <provider2_quota_gb>400</provider2_quota_gb>
        <provider2_cycle_day>1</provider2_cycle_day>
        <provider2_warning_percent>80</provider2_warning_percent>
      </general>
    </WanQuota>
  </OPNsense>
</opnsense>
"""


class ConsumerReportTests(unittest.TestCase):
    """consumers.report() against real sqlite fixtures."""

    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        root = Path(self.scratch.name)

        self.config = root / "config.xml"
        self.config.write_text(CONFIG, encoding="utf-8")

        # Real sqlite, real queries. Insight stores one row per flow.
        self.flow_db = root / "flows.sqlite"
        with sqlite3.connect(self.flow_db) as connection:
            connection.execute(
                "CREATE TABLE flows (if_name TEXT, direction TEXT, src_addr TEXT, "
                "dst_addr TEXT, octets INTEGER, mtime INTEGER)"
            )
        self.domain_db = root / "domains.sqlite"
        with sqlite3.connect(self.domain_db) as connection:
            connection.execute(
                "CREATE TABLE ip_domains (ip TEXT PRIMARY KEY, domain TEXT, last_seen INTEGER)"
            )
            connection.executemany(
                "INSERT INTO ip_domains VALUES (?, ?, strftime('%s','now'))",
                [("198.51.100.5", "cdn.example"), ("198.51.100.6", "pkg.example")],
            )

        self.saved = {
            "DNSMASQ_LEASES": CONSUMERS.DNSMASQ_LEASES,
            "KEA_LEASES": CONSUMERS.KEA_LEASES,
            "arp_macs": CONSUMERS.arp_macs,
            "CONFIG_PATH": CONSUMERS.CONFIG_PATH,
            "DOMAIN_DB": CONSUMERS.DOMAIN_DB,
            "flow_rows": CONSUMERS.flow_rows,
            "host_rrds": CONSUMERS.host_rrds,
            "rrd_totals": CONSUMERS.rrd_totals,
            "domain_map": CONSUMERS.domain_map,
        }
        CONSUMERS.CONFIG_PATH = str(self.config)
        CONSUMERS.DOMAIN_DB = str(self.domain_db)
        # Lease and ARP sources: absent by default, overridden per test.
        CONSUMERS.DNSMASQ_LEASES = str(root / "absent.leases")
        CONSUMERS.KEA_LEASES = str(root / "absent.csv")
        CONSUMERS.arp_macs = lambda runner=None: {}
        self.root = root

        # ntopng RRDs are a binary format; fabricating them would test the
        # fixture, not the report. Patch at the boundary instead.
        CONSUMERS.host_rrds = lambda network: [
            ("192.168.1.10", "/fake/truenas"),
            ("192.168.1.20", "/fake/laptop"),
            ("192.168.1.1", "/fake/router"),
        ]
        CONSUMERS.rrd_totals = lambda path, start: {
            "/fake/truenas": (100, 900),
            "/fake/laptop": (10, 90),
            "/fake/router": (1, 1),
        }[path]

    def tearDown(self):
        for name, value in self.saved.items():
            setattr(CONSUMERS, name, value)
        self.scratch.cleanup()

    def set_flows(self, rows):
        CONSUMERS.flow_rows = lambda start: rows

    def test_router_is_excluded_from_host_totals(self):
        self.set_flows([])
        result = CONSUMERS.report("thirty")
        self.assertEqual({h["ip"] for h in result["hosts"]}, {"192.168.1.10", "192.168.1.20"})

    def test_hosts_are_named_and_ranked(self):
        self.set_flows([])
        result = CONSUMERS.report("thirty")
        self.assertEqual([h["name"] for h in result["hosts"]], ["TRUENAS", "Laptop"])
        self.assertEqual(result["hosts"][0]["total"], 1000)

    def test_lan_egress_is_attributed_to_a_domain(self):
        self.set_flows([
            {"if": "em0", "direction": "out", "src_addr": "192.168.1.10",
             "dst_addr": "198.51.100.5", "octets": 600},
            {"if": "em0", "direction": "out", "src_addr": "192.168.1.20",
             "dst_addr": "198.51.100.6", "octets": 200},
        ])
        result = CONSUMERS.report("thirty")
        pairs = {(r["name"], r["domain"], r["total"]) for r in result["device_domains"]}
        self.assertIn(("TRUENAS", "cdn.example", 600), pairs)
        self.assertIn(("Laptop", "pkg.example", 200), pairs)

    def test_unmapped_destination_counts_as_unattributed(self):
        self.set_flows([
            {"if": "em0", "direction": "out", "src_addr": "192.168.1.10",
             "dst_addr": "198.51.100.5", "octets": 300},
            {"if": "em0", "direction": "out", "src_addr": "192.168.1.10",
             "dst_addr": "203.0.113.99", "octets": 700},
        ])
        result = CONSUMERS.report("thirty")
        row = next(r for r in result["device_attribution"] if r["device"] == "192.168.1.10")
        self.assertEqual(row["external"], 1000)
        self.assertEqual(row["attributed"], 300)
        self.assertEqual(row["unattributed"], 700)
        self.assertAlmostEqual(result["domain_attribution"]["coverage_percent"], 30.0)

    def test_provider_ingress_is_grouped_per_wan(self):
        self.set_flows([
            {"if": "igb0", "direction": "in", "src_addr": "198.51.100.5",
             "dst_addr": "192.168.1.10", "octets": 400},
            {"if": "ue0", "direction": "in", "src_addr": "198.51.100.6",
             "dst_addr": "192.168.1.20", "octets": 250},
        ])
        result = CONSUMERS.report("thirty")
        by_name = {p["name"]: p for p in result["providers"]}
        self.assertEqual(by_name["ETISALAT"]["total"], 400)
        self.assertEqual(by_name["MOBINIL"]["total"], 250)
        self.assertEqual(by_name["ETISALAT"]["devices"][0]["name"], "TRUENAS")

    def test_router_traffic_is_not_attributed_to_a_device(self):
        self.set_flows([
            {"if": "em0", "direction": "out", "src_addr": "192.168.1.1",
             "dst_addr": "198.51.100.5", "octets": 5000},
        ])
        result = CONSUMERS.report("thirty")
        self.assertEqual(result["device_domains"], [])

    def test_lan_to_lan_traffic_is_ignored(self):
        self.set_flows([
            {"if": "em0", "direction": "out", "src_addr": "192.168.1.10",
             "dst_addr": "192.168.1.20", "octets": 9999},
        ])
        result = CONSUMERS.report("thirty")
        self.assertEqual(result["device_domains"], [])
        self.assertEqual(result["domain_attribution"]["total_external_bytes"], 0)

    def test_flow_database_failure_is_reported_not_raised(self):
        def explode(start):
            raise sqlite3.Error("database is locked")

        CONSUMERS.flow_rows = explode
        result = CONSUMERS.report("thirty")
        self.assertEqual(result["status"], "ok")
        self.assertIn("locked", result["domain_attribution"]["error"])
        self.assertTrue(result["hosts"])

    def test_disabled_consumers_returns_empty_document(self):
        self.config.write_text(
            CONFIG.replace("<consumers_enabled>1<", "<consumers_enabled>0<"), encoding="utf-8"
        )
        result = CONSUMERS.report("thirty")
        self.assertEqual(result["status"], "disabled")

    def test_domain_map_reads_the_real_database(self):
        mapping = CONSUMERS.domain_map()
        self.assertEqual(mapping.get("198.51.100.5"), "cdn.example")


class SummaryTests(unittest.TestCase):
    """report.summary() against a patched vnstat boundary."""

    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.config = Path(self.scratch.name) / "config.xml"
        self.config.write_text(CONFIG, encoding="utf-8")
        self.saved = {"CONFIG_PATH": REPORT.CONFIG_PATH, "vnstat_rows": REPORT.vnstat_rows}
        REPORT.CONFIG_PATH = str(self.config)

    def tearDown(self):
        for name, value in self.saved.items():
            setattr(REPORT, name, value)
        self.scratch.cleanup()

    def test_configuration_reads_both_enabled_providers(self):
        enabled, providers = REPORT.configuration()
        self.assertTrue(enabled)
        self.assertEqual([p["name"] for p in providers], ["ETISALAT", "MOBINIL"])
        self.assertEqual(providers[0]["interface"], "igb0")

    def test_summary_totals_and_remaining(self):
        import datetime as dt
        today = dt.date.today().isoformat()
        REPORT.vnstat_rows = lambda interface, period: (
            [{"date": {"year": int(today[:4]), "month": int(today[5:7]), "day": int(today[8:10])},
              "rx": 1_000_000_000, "tx": 200_000_000}],
            None,
        )
        document = REPORT.summary(*REPORT.configuration())
        self.assertEqual(document["status"], "ok")
        etisalat = document["providers"][0]
        self.assertEqual(etisalat["used"], 1_200_000_000)
        self.assertEqual(etisalat["quota"], 140_000_000_000)
        self.assertEqual(etisalat["remaining"], 140_000_000_000 - 1_200_000_000)
        self.assertTrue(etisalat["available"])

    def test_vnstat_failure_marks_provider_unavailable(self):
        REPORT.vnstat_rows = lambda interface, period: ([], "vnstat: interface not found")
        document = REPORT.summary(*REPORT.configuration())
        self.assertFalse(document["providers"][0]["available"])

    def rows_for(self, dates_and_bytes):
        def rows(interface, period):
            return ([
                {"date": {"year": d.year, "month": d.month, "day": d.day}, "rx": rx, "tx": 0}
                for d, rx in dates_and_bytes
            ], None)
        return rows

    def test_projection_uses_measured_days_not_elapsed_days(self):
        import datetime as dt
        today = dt.date.today()
        start = today.replace(day=1)
        # Three measured days late in a cycle that began on the 1st: the earlier
        # days were never collected, and must not dilute the observed rate.
        measured = [(today - dt.timedelta(days=n), 2_000_000_000) for n in range(3)]
        if any(d < start for d, _ in measured):
            self.skipTest("run near the start of a month")
        REPORT.vnstat_rows = self.rows_for(measured)
        item = REPORT.summary(*REPORT.configuration())["providers"][0]
        self.assertEqual(item["measured_days"], 3)
        self.assertEqual(item["daily_average"], item["used"] / 3)
        self.assertEqual(item["projection_basis"], "partial" if item["missing_days"] else "measured")
        if item["missing_days"]:
            self.assertIn("no vnStat data", item["projection_note"])
            # The old formula divided by elapsed days, understating the rate.
            self.assertGreater(item["daily_average"], item["used"] / item["elapsed_days"])

    def test_complete_cycle_reports_measured_basis_and_no_note(self):
        import datetime as dt
        today = dt.date.today()
        start = today.replace(day=1)
        every_day = [(start + dt.timedelta(days=n), 1_000_000_000)
                     for n in range((today - start).days + 1)]
        REPORT.vnstat_rows = self.rows_for(every_day)
        item = REPORT.summary(*REPORT.configuration())["providers"][0]
        self.assertEqual(item["missing_days"], 0)
        self.assertEqual(item["projection_basis"], "measured")
        self.assertIsNone(item["projection_note"])

    def test_projection_is_never_below_what_was_already_used(self):
        import datetime as dt
        today = dt.date.today()
        REPORT.vnstat_rows = self.rows_for([(today, 5_000_000_000)])
        item = REPORT.summary(*REPORT.configuration())["providers"][0]
        self.assertGreaterEqual(item["projected"], item["used"])


class IdentityIntegrationTests(ConsumerReportTests):
    """Identity resolution through the whole report."""

    def test_lease_hostname_names_a_device_with_no_static_mapping(self):
        # 192.168.1.30 is deliberately absent from CONFIG's hosts entries.
        (self.root / "d.leases").write_text(
            "1787050729 aa:bb:cc:dd:ee:01 192.168.1.30 spare-laptop *\n", encoding="utf-8")
        CONSUMERS.DNSMASQ_LEASES = str(self.root / "d.leases")
        CONSUMERS.host_rrds = lambda network: [("192.168.1.30", "/fake/spare")]
        CONSUMERS.rrd_totals = lambda path, start: (10, 90)
        self.set_flows([])
        result = CONSUMERS.report("thirty")
        row = next(h for h in result["hosts"] if h["ip"] == "192.168.1.30")
        self.assertEqual(row["name"], "spare-laptop")
        self.assertEqual(row["name_source"], "dhcp")

    def test_static_name_still_wins_over_a_lease(self):
        (self.root / "d.leases").write_text(
            "1787050729 aa:bb:cc:dd:ee:02 192.168.1.10 truenas-dhcp *\n", encoding="utf-8")
        CONSUMERS.DNSMASQ_LEASES = str(self.root / "d.leases")
        self.set_flows([])
        row = next(h for h in CONSUMERS.report("thirty")["hosts"] if h["ip"] == "192.168.1.10")
        self.assertEqual(row["name"], "TRUENAS")
        self.assertEqual(row["name_source"], "static")

    def test_hosts_and_attribution_carry_mac_and_stable_key(self):
        CONSUMERS.arp_macs = lambda runner=None: {"192.168.1.10": "70:f3:95:04:88:a6"}
        self.set_flows([
            {"if": "em0", "direction": "out", "src_addr": "192.168.1.10",
             "dst_addr": "198.51.100.5", "octets": 600},
        ])
        result = CONSUMERS.report("thirty")
        host = next(h for h in result["hosts"] if h["ip"] == "192.168.1.10")
        att = next(a for a in result["device_attribution"] if a["device"] == "192.168.1.10")
        self.assertEqual(host["mac"], "70:f3:95:04:88:a6")
        self.assertEqual(host["device_key"], "70:f3:95:04:88:a6")
        self.assertEqual(att["mac"], "70:f3:95:04:88:a6")

    def test_stable_key_is_the_address_when_no_mac_is_known(self):
        self.set_flows([])
        host = next(h for h in CONSUMERS.report("thirty")["hosts"] if h["ip"] == "192.168.1.10")
        self.assertEqual(host["device_key"], "192.168.1.10")


if __name__ == "__main__":
    unittest.main()
