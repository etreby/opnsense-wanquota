"""Per-service bandwidth limits: plan building, and what it refuses.

The refusals matter as much as the plan. Capping a shared CDN would throttle
unrelated traffic, and a cap with no matching addresses is a limit that silently
does nothing, so both are reported rather than quietly accepted.
"""

import importlib.util
from pathlib import Path
import sys
import unittest

SOURCE_DIR = Path(__file__).parents[1] / "src/opnsense/scripts/OPNsense/WanQuota"
sys.path.insert(0, str(SOURCE_DIR))
SPEC = importlib.util.spec_from_file_location("wanquota_shaper", SOURCE_DIR / "shaper.py")
SHAPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHAPER)

MAPPINGS = [
    ("ipv4-c001.lhr001.ix.nflxvideo.net", "198.51.100.10"),
    ("ipv4-c002.lhr001.ix.nflxvideo.net", "198.51.100.11"),
    ("netflix.com", "198.51.100.12"),
    ("rr1---sn-abc.googlevideo.com", "203.0.113.20"),
    ("example.invalid", "203.0.113.99"),
]


class RateTests(unittest.TestCase):
    def test_published_presets(self):
        self.assertEqual(SHAPER.RESOLUTION_PRESETS["1080p"], 5.0)
        self.assertEqual(SHAPER.RESOLUTION_PRESETS["4k"], 15.0)
        self.assertEqual(SHAPER.RESOLUTION_PRESETS["720p"], 3.0)

    def test_resolution_resolves_to_its_rate(self):
        self.assertEqual(SHAPER.resolve_rate({"resolution": "1080p"}), 5.0)

    def test_resolution_is_case_insensitive(self):
        self.assertEqual(SHAPER.resolve_rate({"resolution": "1080P"}), 5.0)

    def test_explicit_mbit_wins_over_a_preset(self):
        self.assertEqual(SHAPER.resolve_rate({"resolution": "1080p", "mbit": 2}), 2.0)

    def test_zero_and_negative_rates_are_refused(self):
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                SHAPER.resolve_rate({"mbit": bad})

    def test_nonsense_rate_is_refused(self):
        with self.assertRaises(ValueError):
            SHAPER.resolve_rate({"mbit": "fast"})

    def test_missing_rate_names_the_valid_presets(self):
        with self.assertRaises(ValueError) as caught:
            SHAPER.resolve_rate({})
        self.assertIn("1080p", str(caught.exception))


class SharedCdnTests(unittest.TestCase):
    def test_shared_infrastructure_is_recognised(self):
        for suffix in ("cloudflare.com", "a.akamaiedge.net", "d1.cloudfront.net",
                       "gstatic.com", "s3.amazonaws.com"):
            self.assertTrue(SHAPER.is_shared_cdn(suffix), suffix)

    def test_dedicated_media_hostnames_are_not(self):
        for suffix in ("nflxvideo.net", "googlevideo.com", "ttvnw.net", "scdn.co"):
            self.assertFalse(SHAPER.is_shared_cdn(suffix), suffix)

    def test_no_suffix_belongs_to_two_services(self):
        # Two services sharing a suffix would give two pipes the same addresses,
        # and capping one would silently cap the other. fbcdn.net is the case that
        # forced this: it carries both Facebook and Instagram media, so it is its
        # own entry rather than filed under either.
        seen = {}
        for key, service in SHAPER.STREAMING_SERVICES.items():
            for suffix in service["suffixes"]:
                self.assertNotIn(suffix, seen,
                                 f"{suffix} in both {seen.get(suffix)} and {key}")
                seen[suffix] = key

    def test_social_services_are_present(self):
        for key in ("instagram", "facebook", "meta_cdn"):
            self.assertIn(key, SHAPER.STREAMING_SERVICES, key)

    def test_newly_added_services_are_present(self):
        for key in ("watchit", "yango_play", "tod", "xbox", "epic_games", "playstation"):
            self.assertIn(key, SHAPER.STREAMING_SERVICES, key)

    def test_no_catalogued_service_rides_shared_infrastructure(self):
        # The catalog is the safety boundary; if an entry ever gains a shared
        # suffix, capping it would throttle unrelated traffic.
        for key, service in SHAPER.STREAMING_SERVICES.items():
            for suffix in service["suffixes"]:
                self.assertFalse(SHAPER.is_shared_cdn(suffix), f"{key}: {suffix}")


