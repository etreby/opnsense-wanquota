"""Per-device identity: policy matching and the history migration.

Device policies and history baselines were keyed to the IP address. DHCP
reassigns addresses, and a device using a randomised MAC per network holds
several leases at once, so anything keyed to an address alone quietly stops
matching the device it was configured for.
"""

import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

SOURCE_DIR = Path(__file__).parents[1] / "src/opnsense/scripts/OPNsense/WanQuota"
sys.path.insert(0, str(SOURCE_DIR))
SPEC = importlib.util.spec_from_file_location("wanquota_intelligence_id", SOURCE_DIR / "intelligence.py")
INTEL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INTEL)


class PolicyMatchingTests(unittest.TestCase):
    def test_matches_by_address(self):
        index = INTEL.policy_index([{"address": "192.168.1.20", "budget_gb": 50}])
        self.assertEqual(INTEL.policy_for({"ip": "192.168.1.20"}, index)["budget_gb"], 50)

    def test_matches_by_mac_after_the_address_changed(self):
        index = INTEL.policy_index([{"mac": "AA:BB:CC:DD:EE:FF", "budget_gb": 25}])
        host = {"ip": "192.168.1.99", "mac": "aa:bb:cc:dd:ee:ff"}
        self.assertEqual(INTEL.policy_for(host, index)["budget_gb"], 25)

    def test_matches_by_dhcp_hostname(self):
        index = INTEL.policy_index([{"hostname": "MacBookPro", "exclude": True}])
        host = {"ip": "192.168.1.222", "hostname": "macbookpro"}
        self.assertTrue(INTEL.policy_for(host, index)["exclude"])

    def test_no_match_returns_empty(self):
        index = INTEL.policy_index([{"address": "192.168.1.20"}])
        self.assertEqual(INTEL.policy_for({"ip": "192.168.1.77"}, index), {})

    def test_address_policy_still_wins_for_the_same_host(self):
        index = INTEL.policy_index([
            {"address": "192.168.1.20", "budget_gb": 10},
            {"mac": "aa:bb:cc:dd:ee:ff", "budget_gb": 99},
        ])
        host = {"ip": "192.168.1.20", "mac": "aa:bb:cc:dd:ee:ff"}
        self.assertEqual(INTEL.policy_for(host, index)["budget_gb"], 10)

    def test_entries_without_any_identifier_are_ignored(self):
        self.assertEqual(INTEL.policy_index([{"budget_gb": 5}]), {})


class HistoryMigrationTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.saved = (INTEL.STATE_DIR, INTEL.DB_PATH)
        INTEL.STATE_DIR = self.dir.name
        INTEL.DB_PATH = str(Path(self.dir.name) / "intelligence.sqlite")

    def tearDown(self):
        INTEL.STATE_DIR, INTEL.DB_PATH = self.saved
        self.dir.cleanup()

    def columns(self):
        with INTEL.database() as db:
            return {r[1] for r in db.execute("PRAGMA table_info(consumer_samples)")}

    def test_fresh_database_has_the_mac_column(self):
        self.assertIn("mac", self.columns())

    def test_migrates_a_pre_existing_table_without_the_column(self):
        # Simulate an install from before the column existed.
        with sqlite3.connect(INTEL.DB_PATH) as db:
            db.execute("CREATE TABLE consumer_samples(ts INTEGER,device TEXT,name TEXT,"
                       "total REAL,download REAL,upload REAL)")
            db.execute("INSERT INTO consumer_samples VALUES(1,'192.168.1.10','TRUENAS',5,4,1)")
        self.assertIn("mac", self.columns())
        with INTEL.database() as db:
            row = db.execute("SELECT device,name,mac FROM consumer_samples").fetchone()
        # The old row survives with a NULL mac and still matches by address.
        self.assertEqual((row[0], row[1], row[2]), ("192.168.1.10", "TRUENAS", None))

    def test_migration_is_idempotent(self):
        for _ in range(3):
            self.assertIn("mac", self.columns())


if __name__ == "__main__":
    unittest.main()
