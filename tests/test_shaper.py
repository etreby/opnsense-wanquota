"""Per-service bandwidth limits: plan building, and what it refuses.

The refusals matter as much as the plan. Capping a shared CDN would throttle
unrelated traffic, and a cap with no matching addresses is a limit that silently
does nothing, so both are reported rather than quietly accepted.
"""

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
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


class CatalogueCoverageTests(unittest.TestCase):
    """A domain the app classifier assigns to a service must be cappable as that service.

    The classifier and the shaper catalogue are separate lists, and they drifted. Netflix
    was classified on nflxext.com while the shaper did not know it, so addresses carrying
    nothing but Netflix names were excluded as shared and the cap missed them: measured on
    a live network the cappable set went 27 to 29 to 31 as nflxso.net and nflxext.com were
    added.
    """

    # Divergences that are deliberate. fbcdn.net carries both Facebook and Instagram
    # media, so it is its own service; folding it into Facebook would quietly cap
    # Instagram as well.
    INTENTIONAL = {("Facebook", "fbcdn.net")}

    def test_no_classified_domain_is_missing_from_its_service(self):
        import importlib.util
        from pathlib import Path
        source = Path(__file__).parents[1] / "src/opnsense/scripts/OPNsense/WanQuota/intelligence.py"
        spec = importlib.util.spec_from_file_location("wq_intel_cov", source)
        intel = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(intel)
        by_label = {entry["label"]: set(entry["suffixes"]) | set(entry.get("co_delivery", ()))
                    for entry in SHAPER.STREAMING_SERVICES.values()}
        gaps = []
        for app, suffixes in intel.APP_DEFINITIONS.items():
            if app not in by_label:
                continue
            for suffix in suffixes:
                if suffix in by_label[app] or SHAPER.is_shared_cdn(suffix):
                    continue
                if (app, suffix) in self.INTENTIONAL:
                    continue
                gaps.append(f"{app} is classified on {suffix} but cannot be capped on it")
        self.assertEqual(gaps, [], "; ".join(gaps))

    def test_the_netflix_open_connect_domains_are_covered(self):
        suffixes = SHAPER.STREAMING_SERVICES["netflix"]["suffixes"]
        for domain in ("nflxso.net", "nflxext.com", "nflxvideo.net"):
            self.assertIn(domain, suffixes)


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