class AddressTests(unittest.TestCase):
    def test_matches_subdomains_of_a_service_suffix(self):
        got, _, _extra = SHAPER.service_addresses(("nflxvideo.net",), MAPPINGS)
        self.assertEqual(got, ["198.51.100.10", "198.51.100.11"])

    def test_unrelated_domains_are_not_matched(self):
        got, _, _extra = SHAPER.service_addresses(("nflxvideo.net",), MAPPINGS)
        self.assertNotIn("203.0.113.99", got)

    def test_result_is_sorted_and_deduplicated(self):
        pairs = MAPPINGS + [("a.nflxvideo.net", "198.51.100.10")]
        got, _, _extra = SHAPER.service_addresses(("nflxvideo.net",), pairs)
        self.assertEqual(got, sorted(set(got)))

    def test_no_mappings_yields_nothing(self):
        self.assertEqual(SHAPER.service_addresses(("nflxvideo.net",), []), ([], {}, {}))

    def test_address_shared_with_another_service_is_excluded(self):
        # Observed on real data: a third of Netflix's addresses also served
        # amazonaws.com. Capping those throttles unrelated traffic.
        pairs = [("nflxvideo.net", "198.51.100.10"),
                 ("netflix.com", "198.51.100.50"),
                 ("amazonaws.com", "198.51.100.50")]
        exclusive, shared, _extra = SHAPER.service_addresses(("nflxvideo.net", "netflix.com"), pairs)
        self.assertEqual(exclusive, ["198.51.100.10"])
        self.assertIn("198.51.100.50", shared)
        self.assertIn("amazonaws.com", shared["198.51.100.50"])

    def test_two_hostnames_of_the_same_service_do_not_count_as_sharing(self):
        pairs = [("nflxvideo.net", "198.51.100.10"), ("netflix.com", "198.51.100.10")]
        exclusive, shared, _extra = SHAPER.service_addresses(("nflxvideo.net", "netflix.com"), pairs)
        self.assertEqual(exclusive, ["198.51.100.10"])
        self.assertEqual(shared, {})

    def test_service_whose_every_address_is_shared_is_refused(self):
        pairs = [("netflix.com", "198.51.100.50"), ("amazonaws.com", "198.51.100.50")]
        plan = SHAPER.build_plan([{"service": "netflix", "resolution": "1080p"}], pairs)
        self.assertEqual(plan["pipes"], [])
        self.assertIn("shared with other services", plan["rejected"][0]["reason"])

    def test_plan_reports_how_many_addresses_were_excluded(self):
        pairs = [("nflxvideo.net", "198.51.100.10"),
                 ("netflix.com", "198.51.100.50"), ("amazonaws.com", "198.51.100.50")]
        plan = SHAPER.build_plan([{"service": "netflix", "mbit": 5}], pairs)
        self.assertEqual(plan["pipes"][0]["address_count"], 1)
        self.assertEqual(plan["pipes"][0]["shared_excluded"], 1)


