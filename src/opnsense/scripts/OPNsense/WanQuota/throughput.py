#!/usr/local/bin/python3
"""Live throughput per WAN, read from the interface counters.

The quota reports answer "how much this cycle". They cannot answer "what is moving
right now", because vnStat and the flow database both aggregate after the fact. This
samples the kernel's own byte counters twice and reports the difference, which is the
only way to get a current rate without keeping state between calls.

Direction is unambiguous on a WAN interface: bytes arriving are download and bytes
leaving are upload. That is worth saying because the per-WAN *attribution* report
explicitly cannot split direction — it derives from flow records whose interface
direction is not the same question — so the two must not be confused. Here the
counters are the interface's own and the split is exact.
"""

import json
import re
import subprocess
import sys
import time

import report

# Long enough that a short burst does not dominate the average, short enough that the
# interface feels live and a GUI poll does not hang.
SAMPLE_SECONDS = 1.0


def counters(interface, runner=None):
    """(bytes_in, bytes_out) for one interface, or None if it cannot be read.

    Columns are located from the header rather than by counting numeric fields. The
    first attempt did the latter and read the wrong pair, because Mtu is numeric too:
    picking the fourth number found Idrop instead of Ibytes, so every rate came out as
    zero. Naming the columns also survives a netstat that adds or drops one.
    """
    invoke = runner or _netstat
    text = invoke(interface)
    headers = None
    for line in (text or "").splitlines():
        fields = line.split()
        if not fields:
            continue
        if fields[0] == "Name":
            headers = fields
            continue
        # The <Link#N> line carries the hardware totals. Address lines repeat the
        # interface with per-protocol counters and would double-count.
        if headers is None or "<Link#" not in line:
            continue
        try:
            inbound = fields[headers.index("Ibytes")]
            outbound = fields[headers.index("Obytes")]
            return int(inbound), int(outbound)
        except (ValueError, IndexError):
            return None
    return None


def _netstat(interface):
    try:
        done = subprocess.run(["/usr/bin/netstat", "-ibnW", "-I", interface],
                              capture_output=True, text=True, timeout=15)
        return done.stdout
    except Exception:
        return ""


def sample(providers, runner=None, seconds=SAMPLE_SECONDS, sleeper=None):
    """Rates for each provider, measured over one interval."""
    wait = sleeper or time.sleep
    first = {}
    for provider in providers:
        first[provider["interface"]] = counters(provider["interface"], runner)
    wait(seconds)
    rows = []
    for provider in providers:
        interface = provider["interface"]
        before, after = first.get(interface), counters(interface, runner)
        if before is None or after is None:
            rows.append({
                "name": provider["name"],
                "interface": interface,
                "logical_interface": provider.get("logical_interface", ""),
                "available": False,
                "reason": "the interface counters could not be read",
            })
            continue
        # A counter that has gone backwards means the interface was reset between
        # samples. Reporting a negative rate, or a huge one from a wrap, would be
        # worse than saying the sample is unusable.
        down = after[0] - before[0]
        up = after[1] - before[1]
        if down < 0 or up < 0:
            rows.append({
                "name": provider["name"], "interface": interface,
                "logical_interface": provider.get("logical_interface", ""),
                "available": False,
                "reason": "the interface counters restarted during the sample",
            })
            continue
        rows.append({
            "name": provider["name"],
            "interface": interface,
            "logical_interface": provider.get("logical_interface", ""),
            "available": True,
            "download_bps": round(down * 8 / seconds),
            "upload_bps": round(up * 8 / seconds),
            "download_bytes": down,
            "upload_bytes": up,
        })
    return rows


def document(runner=None, seconds=SAMPLE_SECONDS, sleeper=None):
    try:
        enabled, providers = report.configuration()
    except Exception as error:
        return {"status": "failed", "error": str(error), "wans": []}
    if not enabled:
        return {"status": "disabled", "wans": [],
                "note": "WAN quota reporting is disabled."}
    rows = sample(providers, runner, seconds, sleeper)
    return {
        "status": "ok",
        "sample_seconds": seconds,
        "wans": rows,
        "total_download_bps": sum(r.get("download_bps", 0) for r in rows),
        "total_upload_bps": sum(r.get("upload_bps", 0) for r in rows),
        "note": (
            f"Measured from the interface counters over {seconds:g} s. Download is "
            "bytes arriving on the WAN and upload is bytes leaving it, taken from the "
            "interface itself, so unlike the per-WAN attribution report this split is "
            "exact."
        ),
    }


def main():
    seconds = SAMPLE_SECONDS
    if len(sys.argv) > 1:
        try:
            seconds = max(0.2, min(5.0, float(sys.argv[1])))
        except ValueError:
            pass
    print(json.dumps(document(seconds=seconds), separators=(",", ":")))


if __name__ == "__main__":
    main()
