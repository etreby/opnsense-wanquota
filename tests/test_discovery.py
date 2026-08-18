"""Finding services the catalog does not know yet.

The value of this feature is that an accepted candidate becomes cappable, so the tests
care about two things above all: that a candidate is never applied on its own, and that
what it claims about cappability is true before someone acts on it.
"""

import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

SOURCE_DIR = Path(__file__).parents[1] / "src/opnsense/scripts/OPNsense/WanQuota"
sys.path.insert(0, str(SOURCE_DIR))
SPEC = importlib.util.spec_from_file_location("wanquota_discovery", SOURCE_DIR / "discovery.py")
DISCOVERY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DISCOVERY)

MB = 1024 * 1024

# The shape real data takes: several hostnames under one registrable domain, each with
# its own addresses.
MAPPINGS = [
    ("g.whatsapp.net", "31.13.66.52"),
    ("mmg.whatsapp.net", "31.13.66.53"),
    ("media.viber.com", "198.51.100.20"),
    ("cdn.viber.com", "198.51.100.21"),
    ("gw.snapchat.com", "203.0.113.30"),
    ("feelinsonice.appspot.com", "203.0.113.31"),
    ("ipv4-c001.ix.nflxvideo.net", "198.51.100.10"),
    ("something.internal.invalid", "10.0.0.5"),
]
TOTALS = [
    {"domain": "g.whatsapp.net", "total": 40 * MB},
    {"domain": "mmg.whatsapp.net", "total": 20 * MB},
    {"domain": "media.viber.com", "total": 120 * MB},
    {"domain": "gw.snapchat.com", "total": 8 * MB},
    {"domain": "something.internal.invalid", "total": 1 * MB},
]


def fresh_db():
    handle = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    handle.close()
    os.unlink(handle.name)
    return DISCOVERY.database(handle.name), handle.name


class CandidateTests(unittest.TestCase):
    def found(self, **kwargs):
        options = {"mappings": MAPPINGS, "domain_totals": TOTALS, "minimum_bytes": 5 * MB,
                   "now": 1000}
        options.update(kwargs)
        return DISCOVERY.candidates(options["mappings"], options["domain_totals"],
                                    minimum_bytes=options["minimum_bytes"],
                                    now=options["now"])

    def test_an_unknown_service_with_real_traffic_is_proposed(self):
        names = {item["domain"] for item in self.found()}
        self.assertIn("viber.com", names)

    def test_a_service_already_in_the_catalog_is_not_proposed(self):
        """Netflix is catalogued, so its traffic is not a discovery."""
        names = {item["domain"] for item in self.found()}
        self.assertNotIn("nflxvideo.net", names)

    def test_something_the_app_classifier_already_names_is_not_proposed(self):
        """WhatsApp is in APP_DEFINITIONS, so it is known even if it cannot be capped."""
        names = {item["domain"] for item in self.found()}
        self.assertNotIn("whatsapp.net", names)

    def test_a_trickle_is_not_evidence_of_a_service(self):
        names = {item["domain"] for item in self.found()}
        self.assertNotIn("internal.invalid", names)

    def test_a_recognised_domain_gets_its_proper_name(self):
        viber = next(i for i in self.found() if i["domain"] == "viber.com")
        self.assertEqual(viber["label"], "Viber")
        self.assertEqual(viber["category"], "Messaging")
        self.assertEqual(viber["named_from"], "known domain")

    def test_an_unrecognised_domain_is_named_after_itself_and_says_so(self):
        pairs = [("cdn.example-thing.test", "198.51.100.90"),
                 ("api.example-thing.test", "198.51.100.91")]
        totals = [{"domain": "cdn.example-thing.test", "total": 50 * MB}]
        found = self.found(mappings=pairs, domain_totals=totals)
        item = next(i for i in found if i["domain"] == "example-thing.test")
        self.assertEqual(item["label"], "example-thing.test")
        self.assertEqual(item["category"], "Unclassified")
        self.assertIn("all the evidence supports", item["named_from"])

    def test_candidates_are_ranked_by_traffic(self):
        found = self.found()
        amounts = [item["bytes_seen"] for item in found]
        self.assertEqual(amounts, sorted(amounts, reverse=True))

    def test_each_candidate_states_whether_it_could_be_capped(self):
        for item in self.found():
            self.assertIn("cappable", item)
            self.assertIsInstance(item["cappable"], bool)

    def test_a_candidate_on_shared_infrastructure_is_not_claimed_cappable(self):
        pairs = [("assets.cloudfront.net", "203.0.113.70"),
                 ("other.cloudfront.net", "203.0.113.71")]
        totals = [{"domain": "assets.cloudfront.net", "total": 90 * MB}]
        found = self.found(mappings=pairs, domain_totals=totals)
        item = next(i for i in found if i["domain"] == "cloudfront.net")
        self.assertFalse(item["cappable"],
                         "capping a shared CDN would throttle unrelated traffic")