class CoDeliveryTests(unittest.TestCase):
    """Nodes that serve a service under a second name of the same operator.

    Measured on a live network: the address serving a 720p YouTube stream resolved
    from both rr4.sn-vg5obxxb-j5pk.googlevideo.com and
    rr4.sn-vg5obxxb-j5pk.gvt1.com. Treating gvt1.com as a stranger excluded 22 of
    49 observed video nodes — including the one carrying the stream — so the cap
    matched the YouTube page and never the video.
    """

    NODE = [("rr4.sn-x.googlevideo.com", "41.91.253.47"),
            ("rr4.sn-x.gvt1.com", "41.91.253.47")]

    def test_a_co_delivery_node_is_cappable(self):
        exclusive, shared, incidental = SHAPER.service_addresses(
            ("googlevideo.com",), self.NODE, co_delivery=("gvt1.com",))
        self.assertEqual(exclusive, ["41.91.253.47"])
        self.assertEqual(shared, {})
        self.assertEqual(incidental["41.91.253.47"], ["gvt1.com"])

    def test_without_the_declaration_the_same_node_is_excluded(self):
        """The behaviour being corrected."""
        exclusive, shared, _ = SHAPER.service_addresses(("googlevideo.com",), self.NODE)
        self.assertEqual(exclusive, [])
        self.assertIn("41.91.253.47", shared)

    def test_genuinely_unrelated_domains_still_exclude_the_address(self):
        """Search, static assets, APIs and ads must never be caught by a video cap."""
        for stranger in ("google.com", "gstatic.com", "googleapis.com",
                         "doubleclick.net", "app-measurement.com"):
            pairs = [("rr1.googlevideo.com", "203.0.113.7"), (stranger, "203.0.113.7")]
            exclusive, shared, _ = SHAPER.service_addresses(
                ("googlevideo.com",), pairs, co_delivery=("gvt1.com",))
            self.assertEqual(exclusive, [], f"{stranger} must still exclude the address")
            self.assertIn(stranger, shared["203.0.113.7"])

    def test_the_youtube_catalog_entry_declares_it(self):
        self.assertIn("gvt1.com", SHAPER.STREAMING_SERVICES["youtube"]["co_delivery"])

    def test_the_plan_discloses_what_else_the_cap_limits(self):
        plan = SHAPER.build_plan([{"service": "youtube", "mbit": 3}], self.NODE)
        entry = plan["pipes"][0]
        self.assertEqual(entry["address_count"], 1)
        self.assertEqual(entry["also_limits"], ["gvt1.com"])
        self.assertEqual(entry["also_limits_addresses"], 1)

    def test_a_plan_with_nothing_incidental_says_so(self):
        plan = SHAPER.build_plan([{"service": "netflix", "mbit": 5}], MAPPINGS)
        self.assertEqual(plan["pipes"][0]["also_limits"], [])

    def test_no_co_delivery_domain_is_shared_infrastructure(self):
        """A co-delivery domain on a real CDN would reintroduce the original hazard."""
        for key, service in SHAPER.STREAMING_SERVICES.items():
            for domain in service.get("co_delivery", ()):
                self.assertFalse(SHAPER.is_shared_cdn(domain), f"{key}: {domain}")

    def test_no_co_delivery_domain_belongs_to_another_service(self):
        """Otherwise capping one service would silently cap another."""
        suffixes = {}
        for key, service in SHAPER.STREAMING_SERVICES.items():
            for suffix in service["suffixes"]:
                suffixes[suffix] = key
        for key, service in SHAPER.STREAMING_SERVICES.items():
            for domain in service.get("co_delivery", ()):
                owner = suffixes.get(domain)
                self.assertIsNone(owner, f"{key} co-delivers {domain}, owned by {owner}")


class UpdateServiceTests(unittest.TestCase):
    def test_bulk_download_services_are_available(self):
        for key in ("windows_update", "apple_update", "linux_update", "steam_downloads"):
            self.assertIn(key, SHAPER.STREAMING_SERVICES, key)

    def test_update_services_are_not_on_shared_infrastructure_by_suffix(self):
        for key in ("windows_update", "apple_update", "linux_update", "steam_downloads"):
            for suffix in SHAPER.STREAMING_SERVICES[key]["suffixes"]:
                self.assertFalse(SHAPER.is_shared_cdn(suffix), f"{key}: {suffix}")


