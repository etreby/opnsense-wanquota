import datetime as dt
import importlib.util
from pathlib import Path
import unittest


SOURCE = Path(__file__).parents[1] / "src/opnsense/scripts/OPNsense/WanQuota/consumers.py"
SPEC = importlib.util.spec_from_file_location("wanquota_consumers", SOURCE)
CONSUMERS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONSUMERS)


class ConsumerHelpersTests(unittest.TestCase):
    def test_period_boundaries(self):
        today = dt.date.today()
        self.assertEqual(CONSUMERS.period_start("today"), today)
        self.assertEqual(CONSUMERS.period_start("week"), today - dt.timedelta(days=6))
        self.assertEqual(CONSUMERS.period_start("thirty"), today - dt.timedelta(days=29))
        self.assertEqual(CONSUMERS.period_start("month"), today.replace(day=1))

    def test_domain_normalization(self):
        self.assertEqual(CONSUMERS.normalize_domain("Example.COM."), "example.com")

    def test_network_membership(self):
        network = CONSUMERS.ipaddress.ip_network("192.0.2.0/24")
        self.assertTrue(CONSUMERS.is_local("192.0.2.10", network))
        self.assertFalse(CONSUMERS.is_local("198.51.100.10", network))
        self.assertFalse(CONSUMERS.is_local("not-an-address", network))

    def test_classifies_lan_upload_without_provider(self):
        settings = {"network": CONSUMERS.ipaddress.ip_network("192.0.2.0/24"), "router": "192.0.2.1", "lan_interface": "lan0", "providers": {"wan0": {}}}
        row = {"if": "lan0", "direction": "out", "src_addr": "192.0.2.20", "dst_addr": "198.51.100.10", "octets": 500}
        result = CONSUMERS.classify_flow(row, settings)
        self.assertEqual((result["scope"], result["provider"], result["host"]), ("lan", None, "192.0.2.20"))

    def test_classifies_wan_download_to_internal_device(self):
        settings = {"network": CONSUMERS.ipaddress.ip_network("192.0.2.0/24"), "router": "192.0.2.1", "lan_interface": "lan0", "providers": {"wan0": {}}}
        row = {"if": "wan0", "direction": "in", "src_addr": "198.51.100.10", "dst_addr": "192.0.2.20", "octets": 900}
        result = CONSUMERS.classify_flow(row, settings)
        self.assertEqual((result["scope"], result["provider"], result["host"]), ("provider", "wan0", "192.0.2.20"))


class MatrixCapTests(unittest.TestCase):
    @staticmethod
    def row(device, domain, total):
        return {"device": device, "domain": domain, "total": total}

    def test_keeps_each_device_top_domains(self):
        # Every device shares the same domains, so the by-domain pass cannot be
        # what rescues the quiet device — only the per-device cap can.
        shared = [f"d{i}.example" for i in range(5)]
        rows = [self.row("A", name, 1000 - i) for i, name in enumerate(shared)]
        rows += [self.row("B", name, 10 - i) for i, name in enumerate(shared)]
        capped = CONSUMERS.cap_matrix(rows, 2)
        kept = {r["domain"] for r in capped if r["device"] == "B"}
        # B's own top 2 survive even though both rank far below every A row.
        self.assertIn("d0.example", kept)
        self.assertIn("d1.example", kept)

    def test_global_top_n_would_have_dropped_the_quiet_device(self):
        # Guards the actual bug: a plain global sort+slice loses B entirely.
        shared = [f"d{i}.example" for i in range(5)]
        rows = [self.row("A", name, 1000 - i) for i, name in enumerate(shared)]
        rows += [self.row("B", name, 10 - i) for i, name in enumerate(shared)]
        global_top = sorted(rows, key=lambda r: r["total"], reverse=True)[:5]
        self.assertEqual({r["device"] for r in global_top}, {"A"})
        self.assertIn("B", {r["device"] for r in CONSUMERS.cap_matrix(rows, 2)})

    def test_keeps_each_domain_top_devices(self):
        # shared.example is every device's rank-3 domain, so a per-device-only cap
        # of 2 would drop it entirely and break the domain drill-down.
        rows = []
        for device in ("A", "B"):
            rows.append(self.row(device, "big1.example", 900))
            rows.append(self.row(device, "big2.example", 800))
            rows.append(self.row(device, "shared.example", 5))
        capped = CONSUMERS.cap_matrix(rows, 2)
        shared = [r for r in capped if r["domain"] == "shared.example"]
        self.assertEqual({r["device"] for r in shared}, {"A", "B"})

    def test_output_is_sorted_and_deduplicated(self):
        rows = [self.row("A", "x.example", 10), self.row("B", "x.example", 30), self.row("A", "y.example", 20)]
        capped = CONSUMERS.cap_matrix(rows, 5)
        self.assertEqual([r["total"] for r in capped], [30, 20, 10])
        self.assertEqual(len(capped), len({(r["device"], r["domain"]) for r in capped}))

    def test_empty_input(self):
        self.assertEqual(CONSUMERS.cap_matrix([], 5), [])


class DeviceAttributionTests(unittest.TestCase):
    def test_coverage_uses_external_bytes_as_denominator(self):
        rows = CONSUMERS.attribution_rows({"192.0.2.20": 1000}, {"192.0.2.20": 250}, {})
        self.assertEqual(rows[0]["coverage_percent"], 25.0)
        self.assertEqual(rows[0]["unattributed"], 750)

    def test_device_with_no_attributed_flows(self):
        rows = CONSUMERS.attribution_rows({"192.0.2.30": 500}, {}, {})
        self.assertEqual(rows[0]["attributed"], 0)
        self.assertEqual(rows[0]["coverage_percent"], 0)
        self.assertEqual(rows[0]["unattributed"], 500)

    def test_zero_external_does_not_divide_by_zero(self):
        rows = CONSUMERS.attribution_rows({"192.0.2.40": 0}, {}, {})
        self.assertEqual(rows[0]["coverage_percent"], 0)

    def test_flags_a_busy_device_that_resolves_to_almost_nothing(self):
        rows = CONSUMERS.attribution_rows({"192.0.2.20": 400_000_000}, {"192.0.2.20": 2_000_000}, {})
        self.assertTrue(rows[0]["likely_unattributable"])

    def test_does_not_flag_a_small_talker(self):
        # 0% of a trivial amount says nothing about encrypted DNS.
        rows = CONSUMERS.attribution_rows({"192.0.2.21": 1_000_000}, {}, {})
        self.assertFalse(rows[0]["likely_unattributable"])

    def test_does_not_flag_a_well_attributed_device(self):
        rows = CONSUMERS.attribution_rows({"192.0.2.22": 900_000_000}, {"192.0.2.22": 800_000_000}, {})
        self.assertFalse(rows[0]["likely_unattributable"])

    def test_uses_friendly_name_and_sorts_by_external(self):
        rows = CONSUMERS.attribution_rows(
            {"192.0.2.20": 100, "192.0.2.30": 900},
            {"192.0.2.30": 900},
            {"192.0.2.30": "TRUENAS"},
        )
        self.assertEqual([r["name"] for r in rows], ["TRUENAS", "192.0.2.20"])


if __name__ == "__main__":
    unittest.main()
