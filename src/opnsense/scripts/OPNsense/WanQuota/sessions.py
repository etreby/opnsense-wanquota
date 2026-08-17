#!/usr/local/bin/python3
"""Live sessions: what the network is doing right now.

Every other report in this plugin is historical — bytes already counted. This one
answers a different question: which conversations are open at this moment, from
which device, to what. It reads the firewall's own state table, so it reflects
reality rather than a collector's last pass.

Two things it deliberately is not. It is not a byte accounting source: state
counters reset when a state is created and vanish when it expires, so they must
never be added to quota figures. And it is not filtered by DNS attribution — a
state exists whether or not the destination has a name, so this is the one view
where traffic hidden from the domain reports is still visible.
"""

import ipaddress
import json
import re
import subprocess
import sys

import consumers

PFCTL = "/sbin/pfctl"
STATE_LIMIT = 500

# "all tcp 1.2.3.4:443 <- 192.168.1.20:51200   ESTABLISHED:ESTABLISHED"
# "all tcp 172.16.0.5:2298 (192.168.1.20:51200) -> 1.2.3.4:443   ESTABLISHED..."
#
# Endpoints are captured whole and split in Python rather than by the pattern: a
# character class covering both addresses and the port separator is greedy and
# swallows the port, and IPv6 endpoints carry colons of their own.
HEADER = re.compile(
    r"^\s*(?P<iface>\S+)\s+(?P<proto>tcp|udp|icmp|icmp6|ipv6-icmp|esp|gre|ip)\s+"
    r"(?P<left>\S+)\s*"
    r"(?:\((?P<nat>[^)]+)\)\s*)?"
    r"(?P<arrow><-|->)\s+"
    r"(?P<right>\S+)"
    r"(?:\s+(?P<state>\S+))?\s*$"
)
# "   age 01:06:55, expires in 23:59:42, 85:158 pkts, 6539:13489 bytes, rule 98"
DETAIL = re.compile(
    r"age\s+(?P<age>[\d:]+).*?(?P<pkts_in>\d+):(?P<pkts_out>\d+)\s+pkts,\s*"
    r"(?P<bytes_in>\d+):(?P<bytes_out>\d+)\s+bytes"
)


def split_endpoint(value):
    """(address, port) from a pf endpoint, tolerating IPv6 and a missing port."""
    token = (value or "").strip()
    if not token:
        return "", None
    if token.startswith("["):
        # [2001:db8::1]:443
        address, _, rest = token[1:].partition("]")
        port = rest.lstrip(":")
        return address, int(port) if port.isdigit() else None
    if token.count(":") > 1:
        # A bare IPv6 address; pf only appends a port in bracket form.
        return token, None
    address, _, port = token.rpartition(":")
    if not address:
        return token, None
    return address, int(port) if port.isdigit() else None


def _seconds(value):
    parts = [int(p) for p in (value or "").split(":") if p.isdigit()]
    total = 0
    for part in parts:
        total = total * 60 + part
    return total


def parse_states(output):
    """Turn `pfctl -vv -ss` output into records.

    A state appears twice on a NAT'd firewall — once per translation direction — so
    records are keyed on the internal address and port pair and merged, otherwise
    every conversation is double counted.
    """
    records = {}
    current = None
    for line in (output or "").splitlines():
        header = HEADER.match(line)
        if header:
            groups = header.groupdict()
            # The internal address is whichever side is behind NAT when a
            # translation is shown, otherwise the local end of the arrow.
            if groups.get("nat"):
                internal, internal_port = split_endpoint(groups["nat"])
            else:
                internal, internal_port = split_endpoint(groups["left"])
            remote, remote_port = split_endpoint(groups["right"])
            if groups["arrow"] == "<-":
                internal, remote = remote, internal
                internal_port, remote_port = remote_port, internal_port
            current = {
                "protocol": groups["proto"],
                "device": internal,
                "device_port": internal_port,
                "remote": remote,
                "remote_port": remote_port,
                "state": groups.get("state") or "",
                "age_seconds": 0,
                "bytes": 0,
                "packets": 0,
            }
            key = (current["protocol"], current["device"], current["device_port"],
                   current["remote"], current["remote_port"])
            records.setdefault(key, current)
            current = records[key]
            continue
        if current is None:
            continue
        detail = DETAIL.search(line)
        if detail:
            values = detail.groupdict()
            current["age_seconds"] = max(current["age_seconds"], _seconds(values["age"]))
            total = int(values["bytes_in"]) + int(values["bytes_out"])
            current["bytes"] = max(current["bytes"], total)
            current["packets"] = max(
                current["packets"], int(values["pkts_in"]) + int(values["pkts_out"]))
    return list(records.values())


def local_sessions(states, network, router, names, domains, limit=STATE_LIMIT):
    """Sessions originating from a LAN device, largest first, named where possible."""
    rows = []
    for state in states:
        device = state["device"]
        if device == router or not consumers.is_local(device, network):
            continue
        if consumers.is_local(state["remote"], network):
            # LAN to LAN never crossed the WAN, so it is not interesting here.
            continue
        rows.append({
            **state,
            "name": names.get(device, device),
            "remote_domain": domains.get(state["remote"]),
            "service": consumers.transport_label(state["protocol"], state["remote_port"]),
        })
    rows.sort(key=lambda item: (item["bytes"], item["age_seconds"]), reverse=True)
    return rows[:limit]


def _run_pfctl():
    return subprocess.check_output([PFCTL, "-vv", "-ss"], text=True, timeout=30)


def document(runner=None, limit=STATE_LIMIT):
    try:
        output = (runner or _run_pfctl)()
    except (OSError, subprocess.SubprocessError) as error:
        return {"status": "failed", "error": str(error), "sessions": []}
    settings, static_names = consumers.settings_and_names()
    leases = {**consumers.kea_leases(), **consumers.dnsmasq_leases()}
    ident = consumers.identities(static_names, leases, consumers.arp_macs())
    names = {address: entry["name"] for address, entry in ident.items()}
    for address, name in static_names.items():
        names.setdefault(address, name)
    states = parse_states(output)
    sessions = local_sessions(
        states, settings["network"], settings["router"], names,
        consumers.domain_map() if settings["domain_enabled"] else {}, limit,
    )
    by_device = {}
    for row in sessions:
        entry = by_device.setdefault(row["device"], {
            "device": row["device"], "name": row["name"], "sessions": 0, "bytes": 0})
        entry["sessions"] += 1
        entry["bytes"] += row["bytes"]
    return {
        "status": "ok",
        "total_states": len(states),
        "shown": len(sessions),
        "limit": limit,
        "sessions": sessions,
        "devices": sorted(by_device.values(), key=lambda item: item["bytes"], reverse=True),
        "note": (
            "State counters are per state and reset when a state is created, so these "
            "byte figures are not quota accounting. Sessions are shown whether or not "
            "the destination has a known name, so traffic missing from the domain "
            "reports still appears here."
        ),
    }


def main():
    limit = STATE_LIMIT
    if len(sys.argv) > 1:
        try:
            limit = max(1, min(5000, int(sys.argv[1])))
        except ValueError:
            pass
    print(json.dumps(document(limit=limit), separators=(",", ":")))


if __name__ == "__main__":
    main()
