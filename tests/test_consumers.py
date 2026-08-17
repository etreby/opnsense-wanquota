import datetime as dt
import importlib.util
from pathlib import Path
import tempfile
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



class LeaseNamingTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.dir.cleanup()

    def write(self, name, text):
        path = Path(self.dir.name) / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_dnsmasq_leases_parsed(self):
        path = self.write("d.leases",
            "1787050729 60:cf:84:d9:c1:2c 192.168.1.46 etreby-desktop-25g *\n"
            "1787029620 70:f3:95:04:88:a6 192.168.1.10 truenas *\n")
        got = CONSUMERS.dnsmasq_leases(path)
        self.assertEqual(got["192.168.1.10"], ("truenas", "70:f3:95:04:88:a6"))

    def test_dnsmasq_star_hostname_is_not_a_name(self):
        path = self.write("d2.leases", "1787050729 aa:bb:cc:dd:ee:ff 192.168.1.60 * *\n")
        self.assertEqual(CONSUMERS.dnsmasq_leases(path)["192.168.1.60"][0], "")

    def test_kea_leases_parsed(self):
        path = self.write("k.csv",
            "address,hwaddr,client_id,valid_lifetime,expire,subnet_id,fqdn_fwd,fqdn_rev,hostname,state,user_context,pool_id\n"
            "192.168.1.77,11:22:33:44:55:66,,7200,1787,1,0,0,printer.lan.,0,,0\n")
        self.assertEqual(CONSUMERS.kea_leases(path), {"192.168.1.77": ("printer.lan", "11:22:33:44:55:66")})

    def test_missing_lease_files_are_not_an_error(self):
        self.assertEqual(CONSUMERS.dnsmasq_leases("/nonexistent"), {})
        self.assertEqual(CONSUMERS.kea_leases("/nonexistent"), {})

    def test_empty_kea_file_is_not_an_error(self):
        path = self.write("empty.csv", "address,hwaddr,hostname\n")
        self.assertEqual(CONSUMERS.kea_leases(path), {})

    def test_arp_parses_and_skips_permanent(self):
        out = ("? (172.16.1.100) at 68:f7:28:e7:eb:5e on igb0 permanent [ethernet]\n"
               "? (192.168.1.10) at 70:f3:95:04:88:a6 on em0 expires in 900 seconds [ethernet]\n")
        got = CONSUMERS.arp_macs(lambda: out)
        self.assertEqual(got, {"192.168.1.10": "70:f3:95:04:88:a6"})

    def test_arp_failure_is_not_fatal(self):
        def boom():
            raise OSError("arp missing")
        self.assertEqual(CONSUMERS.arp_macs(boom), {})


class IdentityTests(unittest.TestCase):
    def test_static_name_wins_over_lease(self):
        ident = CONSUMERS.identities(
            {"192.168.1.10": "TRUENAS"}, {"192.168.1.10": ("truenas", "70:f3:95:04:88:a6")}, {})
        self.assertEqual(ident["192.168.1.10"]["name"], "TRUENAS")
        self.assertEqual(ident["192.168.1.10"]["name_source"], "static")

    def test_lease_name_used_when_no_static_mapping(self):
        # This is the case that made a real device show as a bare IP.
        ident = CONSUMERS.identities({}, {"192.168.1.222": ("MacBookPro", "de:80:12:9d:25:90")}, {})
        self.assertEqual(ident["192.168.1.222"]["name"], "MacBookPro")
        self.assertEqual(ident["192.168.1.222"]["name_source"], "dhcp")

    def test_address_is_the_last_resort(self):
        ident = CONSUMERS.identities({}, {}, {"192.168.1.99": "aa:bb:cc:dd:ee:ff"})
        self.assertEqual(ident["192.168.1.99"]["name"], "192.168.1.99")
        self.assertEqual(ident["192.168.1.99"]["name_source"], "address")

    def test_stable_key_is_the_mac_when_known(self):
        ident = CONSUMERS.identities({}, {}, {"192.168.1.50": "aa:bb:cc:dd:ee:ff"})
        self.assertEqual(ident["192.168.1.50"]["key"], "aa:bb:cc:dd:ee:ff")

    def test_stable_key_falls_back_to_address(self):
        ident = CONSUMERS.identities({"192.168.1.51": "Thing"}, {}, {})
        self.assertEqual(ident["192.168.1.51"]["key"], "192.168.1.51")

    def test_arp_mac_wins_over_a_stale_lease_mac(self):
        ident = CONSUMERS.identities(
            {}, {"192.168.1.60": ("box", "00:00:00:00:00:01")}, {"192.168.1.60": "aa:aa:aa:aa:aa:aa"})
        self.assertEqual(ident["192.168.1.60"]["mac"], "aa:aa:aa:aa:aa:aa")


if __name__ == "__main__":
    unittest.main()