class PlanTests(unittest.TestCase):
    def test_builds_a_pipe_and_addresses_for_a_known_service(self):
        plan = SHAPER.build_plan([{"service": "netflix", "resolution": "1080p"}], MAPPINGS)
        self.assertEqual(len(plan["pipes"]), 1)
        entry = plan["pipes"][0]
        self.assertEqual(entry["mbit"], 5.0)
        self.assertEqual(entry["address_count"], 3)
        self.assertEqual(entry["shared_excluded"], 0)
        self.assertEqual(entry["pipe"], SHAPER.PIPE_BASE)

    def test_pipe_numbers_do_not_collide(self):
        plan = SHAPER.build_plan(
            [{"service": "netflix", "resolution": "720p"},
             {"service": "youtube", "resolution": "480p"}], MAPPINGS)
        numbers = [p["pipe"] for p in plan["pipes"]]
        self.assertEqual(len(numbers), len(set(numbers)))

    def test_disabled_entries_are_skipped_silently(self):
        plan = SHAPER.build_plan(
            [{"service": "netflix", "resolution": "1080p", "enabled": False}], MAPPINGS)
        self.assertEqual(plan["pipes"], [])
        self.assertEqual(plan["rejected"], [])

    def test_unknown_service_is_rejected_with_a_reason(self):
        plan = SHAPER.build_plan([{"service": "notaservice", "mbit": 5}], MAPPINGS)
        self.assertEqual(plan["pipes"], [])
        self.assertIn("not a known service", plan["rejected"][0]["reason"])

    def test_service_with_no_observed_addresses_is_rejected_not_silently_empty(self):
        # A rule with no addresses would be a limit that appears active and does
        # nothing, which is worse than a stated refusal.
        plan = SHAPER.build_plan([{"service": "disney", "resolution": "1080p"}], MAPPINGS)
        self.assertEqual(plan["pipes"], [])
        self.assertIn("no addresses observed", plan["rejected"][0]["reason"])

    def test_a_shared_cdn_service_would_be_refused(self):
        catalog = {"risky": {"label": "Risky", "suffixes": ("cloudfront.net",)}}
        plan = SHAPER.build_plan([{"service": "risky", "mbit": 5}],
                                 [("d1.cloudfront.net", "203.0.113.5")], catalog)
        self.assertEqual(plan["pipes"], [])
        self.assertIn("shared infrastructure", plan["rejected"][0]["reason"])

    def test_bad_rate_is_rejected_per_service_not_fatal(self):
        plan = SHAPER.build_plan(
            [{"service": "netflix", "mbit": -1}, {"service": "youtube", "resolution": "720p"}],
            MAPPINGS)
        self.assertEqual([p["service"] for p in plan["pipes"]], ["youtube"])
        self.assertEqual(plan["rejected"][0]["service"], "netflix")

    def test_note_states_the_coverage_limit(self):
        plan = SHAPER.build_plan([], MAPPINGS)
        self.assertIn("encrypted DNS", plan["note"])
        self.assertIn("uncapped", plan["note"])

    def test_empty_configuration_produces_nothing(self):
        plan = SHAPER.build_plan([], MAPPINGS)
        self.assertEqual(plan["pipes"], [])
        self.assertEqual(plan["rejected"], [])


DEVICES = [
    {"address": "192.168.1.32", "name": "ETREBY-DESKTOP WiFi",
     "mac": "e0:8f:4c:8f:a8:d6", "hostname": "etreby-desktop"},
    {"address": "192.168.1.40", "name": "TV", "mac": "aa:bb:cc:dd:ee:ff",
     "hostname": "livingroom-tv"},
]

# Real output from the live firewall, which runs Zenarmor. The eastpect process is
# the Zenarmor engine and holds two netmap descriptors.
FSTAT_ZENARMOR = """\
USER     CMD          PID   FD MOUNT      INUM MODE         SZ|DV R/W
root     eastpect   28653   29 /dev         18 crw-------  netmap rw
root     eastpect   28653   31 /dev         18 crw-------  netmap rw
root     sshd       12345    3 /dev          6 crw-rw-rw-    ttyv rw
"""

FSTAT_CLEAN = """\
USER     CMD          PID   FD MOUNT      INUM MODE         SZ|DV R/W
root     sshd       12345    3 /dev          6 crw-rw-rw-    ttyv rw
root     python3    23456    5 / 1234567 -rw-r--r--  /var/log/netmap.log rw
"""

# Real `ipfw -a list` output captured while a per-device limit was applied.
IPFW_LISTING = """\
00110      0        0 allow carp from any to any
60000      0        0 return next-rulenum proto ip
60001  37009 29096814 pipe 22000 ip from any to 192.168.1.32 out via em0 // 632dc30c-73af
60002    867    71152 pipe 22500 ip from 192.168.1.32 to any in via em0 // e0806d3f-10b2
60003   1200  4500000 pipe 21000 ip from 203.0.113.5 to any out via em0 // aaaa-bbbb
65533 208390 83464228 allow ip from any to any
"""