class OwnershipTests(unittest.TestCase):
    """A new domain on a known service's machines is a new URL, not a new service."""

    def test_a_domain_sharing_a_services_addresses_is_attributed_to_it(self):
        mappings = [("ipv4-c001.ix.nflxvideo.net", "198.51.100.10"),
                    ("ipv4-c002.ix.nflxvideo.net", "198.51.100.11"),
                    ("new-delivery.example-nflx.test", "198.51.100.10"),
                    ("also.example-nflx.test", "198.51.100.11")]
        owner = DISCOVERY.owning_service({"198.51.100.10", "198.51.100.11"}, mappings)
        self.assertEqual(owner, "netflix")

    def test_an_unrelated_domain_is_attributed_to_nothing(self):
        mappings = [("ipv4-c001.ix.nflxvideo.net", "198.51.100.10"),
                    ("media.viber.com", "203.0.113.99")]
        self.assertEqual(DISCOVERY.owning_service({"203.0.113.99"}, mappings), "")

    def test_no_addresses_attributes_to_nothing(self):
        self.assertEqual(DISCOVERY.owning_service(set(), []), "")


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.connection, self.path = fresh_db()

    def tearDown(self):
        self.connection.close()
        os.unlink(self.path)

    def sample(self, domain="viber.com", **kwargs):
        item = {"domain": domain, "label": "Viber", "category": "Messaging",
                "named_from": "known domain", "hostnames": ["media.viber.com"],
                "hostname_count": 1, "addresses": 2, "shared": 0, "cappable": True,
                "belongs_to": "", "bytes_seen": 100, "first_seen": 1, "last_seen": 1}
        item.update(kwargs)
        return item

    def test_a_candidate_starts_as_new_and_is_never_applied_by_itself(self):
        DISCOVERY.record([self.sample()], self.connection)
        row = DISCOVERY.listing(connection=self.connection)[0]
        self.assertEqual(row["status"], "new")
        self.assertEqual(DISCOVERY.accepted_services(self.connection), {},
                         "nothing is shapeable until a person accepts it")

    def test_accepting_makes_it_a_cappable_service(self):
        DISCOVERY.record([self.sample()], self.connection)
        DISCOVERY.set_status("viber.com", "accepted", self.connection)
        services = DISCOVERY.accepted_services(self.connection)
        self.assertEqual(list(services), ["viber_com"])
        self.assertEqual(services["viber_com"]["label"], "Viber")
        self.assertEqual(services["viber_com"]["suffixes"], ("viber.com",))
        self.assertTrue(services["viber_com"]["discovered"])

    def test_an_ignored_candidate_does_not_come_back_on_the_next_scan(self):
        """A discovery feature that nags is one that gets switched off."""
        DISCOVERY.record([self.sample()], self.connection)
        DISCOVERY.set_status("viber.com", "ignored", self.connection)
        DISCOVERY.record([self.sample(bytes_seen=999)], self.connection)
        row = DISCOVERY.listing(connection=self.connection)[0]
        self.assertEqual(row["status"], "ignored")
        self.assertEqual(row["bytes_seen"], 999, "evidence still refreshes")
        self.assertEqual(DISCOVERY.listing("new", self.connection), [])

    def test_rescanning_updates_evidence_without_duplicating(self):
        DISCOVERY.record([self.sample()], self.connection)
        result = DISCOVERY.record([self.sample(bytes_seen=500)], self.connection)
        self.assertEqual(result, {"added": 0, "updated": 1})
        self.assertEqual(len(DISCOVERY.listing(connection=self.connection)), 1)

    def test_an_unknown_domain_cannot_be_accepted(self):
        with self.assertRaises(ValueError):
            DISCOVERY.set_status("never-seen.test", "accepted", self.connection)

    def test_a_nonsense_status_is_refused(self):
        DISCOVERY.record([self.sample()], self.connection)
        with self.assertRaises(ValueError):
            DISCOVERY.set_status("viber.com", "enabled", self.connection)

    def test_a_decision_can_be_reset(self):
        DISCOVERY.record([self.sample()], self.connection)
        DISCOVERY.set_status("viber.com", "ignored", self.connection)
        DISCOVERY.set_status("viber.com", "new", self.connection)
        self.assertEqual(len(DISCOVERY.listing("new", self.connection)), 1)

    def test_hostnames_survive_the_round_trip(self):
        DISCOVERY.record([self.sample(hostnames=["a.viber.com", "b.viber.com"])],
                         self.connection)
        row = DISCOVERY.listing(connection=self.connection)[0]
        self.assertEqual(row["hostnames"], ["a.viber.com", "b.viber.com"])


