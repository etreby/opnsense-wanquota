"""The local service address book."""

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

SOURCE_DIR = Path(__file__).parents[1] / "src/opnsense/scripts/OPNsense/WanQuota"
sys.path.insert(0, str(SOURCE_DIR))
SPEC = importlib.util.spec_from_file_location("wanquota_addresses", SOURCE_DIR / "addresses.py")
BOOK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BOOK)

CATALOG = {
    "netflix": {"label": "Netflix", "suffixes": ("nflxvideo.net", "netflix.com")},
    "linux_update": {"label": "Linux updates", "suffixes": ("archive.ubuntu.com",)},
}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.saved = (BOOK.STATE_DIR, BOOK.DB_PATH)
        BOOK.STATE_DIR = self.dir.name
        BOOK.DB_PATH = str(Path(self.dir.name) / "services.sqlite")
        self.db = BOOK.database()

    def tearDown(self):
        self.db.close()
        BOOK.STATE_DIR, BOOK.DB_PATH = self.saved
        self.dir.cleanup()

    def resolver(self, table):
        def lookup(hostname):
            if hostname not in table:
                raise OSError("NXDOMAIN")
            return table[hostname]
        return lookup

    def test_schema_is_created(self):
        names = {r[0] for r in self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("service_addresses", names)
        self.assertIn("service_hostnames", names)

    def test_creating_twice_is_idempotent(self):
        BOOK.database(BOOK.DB_PATH).close()
        self.assertIn("service_addresses", {r[0] for r in self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")})

    def test_observed_addresses_are_stored_from_mappings(self):
        BOOK.refresh(CATALOG, [("a.nflxvideo.net", "1.1.1.1")], self.db,
                     self.resolver({}))
        rows = BOOK.addresses_for("netflix", self.db)
        self.assertEqual([r["address"] for r in rows], ["1.1.1.1"])
        self.assertEqual(rows[0]["source"], BOOK.SOURCE_OBSERVED)

    def test_resolution_fills_a_service_nothing_has_queried(self):
        # This is the gap: Windows Update was uncappable because no device had
        # resolved it recently.
        BOOK.refresh(CATALOG, [], self.db,
                     self.resolver({"archive.ubuntu.com": ["185.125.190.81"]}))
        rows = BOOK.addresses_for("linux_update", self.db)
        self.assertEqual([r["address"] for r in rows], ["185.125.190.81"])
        self.assertEqual(rows[0]["source"], BOOK.SOURCE_RESOLVED)

    def test_observed_outranks_resolved_for_the_same_address(self):
        # Real traffic is stronger evidence than a lookup.
        BOOK.refresh(CATALOG, [], self.db, self.resolver({"netflix.com": ["5.5.5.5"]}))
        BOOK.refresh(CATALOG, [("netflix.com", "5.5.5.5")], self.db, self.resolver({}))
        rows = BOOK.addresses_for("netflix", self.db)
        self.assertEqual(rows[0]["source"], BOOK.SOURCE_OBSERVED)

    def test_a_hostname_that_does_not_resolve_is_not_an_error(self):
        result = BOOK.refresh(CATALOG, [], self.db, self.resolver({}))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(BOOK.addresses_for("netflix", self.db), [])

    def test_records_which_hostname_produced_an_address(self):
        BOOK.refresh(CATALOG, [], self.db,
                     self.resolver({"netflix.com": ["5.5.5.5"]}))
        rows = BOOK.addresses_for("netflix", self.db)
        self.assertIn("netflix.com", rows[0]["hostnames"])

    def test_expired_rows_are_pruned_and_not_returned(self):
        BOOK.refresh(CATALOG, [], self.db,
                     self.resolver({"netflix.com": ["5.5.5.5"]}), now=1000)
        later = 1000 + BOOK.RESOLVED_TTL + 1
        self.assertEqual(BOOK.addresses_for("netflix", self.db, now=later), [])
        result = BOOK.refresh(CATALOG, [], self.db, self.resolver({}), now=later)
        self.assertGreaterEqual(result["pruned"], 1)

    def test_refresh_reports_per_service_counts(self):
        result = BOOK.refresh(CATALOG, [("a.nflxvideo.net", "1.1.1.1")], self.db,
                              self.resolver({"archive.ubuntu.com": ["2.2.2.2", "3.3.3.3"]}))
        by_service = {s["service"]: s for s in result["services"]}
        self.assertEqual(by_service["netflix"]["observed_addresses"], 1)
        self.assertEqual(by_service["linux_update"]["resolved_addresses"], 2)

    def test_extra_hostname_is_used_on_the_next_refresh(self):
        BOOK.add_hostname("netflix", "Custom.CDN.Example.", self.db)
        self.assertEqual(BOOK.extra_hostnames(self.db, "netflix"), ["custom.cdn.example"])
        BOOK.refresh(CATALOG, [], self.db, self.resolver({"custom.cdn.example": ["7.7.7.7"]}))
        self.assertEqual([r["address"] for r in BOOK.addresses_for("netflix", self.db)],
                         ["7.7.7.7"])

    def test_a_bad_hostname_is_refused(self):
        for bad in ("", "   ", "notadomain"):
            with self.assertRaises(ValueError):
                BOOK.add_hostname("netflix", bad, self.db)

    def test_inventory_splits_evidence_by_source(self):
        BOOK.refresh(CATALOG, [("a.nflxvideo.net", "1.1.1.1")], self.db,
                     self.resolver({"netflix.com": ["5.5.5.5"]}))
        rows = {r["service"]: r for r in BOOK.inventory(CATALOG, self.db)}
        self.assertEqual(rows["netflix"]["observed"], 1)
        self.assertEqual(rows["netflix"]["resolved"], 1)
        self.assertEqual(rows["netflix"]["total"], 2)

    def test_resolver_failure_does_not_abort_other_services(self):
        def flaky(hostname):
            if "nflx" in hostname or "netflix" in hostname:
                raise OSError("timeout")
            return ["9.9.9.9"]
        BOOK.refresh(CATALOG, [], self.db, flaky)
        self.assertEqual([r["address"] for r in BOOK.addresses_for("linux_update", self.db)],
                         ["9.9.9.9"])


if __name__ == "__main__":
    unittest.main()
