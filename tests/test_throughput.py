"""Live per-WAN throughput from the interface counters.

The counters are cumulative, so everything here is about the difference between two
samples: picking the right line, the right columns, and refusing to report a rate when
the sample cannot mean anything.
"""

import importlib.util
from pathlib import Path
import sys
import unittest

SOURCE_DIR = Path(__file__).parents[1] / "src/opnsense/scripts/OPNsense/WanQuota"
sys.path.insert(0, str(SOURCE_DIR))
SPEC = importlib.util.spec_from_file_location("wanquota_throughput", SOURCE_DIR / "throughput.py")
THROUGHPUT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(THROUGHPUT)

# Real output from the firewall. The address lines matter: they repeat the interface
# with per-protocol counters, and counting them would double the totals.
NETSTAT = """\
Name    Mtu Network                   Address                    Ipkts Ierrs Idrop      Ibytes    Opkts Oerrs      Obytes  Coll
igb0   1500 <Link#1>                  68:f7:28:e7:eb:5e        3759785     0     0  3772444762  2993711     0   721225033     0
igb0      - fe80::%igb0/64            fe80::6af7:28ff:fee7      3381     -     -      237056     5104     -      350404     -
"""


class CounterTests(unittest.TestCase):
    def test_the_link_line_supplies_the_totals(self):
        self.assertEqual(THROUGHPUT.counters("igb0", lambda _i: NETSTAT),
                         (3772444762, 721225033))

    def test_an_unreadable_interface_reports_nothing_rather_than_zero(self):
        self.assertIsNone(THROUGHPUT.counters("igb0", lambda _i: ""))

    def test_output_without_a_link_line_is_not_guessed_at(self):
        text = "Name Mtu Network Address Ipkts\nigb0 - fe80::%igb0/64 x 1\n"
        self.assertIsNone(THROUGHPUT.counters("igb0", lambda _i: text))


class SampleTests(unittest.TestCase):
    PROVIDERS = [{"name": "ETISALAT", "interface": "igb0", "logical_interface": "wan"}]

    def growing(self, down_delta, up_delta):
        """A fake netstat whose counters advance between calls."""
        state = {"calls": 0}

        def runner(_interface):
            state["calls"] += 1
            step = 0 if state["calls"] == 1 else 1
            return NETSTAT.replace("3772444762", str(3772444762 + down_delta * step)) \
                          .replace("721225033", str(721225033 + up_delta * step))

        return runner

    def test_a_rate_is_bits_per_second_from_the_byte_difference(self):
        # 1,250,000 bytes in 1 s is 10 Mbit/s.
        rows = THROUGHPUT.sample(self.PROVIDERS, self.growing(1250000, 125000),
                                 seconds=1.0, sleeper=lambda _s: None)
        self.assertTrue(rows[0]["available"])
        self.assertEqual(rows[0]["download_bps"], 10000000)
        self.assertEqual(rows[0]["upload_bps"], 1000000)

    def test_the_interval_divides_the_rate(self):
        rows = THROUGHPUT.sample(self.PROVIDERS, self.growing(1250000, 0),
                                 seconds=2.0, sleeper=lambda _s: None)
        self.assertEqual(rows[0]["download_bps"], 5000000)

    def test_an_idle_link_reports_zero_and_stays_available(self):
        rows = THROUGHPUT.sample(self.PROVIDERS, self.growing(0, 0),
                                 seconds=1.0, sleeper=lambda _s: None)
        self.assertTrue(rows[0]["available"])
        self.assertEqual(rows[0]["download_bps"], 0)

    def test_a_counter_that_restarts_is_reported_unusable_not_negative(self):
        state = {"calls": 0}

        def runner(_interface):
            state["calls"] += 1
            if state["calls"] == 1:
                return NETSTAT
            return NETSTAT.replace("3772444762", "5")

        rows = THROUGHPUT.sample(self.PROVIDERS, runner, seconds=1.0, sleeper=lambda _s: None)
        self.assertFalse(rows[0]["available"])
        self.assertIn("restarted", rows[0]["reason"])
        self.assertNotIn("download_bps", rows[0])

    def test_an_unreadable_interface_is_named_rather_than_dropped(self):
        rows = THROUGHPUT.sample(self.PROVIDERS, lambda _i: "", seconds=1.0,
                                 sleeper=lambda _s: None)
        self.assertEqual(rows[0]["name"], "ETISALAT")
        self.assertFalse(rows[0]["available"])

    def test_every_provider_gets_a_row_even_when_one_fails(self):
        providers = self.PROVIDERS + [{"name": "MOBINIL", "interface": "nope",
                                       "logical_interface": "opt1"}]

        def runner(interface):
            return NETSTAT if interface == "igb0" else ""

        rows = THROUGHPUT.sample(providers, runner, seconds=1.0, sleeper=lambda _s: None)
        self.assertEqual([r["name"] for r in rows], ["ETISALAT", "MOBINIL"])
        self.assertTrue(rows[0]["available"])
        self.assertFalse(rows[1]["available"])


if __name__ == "__main__":
    unittest.main()