class SeedTests(unittest.TestCase):
    def test_the_messengers_asked_for_are_recognised(self):
        for domain, label in (("whatsapp.net", "WhatsApp"), ("viber.com", "Viber"),
                              ("telegram.org", "Telegram"), ("snapchat.com", "Snapchat")):
            self.assertEqual(DISCOVERY.SEED_NAMES[domain][0], label)

    def test_no_seed_domain_is_shared_infrastructure(self):
        """Naming something does not make it safe to cap; it must not imply that."""
        import shaper
        for domain in DISCOVERY.SEED_NAMES:
            self.assertFalse(shaper.is_shared_cdn(domain), domain)

    def test_every_seed_entry_has_a_name_and_a_category(self):
        for domain, value in DISCOVERY.SEED_NAMES.items():
            self.assertEqual(len(value), 2, domain)
            self.assertTrue(all(part.strip() for part in value), domain)


if __name__ == "__main__":
    unittest.main()


class InfrastructureTests(unittest.TestCase):
    """CDNs must never be offered as cappable services.

    The first live run of discovery on a real network proposed cloudflare.net as a
    service moving 2.4 GB that could safely be capped. cloudflare.com was in the
    shared-infrastructure list and cloudflare.net — the domain that actually serves the
    content — was not. Capping it would have throttled a large share of the internet.
    These are the domains that run surfaced, ranked by traffic.
    """

    OBSERVED = ("fastly.net", "cloudflare.net", "akamai.net", "cloudfront.net",
                "edgesuite.net", "mcr-msedge.net")

    def test_every_cdn_the_live_run_surfaced_is_recognised(self):
        import shaper
        for domain in self.OBSERVED:
            self.assertTrue(shaper.is_shared_cdn(domain),
                            f"{domain} would be offered as a cappable service")

    def test_a_cdn_candidate_is_flagged_and_not_cappable(self):
        pairs = [("a.cloudflare.net", "198.51.100.1"), ("b.cloudflare.net", "198.51.100.2")]
        totals = [{"domain": "a.cloudflare.net", "total": 2400 * MB}]
        found = DISCOVERY.candidates(pairs, totals, minimum_bytes=5 * MB, now=1)
        item = next(i for i in found if i["domain"] == "cloudflare.net")
        self.assertTrue(item["infrastructure"])
        self.assertFalse(item["cappable"])

    def test_infrastructure_sorts_below_real_candidates_despite_more_traffic(self):
        """A CDN always leads on volume, so volume must not decide the order."""
        pairs = [("a.cloudflare.net", "198.51.100.1"), ("b.cloudflare.net", "198.51.100.2"),
                 ("media.viber.com", "203.0.113.1"), ("cdn.viber.com", "203.0.113.2")]
        totals = [{"domain": "a.cloudflare.net", "total": 2400 * MB},
                  {"domain": "media.viber.com", "total": 100 * MB}]
        found = DISCOVERY.candidates(pairs, totals, minimum_bytes=5 * MB, now=1)
        self.assertEqual(found[0]["domain"], "viber.com")
        self.assertEqual(found[-1]["domain"], "cloudflare.net")

    def test_a_real_service_is_not_flagged_as_infrastructure(self):
        pairs = [("media.viber.com", "203.0.113.1"), ("cdn.viber.com", "203.0.113.2")]
        totals = [{"domain": "media.viber.com", "total": 100 * MB}]
        found = DISCOVERY.candidates(pairs, totals, minimum_bytes=5 * MB, now=1)
        self.assertFalse(found[0]["infrastructure"])
        self.assertTrue(found[0]["cappable"])


