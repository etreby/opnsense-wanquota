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
        got, _ = SHAPER.service_addresses(("nflxvideo.net",), MAPPINGS)
        self.assertEqual(got, ["198.51.100.10", "198.51.100.11"])

    def test_unrelated_domains_are_not_matched(self):
        got, _ = SHAPER.service_addresses(("nflxvideo.net",), MAPPINGS)
        self.assertNotIn("203.0.113.99", got)

    def test_result_is_sorted_and_deduplicated(self):
        pairs = MAPPINGS + [("a.nflxvideo.net", "198.51.100.10")]
        got, _ = SHAPER.service_addresses(("nflxvideo.net",), pairs)
        self.assertEqual(got, sorted(set(got)))

    def test_no_mappings_yields_nothing(self):
        self.assertEqual(SHAPER.service_addresses(("nflxvideo.net",), []), ([], {}))

    def test_address_shared_with_another_service_is_excluded(self):
        # Observed on real data: a third of Netflix's addresses also served
        # amazonaws.com. Capping those throttles unrelated traffic.
        pairs = [("nflxvideo.net", "198.51.100.10"),
                 ("netflix.com", "198.51.100.50"),
                 ("amazonaws.com", "198.51.100.50")]
        exclusive, shared = SHAPER.service_addresses(("nflxvideo.net", "netflix.com"), pairs)
        self.assertEqual(exclusive, ["198.51.100.10"])
        self.assertIn("198.51.100.50", shared)
        self.assertIn("amazonaws.com", shared["198.51.100.50"])

    def test_two_hostnames_of_the_same_service_do_not_count_as_sharing(self):
        pairs = [("nflxvideo.net", "198.51.100.10"), ("netflix.com", "198.51.100.10")]
        exclusive, shared = SHAPER.service_addresses(("nflxvideo.net", "netflix.com"), pairs)
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


if __name__ == "__main__":
    unittest.main()
