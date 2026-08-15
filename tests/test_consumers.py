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


if __name__ == "__main__":
    unittest.main()
