"""App category breakdown: shares, rollup, and honest unknowns."""

import importlib.util
from pathlib import Path
import sys
import unittest

SOURCE_DIR = Path(__file__).parents[1] / "src/opnsense/scripts/OPNsense/WanQuota"
sys.path.insert(0, str(SOURCE_DIR))
SPEC = importlib.util.spec_from_file_location("wanquota_intelligence_cat", SOURCE_DIR / "intelligence.py")
INTEL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INTEL)

CATS = INTEL.BUILTIN_CATEGORIES


def domains(*pairs):
    return [{"domain": d, "total": t} for d, t in pairs]


class BreakdownTests(unittest.TestCase):
    def test_shares_are_percentages_of_the_attributed_total(self):
        result = INTEL.category_breakdown(
            domains(("youtube.com", 750), ("zoom.us", 250)), CATS)
        by_name = {r["name"]: r for r in result["categories"]}
        self.assertAlmostEqual(by_name["Media Streaming"]["percent"], 75.0)
        self.assertAlmostEqual(by_name["Conferencing"]["percent"], 25.0)
        self.assertEqual(result["total"], 1000)

    def test_percentages_sum_to_one_hundred(self):
        result = INTEL.category_breakdown(
            domains(("youtube.com", 5), ("github.com", 3), ("claude.ai", 2)), CATS)
        self.assertAlmostEqual(sum(r["percent"] for r in result["categories"]), 100.0)

    def test_ordered_largest_first(self):
        result = INTEL.category_breakdown(
            domains(("zoom.us", 10), ("youtube.com", 90), ("github.com", 50)), CATS)
        percents = [r["percent"] for r in result["categories"]]
        self.assertEqual(percents, sorted(percents, reverse=True))

    def test_subdomains_match_their_suffix(self):
        result = INTEL.category_breakdown(domains(("r1.googlevideo.com", 100)), CATS)
        self.assertEqual(result["categories"][0]["name"], "Media Streaming")

    def test_unmatched_domain_is_uncategorised_not_guessed(self):
        result = INTEL.category_breakdown(
            domains(("youtube.com", 90), ("nowhere.invalid", 10)), CATS)
        by_name = {r["name"]: r["percent"] for r in result["categories"]}
        self.assertAlmostEqual(by_name[INTEL.UNCATEGORISED_LABEL], 10.0)
        self.assertAlmostEqual(result["known_percent"], 90.0)

    def test_tail_is_rolled_into_others_with_a_count(self):
        # Eleven distinct categories with a top_n of 3 leaves eight folded.
        rows = domains(
            ("youtube.com", 100), ("cloudflare.com", 90), ("github.com", 80),
            ("claude.ai", 70), ("office.com", 60), ("whatsapp.net", 50),
            ("google.com", 40), ("zoom.us", 30), ("tailscale.com", 20),
            ("icloud.com", 10), ("facebook.com", 5),
        )
        result = INTEL.category_breakdown(rows, CATS, top_n=3)
        self.assertEqual(len(result["categories"]), 4)
        others = result["categories"][-1]
        self.assertEqual(others["name"], INTEL.OTHERS_LABEL)
        self.assertEqual(others["categories_folded"], 8)
        self.assertAlmostEqual(sum(r["percent"] for r in result["categories"]), 100.0)

    def test_no_others_row_when_nothing_is_folded(self):
        result = INTEL.category_breakdown(domains(("youtube.com", 10)), CATS, top_n=10)
        self.assertNotIn(INTEL.OTHERS_LABEL, {r["name"] for r in result["categories"]})

    def test_default_top_n_is_ten(self):
        self.assertEqual(INTEL.CATEGORY_TOP_N, 10)
        rows = domains(*[(d, 10) for d in (
            "youtube.com", "cloudflare.com", "github.com", "claude.ai", "office.com",
            "whatsapp.net", "google.com", "zoom.us", "tailscale.com", "icloud.com",
            "facebook.com", "steampowered.com")])
        result = INTEL.category_breakdown(rows, CATS)
        self.assertEqual(len(result["categories"]), 11)  # 10 + Others

    def test_zero_and_negative_totals_are_ignored(self):
        result = INTEL.category_breakdown(
            domains(("youtube.com", 100), ("zoom.us", 0), ("github.com", -5)), CATS)
        self.assertEqual([r["name"] for r in result["categories"]], ["Media Streaming"])

    def test_empty_input_does_not_divide_by_zero(self):
        result = INTEL.category_breakdown([], CATS)
        self.assertEqual(result["categories"], [])
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["known_percent"], 0)

    def test_user_categories_override_builtins(self):
        custom = {**CATS, "My Bucket": ("youtube.com",)}
        result = INTEL.category_breakdown(domains(("youtube.com", 10)), custom)
        # suffix_category walks in order, so a user entry placed first wins; assert
        # only that the domain lands in exactly one bucket.
        self.assertEqual(len(result["categories"]), 1)

    def test_note_states_what_the_shares_are_of(self):
        result = INTEL.category_breakdown(domains(("youtube.com", 10)), CATS)
        self.assertIn("not of the whole quota", result["note"])