class BandwidthFieldTests(unittest.TestCase):
    """The shaper model's bandwidth is an integer field.

    A fractional Mbit/s rate is refused with "Bandwidth out of range." and nothing is
    applied at all — no pipe, no rule, and nothing in the interface saying so. A 480p
    YouTube cap failed exactly that way on the live firewall.
    """

    def test_whole_rates_stay_in_mbit(self):
        self.assertEqual(SHAPER.bandwidth_fields(5), (5, "Mbit"))
        self.assertEqual(SHAPER.bandwidth_fields(3.0), (3, "Mbit"))

    def test_fractional_rates_become_kbit(self):
        self.assertEqual(SHAPER.bandwidth_fields(1.5), (1500, "Kbit"))
        self.assertEqual(SHAPER.bandwidth_fields(0.5), (500, "Kbit"))
        self.assertEqual(SHAPER.bandwidth_fields(2.5), (2500, "Kbit"))

    def test_every_value_is_an_integer_of_at_least_one(self):
        """What the model requires: an integer, minimum 1."""
        for mbit in list(SHAPER.RESOLUTION_PRESETS.values()) + [0.001, 0.4, 7.25, 100]:
            value, metric = SHAPER.bandwidth_fields(mbit)
            self.assertIsInstance(value, int, f"{mbit} produced a non-integer")
            self.assertGreaterEqual(value, 1, f"{mbit} produced {value}")
            self.assertIn(metric, ("Mbit", "Kbit"))

    def test_a_rate_too_small_to_express_does_not_become_zero(self):
        """Zero would fail the model's minimum, so it clamps to the smallest rate."""
        self.assertEqual(SHAPER.bandwidth_fields(0.0001), (1, "Kbit"))

    def test_the_planned_rate_is_preserved_exactly(self):
        for mbit in (1.5, 0.5, 5, 3.0, 15, 2.5):
            value, metric = SHAPER.bandwidth_fields(mbit)
            as_mbit = value if metric == "Mbit" else value / 1000
            self.assertAlmostEqual(as_mbit, float(mbit), places=6)

    def test_every_preset_reaches_the_plan_representably(self):
        """The regression: a preset must survive planning, not just rate resolution."""
        for name in SHAPER.RESOLUTION_PRESETS:
            plan = SHAPER.build_plan([{"service": "netflix", "resolution": name}], MAPPINGS)
            self.assertTrue(plan["pipes"], f"{name} produced no pipe")
            entry = plan["pipes"][0]
            self.assertIsInstance(entry["bandwidth"], int, f"{name} is not integral")
            self.assertGreaterEqual(entry["bandwidth"], 1)
            self.assertIn(entry["bandwidth_metric"], ("Mbit", "Kbit"))

    def test_device_plan_carries_integral_rates_for_both_directions(self):
        plan = SHAPER.build_device_plan(
            [{"device": "192.168.1.32", "mbit": 1.5, "upload_mbit": 0.5}], DEVICES)
        entry = plan["device_pipes"][0]
        self.assertEqual((entry["bandwidth"], entry["bandwidth_metric"]), (1500, "Kbit"))
        self.assertEqual((entry["upload_bandwidth"], entry["upload_bandwidth_metric"]),
                         (500, "Kbit"))

    def test_a_download_only_device_limit_has_no_upload_bandwidth(self):
        plan = SHAPER.build_device_plan([{"device": "192.168.1.40", "mbit": 6}], DEVICES)
        entry = plan["device_pipes"][0]
        self.assertEqual((entry["bandwidth"], entry["bandwidth_metric"]), (6, "Mbit"))
        self.assertIsNone(entry["upload_bandwidth"])


class InterceptionTests(unittest.TestCase):
    def test_zenarmor_holding_netmap_is_detected_and_named(self):
        state = SHAPER.netmap_interception(FSTAT_ZENARMOR, device_present=True)
        self.assertTrue(state["active"])
        self.assertEqual(state["engine"], "Zenarmor")
        self.assertEqual(state["processes"], ["eastpect"])
        self.assertIn("upload", state["reason"].lower())

    def test_a_log_path_containing_the_word_is_not_a_holder(self):
        """The device must appear as its own field, not inside a filename."""
        state = SHAPER.netmap_interception(FSTAT_CLEAN, device_present=True)
        self.assertFalse(state["active"])

    def test_absent_device_means_no_interception(self):
        state = SHAPER.netmap_interception(FSTAT_ZENARMOR, device_present=False)
        self.assertFalse(state["active"])

    def test_detection_fails_open_when_fstat_is_unreadable(self):
        state = SHAPER.netmap_interception("", device_present=True)
        self.assertFalse(state["active"])