class VerifyFreshnessTests(unittest.TestCase):
    """A zero counter means two very different things.

    Applying reloads the shaper, which resets every ipfw counter. Verify run just
    after saving therefore reported every rule as having matched nothing, which reads
    as the limits being broken when it only means no traffic has arrived yet. That is
    exactly what a user saw after adding a device limit.
    """

    LISTING = ("60001 0 0 pipe 21015 ip from table(__rule__abc__source) to any out via em0\n"
               "60002 2 640 pipe 22001 ip from any to 192.168.1.30 out via em0\n")
    PLAN = {"pipes": [{"pipe": 21015, "service": "youtube", "label": "YouTube"}],
            "device_pipes": [{"pipe": 22001, "device": "192.168.1.30", "name": "Living room TV",
                              "upload_pipe": None}]}

    def test_a_fresh_install_says_nothing_yet_rather_than_nothing(self):
        result = SHAPER.verify(self.LISTING, interception={"active": False},
                               plan=self.PLAN, age=12)
        self.assertTrue(result["settling"])
        self.assertEqual(result["installed_seconds_ago"], 12)
        self.assertIn("no traffic yet", result["note"])

    def test_a_settled_install_draws_the_stronger_conclusion(self):
        result = SHAPER.verify(self.LISTING, interception={"active": False},
                               plan=self.PLAN, age=4000)
        self.assertFalse(result["settling"])
        self.assertIn("is not limiting anything", result["note"])

    def test_the_boundary_is_the_settling_window(self):
        for age, settling in ((SHAPER.SETTLING_SECONDS - 1, True),
                              (SHAPER.SETTLING_SECONDS, False)):
            result = SHAPER.verify(self.LISTING, interception={"active": False},
                                   plan=self.PLAN, age=age)
            self.assertEqual(result["settling"], settling, age)

    def test_rules_are_labelled_with_something_a_person_recognises(self):
        """The match text is an ipfw table built from a uuid, which names nothing."""
        rows = {row["pipe"]: row for row in
                SHAPER.verify(self.LISTING, interception={"active": False},
                              plan=self.PLAN, age=10)["rules"]}
        self.assertEqual(rows[21015]["label"], "YouTube")
        self.assertEqual(rows[22001]["label"], "Living room TV")

    def test_an_unknown_pipe_gets_an_empty_label_not_a_crash(self):
        listing = "60001 0 0 pipe 21099 ip from any to any out via em0\n"
        rows = SHAPER.verify(listing, interception={"active": False},
                             plan=self.PLAN, age=10)["rules"]
        self.assertEqual(rows[0]["label"], "")

    def test_a_missing_marker_reads_as_unknown_age(self):
        self.assertIsNone(SHAPER.installed_age("/nonexistent/wanquota-installed"))

    def test_an_unknown_age_does_not_claim_the_counters_are_fresh(self):
        result = SHAPER.verify(self.LISTING, interception={"active": False},
                               plan=self.PLAN, age=None)
        self.assertFalse(result["settling"],
                         "with no timestamp, do not excuse a zero as too early")

    def test_the_age_is_read_from_the_marker_file(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = os.path.join(folder, "shaper-installed")
            open(marker, "w").close()
            os.utime(marker, (1000, 1000))
            self.assertEqual(SHAPER.installed_age(marker, now=1090), 90)


class CombinedLimitTests(unittest.TestCase):
    """Per-service and per-device limits are not a choice between two modes.

    They occupy separate pipe ranges and separate rules, so both can be in force at
    once. What they are not is additive: with ipfw's one_pass, a packet leaves the
    ruleset at the first pipe it matches, and service rules are sequenced ahead of
    device rules. So YouTube traffic to a capped device is held to the *service* rate,
    and the device cap governs everything else that device does.
    """

    DEVICES = [{"address": "192.168.1.32", "name": "Desktop",
                "mac": "e0:8f:4c:8f:a8:d6", "hostname": "desktop"}]

    def combined(self):
        plan = SHAPER.build_plan([{"service": "netflix", "mbit": 5}], MAPPINGS)
        plan.update(SHAPER.build_device_plan(
            [{"device": "e0:8f:4c:8f:a8:d6", "mbit": 20}], self.DEVICES))
        return plan

    def test_both_kinds_of_limit_survive_in_one_plan(self):
        plan = self.combined()
        self.assertEqual(len(plan["pipes"]), 1, "the service cap is still planned")
        self.assertEqual(len(plan["device_pipes"]), 1, "the device cap is still planned")

    def test_their_pipe_numbers_cannot_collide(self):
        plan = self.combined()
        service = {entry["pipe"] for entry in plan["pipes"]}
        device = {entry["pipe"] for entry in plan["device_pipes"]}
        self.assertEqual(service & device, set())
        self.assertTrue(all(number < SHAPER.DEVICE_PIPE_BASE for number in service))
        self.assertTrue(all(number >= SHAPER.DEVICE_PIPE_BASE for number in device))

    def test_the_service_rule_is_sequenced_first(self):
        """Precedence, not addition: the more specific limit governs its own traffic."""
        plan = self.combined()
        self.assertLess(max(entry["pipe"] for entry in plan["pipes"]),
                        min(entry["pipe"] for entry in plan["device_pipes"]))

    def test_the_fingerprint_covers_both_so_either_edit_re_applies(self):
        plan = self.combined()
        before = SHAPER.plan_fingerprint(plan)
        widened = json.loads(json.dumps(plan))
        widened["device_pipes"][0]["bandwidth"] = 30
        self.assertTrue(SHAPER.needs_apply(widened, before))
        retimed = json.loads(json.dumps(plan))
        retimed["pipes"][0]["bandwidth"] = 9
        self.assertTrue(SHAPER.needs_apply(retimed, before))


class PrefixTests(unittest.TestCase):
    """Capping a whole delivery block where the evidence supports it.

    Individual addresses cannot keep up with YouTube: it hands out per-session cache
    nodes, so a cap can hold one node while the player moves to another that has never
    been resolved through this firewall. These fixtures are the real shape of a live
    network — an ISP-hosted Google cache in a dedicated /24, and Google's general
    front-ends sharing a /24 with Search, ads and analytics.
    """

    # 41.91.253.0/24 on the live network: nothing but Google video delivery.
    DEDICATED = [
        ("rr4.sn-vg5obxxb-j5pk.googlevideo.com", "41.91.253.47"),
        ("rr4.sn-vg5obxxb-j5pk.gvt1.com", "41.91.253.47"),
        ("rr3.sn-vg5obxxb-j5pk.googlevideo.com", "41.91.253.52"),
        ("rr1.sn-vg5obxxb-j5pk.gvt1.com", "41.91.253.61"),
    ]
    # 142.251.27.0/24: video hostnames alongside Search, ads and analytics.
    MIXED = [
        ("rr1.googlevideo.com", "142.251.27.100"),
        ("www.google.com", "142.251.27.101"),
        ("doubleclick.net", "142.251.27.102"),
        ("googleapis.com", "142.251.27.103"),
    ]

    def prefixes(self, mappings):
        return SHAPER.safe_prefixes(("googlevideo.com", "youtube.com", "ytimg.com"),
                                    ("gvt1.com",), mappings)

    def test_a_dedicated_block_is_offered(self):
        found = self.prefixes(self.DEDICATED)
        self.assertIn("41.91.253.0/24", found)
        self.assertEqual(found["41.91.253.0/24"]["addresses"], 3)
        self.assertEqual(found["41.91.253.0/24"]["domains"], ["googlevideo.com", "gvt1.com"])

    def test_a_block_shared_with_search_is_refused(self):
        """Capping this would throttle Search and ordinary browsing."""
        self.assertEqual(self.prefixes(self.MIXED), {})

    def test_one_observation_is_not_evidence_of_a_whole_block(self):
        single = [("rr1.googlevideo.com", "203.0.113.10")]
        self.assertEqual(self.prefixes(single), {})

    def test_a_prefix_replaces_the_addresses_inside_it(self):
        """The rule must not carry the same traffic twice."""
        matches = SHAPER.collapse_into_prefixes(
            ["41.91.253.47", "41.91.253.52", "8.8.4.4"], {"41.91.253.0/24": {}})
        self.assertEqual(matches, ["41.91.253.0/24", "8.8.4.4"])

    def test_addresses_outside_any_safe_prefix_are_kept(self):
        matches = SHAPER.collapse_into_prefixes(["198.51.100.7"], {})
        self.assertEqual(matches, ["198.51.100.7"])

    def test_shared_infrastructure_is_never_offered_as_a_prefix(self):
        pairs = [("rr1.googlevideo.com", "203.0.113.10"),
                 ("rr2.googlevideo.com", "203.0.113.11"),
                 ("d1.cloudfront.net", "203.0.113.12")]
        self.assertEqual(self.prefixes(pairs), {})

    def test_the_plan_installs_the_prefix_and_reports_it(self):
        plan = SHAPER.build_plan([{"service": "youtube", "resolution": "audio_only"}],
                                 self.DEDICATED)
        entry = plan["pipes"][0]
        self.assertEqual(entry["prefixes"], ["41.91.253.0/24"])
        self.assertEqual(entry["addresses"], ["41.91.253.0/24"],
                         "the block replaces its individual addresses")
        # Two different counts, both correct: 2 addresses were observed under a
        # YouTube hostname, while the block itself holds 3 known addresses.
        self.assertEqual(entry["address_count"], 2)
        self.assertEqual(entry["prefix_evidence"][0]["addresses"], 3)

    def test_a_co_delivery_only_address_is_not_a_video_address_but_is_covered(self):
        """41.91.253.61 was seen only under gvt1.com.

        Co-delivery stops such a name excluding an address; it does not make an
        address that carries nothing else into a YouTube address. It is still inside
        the capped block, which is the point of capping the block and is why
        also_limits is reported.
        """
        exclusive, _shared, _incidental = SHAPER.service_addresses(
            ("googlevideo.com",), self.DEDICATED, co_delivery=("gvt1.com",))
        self.assertNotIn("41.91.253.61", exclusive)
        found = self.prefixes(self.DEDICATED)
        self.assertIn("41.91.253.0/24", found)

    def test_a_mixed_block_leaves_individual_addresses_in_place(self):
        plan = SHAPER.build_plan([{"service": "youtube", "mbit": 3}], self.MIXED)
        entry = plan["pipes"][0]
        self.assertEqual(entry["prefixes"], [])
        self.assertEqual(entry["addresses"], ["142.251.27.100"],
                         "only the video address, and only as an address")

    def test_an_unresolvable_address_does_not_crash_prefixing(self):
        self.assertIsNone(SHAPER._prefix_of("not-an-address"))
        self.assertIsNone(SHAPER._prefix_of("2001:db8::1"))


class SyncTests(unittest.TestCase):
    """A cap must follow its addresses, and must not re-apply for no reason.

    The running rule matches a snapshot taken when the plan was applied. Measured on
    a live network, a 720p YouTube stream ran untouched past a 0.5 Mbit cap because
    it used a cache node learned after the last apply. Applying rewrites the
    configuration and reloads services, so it has to happen when the shaped set
    changes and not otherwise.
    """

    def plan(self, addresses, mbit=3, status="ok"):
        return {"status": status, "dry_run": False,
                "pipes": [{"service": "youtube", "bandwidth": mbit,
                           "bandwidth_metric": "Mbit", "addresses": list(addresses)}],
                "device_pipes": []}

    def test_a_new_address_requires_applying(self):
        before = SHAPER.plan_fingerprint(self.plan(["1.1.1.1"]))
        self.assertTrue(SHAPER.needs_apply(self.plan(["1.1.1.1", "2.2.2.2"]), before))

    def test_an_unchanged_set_does_not(self):
        before = SHAPER.plan_fingerprint(self.plan(["1.1.1.1", "2.2.2.2"]))
        self.assertFalse(SHAPER.needs_apply(self.plan(["2.2.2.2", "1.1.1.1"]), before),
                         "order must not count as a change")

    def test_a_rate_change_requires_applying(self):
        before = SHAPER.plan_fingerprint(self.plan(["1.1.1.1"], mbit=3))
        self.assertTrue(SHAPER.needs_apply(self.plan(["1.1.1.1"], mbit=5), before))

    def test_becoming_disabled_requires_applying_so_the_limit_is_released(self):
        before = SHAPER.plan_fingerprint(self.plan(["1.1.1.1"]))
        after = {"status": "disabled", "pipes": [], "device_pipes": []}
        self.assertTrue(SHAPER.needs_apply(after, before))

    def test_switching_to_dry_run_requires_applying(self):
        before = SHAPER.plan_fingerprint(self.plan(["1.1.1.1"]))
        after = self.plan(["1.1.1.1"])
        after["dry_run"] = True
        self.assertTrue(SHAPER.needs_apply(after, before))

    def test_a_device_limit_change_requires_applying(self):
        base = {"status": "ok", "dry_run": False, "pipes": [],
                "device_pipes": [{"device": "192.168.1.32", "bandwidth": 3,
                                  "bandwidth_metric": "Mbit", "upload_bandwidth": None,
                                  "upload_bandwidth_metric": None}]}
        before = SHAPER.plan_fingerprint(base)
        changed = json.loads(json.dumps(base))
        changed["device_pipes"][0]["bandwidth"] = 6
        self.assertTrue(SHAPER.needs_apply(changed, before))

    def test_a_failed_apply_is_not_recorded_so_it_is_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "applied.json")
            SHAPER.write_applied("something-old", path)
            SHAPER.run = lambda: self.plan(["9.9.9.9"])
            result = SHAPER.sync(applied_path=path,
                                 runner=lambda: {"ok": False, "detail": "boom"})
            self.assertEqual(result["status"], "failed")
            self.assertEqual(SHAPER.read_applied(path), "something-old",
                             "a failed apply must not be recorded as applied")

    def test_a_successful_apply_is_recorded_and_not_repeated(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "applied.json")
            document = self.plan(["9.9.9.9"])
            SHAPER.run = lambda: document
            calls = []
            first = SHAPER.sync(applied_path=path,
                                runner=lambda: (calls.append(1), {"ok": True})[1])
            self.assertTrue(first["applied"])
            second = SHAPER.sync(applied_path=path,
                                 runner=lambda: (calls.append(1), {"ok": True})[1])
            self.assertFalse(second["applied"], "an unchanged plan must not re-apply")
            self.assertEqual(len(calls), 1)

    def test_a_missing_record_reads_as_absent_not_as_a_crash(self):
        self.assertIsNone(SHAPER.read_applied("/nonexistent/path/applied.json"))


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