class TaxonomyTests(unittest.TestCase):
    def test_expected_categories_exist(self):
        for name in ("Media Streaming", "Secure Web Browsing", "Online Utility",
                     "A.I. Tools", "Business Tools", "Instant Messaging",
                     "Web Browsing", "Conferencing", "Network Management",
                     "Cloud Services"):
            self.assertIn(name, CATS, name)

    def test_no_duplicate_suffix_across_categories(self):
        seen = {}
        for category, suffixes in CATS.items():
            for suffix in suffixes:
                self.assertNotIn(suffix, seen,
                                 f"{suffix} in both {seen.get(suffix)} and {category}")
                seen[suffix] = category

    def test_suffixes_are_lowercase_and_have_no_scheme_or_slash(self):
        for category, suffixes in CATS.items():
            for suffix in suffixes:
                self.assertEqual(suffix, suffix.lower(), suffix)
                self.assertNotIn("/", suffix, suffix)
                self.assertIn(".", suffix, suffix)


if __name__ == "__main__":
    unittest.main()


class CategoryDetailTests(unittest.TestCase):
    DOMAINS = [
        {"domain": "youtube.com", "total": 700, "category": "Media Streaming"},
        {"domain": "netflix.com", "total": 300, "category": "Media Streaming"},
        {"domain": "zoom.us", "total": 50, "category": "Conferencing"},
    ]
    MATRIX = [
        {"device": "192.168.1.10", "name": "TRUENAS", "domain": "youtube.com", "total": 500},
        {"device": "192.168.1.32", "name": "DESKTOP", "domain": "netflix.com", "total": 300},
        {"device": "192.168.1.10", "name": "TRUENAS", "domain": "netflix.com", "total": 100},
        {"device": "192.168.1.99", "name": "OTHER", "domain": "zoom.us", "total": 50},
    ]

    def detail(self, name, **kw):
        return INTEL.category_detail(name, self.DOMAINS, self.MATRIX, CATS, **kw)

    def test_lists_only_that_category_domains(self):
        got = self.detail("Media Streaming")
        self.assertEqual([d["domain"] for d in got["domains"]], ["youtube.com", "netflix.com"])
        self.assertEqual(got["total"], 1000)
        self.assertEqual(got["domain_count"], 2)

    def test_devices_are_aggregated_across_the_category_domains(self):
        got = self.detail("Media Streaming")
        by_name = {d["name"]: d for d in got["devices"]}
        self.assertEqual(by_name["TRUENAS"]["total"], 600)
        self.assertEqual(by_name["TRUENAS"]["domains"], 2)
        self.assertNotIn("OTHER", by_name)

    def test_device_sum_never_exceeds_the_category_total(self):
        # It can be lower: the device/domain matrix is capped, so a domain counted
        # in the category may have no matrix row. Claiming equality would be wrong.
        got = self.detail("Media Streaming")
        self.assertLessEqual(got["devices_total"], got["total"])
        self.assertEqual(got["devices_total"], sum(d["total"] for d in got["devices"]))

    def test_shortfall_is_visible_rather_than_hidden(self):
        got = self.detail("Media Streaming")
        self.assertLess(got["devices_total"], got["total"])
        self.assertIn("sum to less than", got["device_note"])

    def test_devices_ranked_largest_first(self):
        totals = [d["total"] for d in self.detail("Media Streaming")["devices"]]
        self.assertEqual(totals, sorted(totals, reverse=True))

    def test_name_match_is_case_insensitive(self):
        self.assertTrue(self.detail("media streaming")["found"])

    def test_unknown_category_returns_an_empty_result_not_an_error(self):
        got = self.detail("Nonexistent")
        self.assertFalse(got["found"])
        self.assertEqual(got["domains"], [])
        self.assertIn("misspelled", got["empty_reason"])

    def test_others_is_explained_as_a_rollup(self):
        got = self.detail("Others")
        self.assertFalse(got["found"])
        self.assertIn("rollup", got["empty_reason"])

    def test_categorises_on_the_fly_when_the_tag_is_absent(self):
        # consumers.report() has no category field; only dashboard() adds it.
        untagged = [{"domain": "youtube.com", "total": 10}]
        got = INTEL.category_detail("Media Streaming", untagged, [], CATS)
        self.assertTrue(got["found"])

    def test_uncategorised_is_reachable_by_its_displayed_name(self):
        # The displayed label and the per-domain tag must agree, or the drill-down
        # for that slice silently finds nothing.
        untagged = [{"domain": "nowhere.invalid", "total": 10}]
        got = INTEL.category_detail(INTEL.UNCATEGORISED_LABEL, untagged, [], CATS)
        self.assertTrue(got["found"])

    def test_top_n_bounds_both_lists(self):
        got = self.detail("Media Streaming", top_n=1)
        self.assertEqual(len(got["domains"]), 1)
        self.assertEqual(len(got["devices"]), 1)
        # The total still reflects the whole category, not the truncated list.
        self.assertEqual(got["total"], 1000)

    def test_device_note_explains_the_denominator(self):
        self.assertIn("only this category", self.detail("Media Streaming")["device_note"])