class DeviceLimitTests(unittest.TestCase):
    def test_without_interception_both_directions_are_planned(self):
        plan = SHAPER.build_device_plan(
            [{"device": "e0:8f:4c:8f:a8:d6", "mbit": 3, "upload_mbit": 1}], DEVICES)
        entry = plan["device_pipes"][0]
        self.assertEqual(entry["device"], "192.168.1.32")
        self.assertEqual(entry["mbit"], 3)
        self.assertEqual(entry["upload_mbit"], 1)
        self.assertIsNotNone(entry["upload_pipe"])
        self.assertEqual(plan["upload_rejected"], [])

    def test_interception_refuses_only_the_upload_half(self):
        """The download cap is measured to work; the upload cap cannot fire."""
        state = SHAPER.netmap_interception(FSTAT_ZENARMOR, device_present=True)
        plan = SHAPER.build_device_plan(
            [{"device": "e0:8f:4c:8f:a8:d6", "mbit": 3, "upload_mbit": 1}],
            DEVICES, interception=state)
        entry = plan["device_pipes"][0]
        self.assertEqual(entry["mbit"], 3, "download must still be capped")
        self.assertIsNone(entry["upload_mbit"])
        self.assertIsNone(entry["upload_pipe"], "no pipe that could never shape anything")
        self.assertEqual(len(plan["upload_rejected"]), 1)
        self.assertIn("Zenarmor", plan["upload_rejected"][0]["reason"])
        self.assertEqual(plan["upload_rejected"][0]["upload_mbit"], 1)

    def test_a_download_only_limit_is_untouched_by_interception(self):
        state = SHAPER.netmap_interception(FSTAT_ZENARMOR, device_present=True)
        plan = SHAPER.build_device_plan([{"device": "192.168.1.40", "mbit": 5}],
                                        DEVICES, interception=state)
        self.assertEqual(plan["device_pipes"][0]["mbit"], 5)
        self.assertEqual(plan["upload_rejected"], [],
                         "nothing was refused because nothing needed the upload path")

    def test_the_firewall_itself_is_never_limited(self):
        plan = SHAPER.build_device_plan([{"device": "192.168.1.32", "mbit": 3}],
                                        DEVICES, router="192.168.1.32")
        self.assertEqual(plan["device_pipes"], [])
        self.assertIn("firewall itself", plan["device_rejected"][0]["reason"])

    def test_one_device_named_twice_gets_one_limit(self):
        plan = SHAPER.build_device_plan(
            [{"device": "192.168.1.32", "mbit": 3},
             {"device": "e0:8f:4c:8f:a8:d6", "mbit": 9}], DEVICES)
        self.assertEqual(len(plan["device_pipes"]), 1)
        self.assertEqual(plan["device_pipes"][0]["mbit"], 3)
        self.assertIn("one device can carry one limit",
                      plan["device_rejected"][0]["reason"])


class VerifyTests(unittest.TestCase):
    def test_counters_are_classified_by_pipe_range(self):
        rows = SHAPER.parse_rule_counters(IPFW_LISTING)
        kinds = {row["pipe"]: row["kind"] for row in rows}
        self.assertEqual(kinds[21000], "service")
        self.assertEqual(kinds[22000], "device-download")
        self.assertEqual(kinds[22500], "device-upload")

    def test_rules_outside_the_plugin_ranges_are_ignored(self):
        rows = SHAPER.parse_rule_counters(IPFW_LISTING)
        self.assertEqual(len(rows), 3, "allow/return rules are not shaper rules")

    def test_byte_counters_are_reported(self):
        rows = {row["pipe"]: row for row in SHAPER.parse_rule_counters(IPFW_LISTING)}
        self.assertEqual(rows[22000]["bytes"], 29096814)
        self.assertEqual(rows[22500]["bytes"], 71152)
        self.assertEqual(rows[22000]["match"], "ip from any to 192.168.1.32 out via em0",
                         "the uuid comment is noise for a reader")

    def test_verify_flags_a_rule_that_has_matched_nothing(self):
        listing = "60002 0 0 pipe 22500 ip from 192.168.1.32 to any in via em0 // x\n"
        result = SHAPER.verify(listing, interception={"active": False})
        self.assertEqual(result["idle"], [22500])

    def test_verify_explains_that_an_idle_upload_rule_is_expected_here(self):
        state = SHAPER.netmap_interception(FSTAT_ZENARMOR, device_present=True)
        result = SHAPER.verify(IPFW_LISTING, interception=state)
        self.assertEqual(result["status"], "ok")
        self.assertIn("expected for upload rules", result["note"])


if __name__ == "__main__":
    unittest.main()