class ListingOrderTests(unittest.TestCase):
    """The stored listing is what the interface shows, so it carries the ordering.

    Sorting only the freshly computed candidates had no visible effect: the panel reads
    the stored rows, which came back ordered by traffic alone, so the CDNs still led the
    list on a live firewall.
    """

    def setUp(self):
        self.connection, self.path = fresh_db()

    def tearDown(self):
        self.connection.close()
        os.unlink(self.path)

    def test_infrastructure_is_listed_last_despite_more_traffic(self):
        DISCOVERY.record([
            {"domain": "cloudflare.net", "label": "cloudflare.net", "category": "x",
             "named_from": "y", "hostnames": [], "hostname_count": 0, "addresses": 2,
             "shared": 0, "cappable": False, "infrastructure": True, "belongs_to": "",
             "bytes_seen": 2_400_000_000, "first_seen": 1, "last_seen": 1},
            {"domain": "viber.com", "label": "Viber", "category": "Messaging",
             "named_from": "known domain", "hostnames": [], "hostname_count": 0,
             "addresses": 2, "shared": 0, "cappable": True, "infrastructure": False,
             "belongs_to": "", "bytes_seen": 100_000_000, "first_seen": 1, "last_seen": 1},
        ], self.connection)
        order = [row["domain"] for row in DISCOVERY.listing(connection=self.connection)]
        self.assertEqual(order, ["viber.com", "cloudflare.net"])
        filtered = [row["domain"] for row in DISCOVERY.listing("new", self.connection)]
        self.assertEqual(filtered, ["viber.com", "cloudflare.net"])


class PruneTests(unittest.TestCase):
    """A candidate a service now claims is stale and must stop being offered.

    nflxso.net stayed on the discovery list as "Unclassified, likely part of netflix"
    after being added to the Netflix catalogue entry — the panel exists to say what is
    *not* accounted for, so listing something that now is says the opposite of the truth.
    """

    def setUp(self):
        self.connection, self.path = fresh_db()

    def tearDown(self):
        self.connection.close()
        os.unlink(self.path)

    def store(self, domain):
        DISCOVERY.record([{"domain": domain, "label": domain, "category": "Unclassified",
                           "named_from": "x", "hostnames": [], "hostname_count": 0,
                           "addresses": 2, "shared": 0, "cappable": True,
                           "infrastructure": False, "belongs_to": "netflix",
                           "bytes_seen": 100, "first_seen": 1, "last_seen": 1}],
                         self.connection)

    def test_a_domain_the_catalogue_now_claims_is_dropped(self):
        self.store("nflxso.net")
        self.assertEqual(len(DISCOVERY.listing(connection=self.connection, prune=False)), 1)
        dropped = DISCOVERY.prune_covered(self.connection)
        self.assertIn("nflxso.net", dropped)
        self.assertEqual(DISCOVERY.listing(connection=self.connection, prune=False), [])

    def test_listing_prunes_by_default(self):
        self.store("nflxso.net")
        self.assertEqual(DISCOVERY.listing(connection=self.connection), [])

    def test_a_domain_nothing_claims_is_kept(self):
        self.store("viber.com")
        kept = [row["domain"] for row in DISCOVERY.listing(connection=self.connection)]
        self.assertEqual(kept, ["viber.com"])

    def test_an_accepted_candidate_is_not_pruned_by_its_own_acceptance(self):
        """Otherwise accepting a service would delete the record that makes it cappable."""
        self.store("viber.com")
        DISCOVERY.set_status("viber.com", "accepted", self.connection)
        DISCOVERY.prune_covered(self.connection)
        self.assertIn("viber_com", DISCOVERY.accepted_services(self.connection))


class StoredFieldTests(unittest.TestCase):
    """Every field the panel displays must survive the round trip.

    hostname_count was computed for a fresh candidate and never stored, so a row read
    back from the database had none and the panel printed "undefined hostname(s)".
    """

    def setUp(self):
        self.connection, self.path = fresh_db()

    def tearDown(self):
        self.connection.close()
        os.unlink(self.path)

    def test_hostname_count_survives_the_round_trip(self):
        DISCOVERY.record([{"domain": "viber.com", "label": "Viber", "category": "Messaging",
                           "named_from": "known domain",
                           "hostnames": ["a.viber.com", "b.viber.com"], "hostname_count": 7,
                           "addresses": 2, "shared": 1, "cappable": True,
                           "infrastructure": False, "belongs_to": "",
                           "bytes_seen": 100, "first_seen": 1, "last_seen": 1}],
                         self.connection)
        row = DISCOVERY.listing(connection=self.connection, prune=False)[0]
        self.assertEqual(row["hostname_count"], 7)

    def test_every_field_the_panel_reads_is_present(self):
        candidates = DISCOVERY.candidates(
            [("a.viber.com", "203.0.113.1"), ("b.viber.com", "203.0.113.2")],
            [{"domain": "a.viber.com", "total": 50 * MB}], minimum_bytes=5 * MB, now=1)
        DISCOVERY.record(candidates, self.connection)
        row = DISCOVERY.listing(connection=self.connection, prune=False)[0]
        for field in ("domain", "label", "category", "named_from", "status", "belongs_to",
                      "cappable", "infrastructure", "addresses", "shared", "hostnames",
                      "hostname_count", "bytes_seen"):
            self.assertIn(field, row, field)
            self.assertIsNotNone(row[field], field)
