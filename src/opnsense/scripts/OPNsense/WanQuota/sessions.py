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
import time

import consumers
import shaper

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
                "upload": 0,
                "download": 0,
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
            # pf prints the pair in the order the state was created. For a
            # LAN-originated connection the first figure is what the device sent and
            # the second is what it received, confirmed by measuring a known 8 MB
            # download: the counters read 28177:8252529. A connection opened from
            # outside, through a port forward, would be the other way round; those
            # are not this plugin's subject and are filtered out with LAN-to-LAN.
            upload = int(values["bytes_in"])
            download = int(values["bytes_out"])
            current["upload"] = max(current["upload"], upload)
            current["download"] = max(current["download"], download)
            current["bytes"] = max(current["bytes"], upload + download)
            current["packets"] = max(
                current["packets"], int(values["pkts_in"]) + int(values["pkts_out"]))
    return list(records.values())


def cap_targets(catalog=None):
    """registrable domain -> the service that already claims it.

    Built once rather than per session: the catalogue is small but a state table is not,
    and rebuilding it five hundred times would be five hundred scans for one answer.
    """
    entries = catalog if catalog is not None else shaper.full_catalog()
    owners = {}
    for key, entry in entries.items():
        for suffix in tuple(entry.get("suffixes", ())) + tuple(entry.get("co_delivery", ())):
            owners[shaper.registrable(suffix)] = entry.get("label", key)
    owners.pop("", None)
    return owners


def cap_hint(domain, owners):
    """Whether this destination could be added to a service, and if not, why.

    Offering a target the planner will refuse is worse than offering nothing: the reader
    only finds out after choosing a service and applying. A shared CDN is refused because
    capping it throttles unrelated traffic, and a domain a service already claims does
    not need adding.
    """
    if not domain:
        return None
    registrable = shaper.registrable(domain)
    if not registrable:
        return None
    if shaper.is_shared_cdn(registrable):
        return {"domain": registrable, "allowed": False, "service": "",
                "reason": "a shared CDN: capping it would throttle unrelated traffic"}
    owner = owners.get(registrable)
    if owner:
        return {"domain": registrable, "allowed": False, "service": owner,
                "reason": f"already part of {owner}"}
    return {"domain": registrable, "allowed": True, "service": "", "reason": ""}


def local_sessions(states, network, router, names, domains, limit=STATE_LIMIT, owners=None):
    """Sessions originating from a LAN device, largest first, named where possible."""
    rows = []
    owners = owners if owners is not None else cap_targets()
    for state in states:
        device = state["device"]
        if device == router or not consumers.is_local(device, network):
            continue
        if consumers.is_local(state["remote"], network):
            # LAN to LAN never crossed the WAN, so it is not interesting here.
            continue
        remote_domain = domains.get(state["remote"])
        rows.append({
            **state,
            "name": names.get(device, device),
            "remote_domain": remote_domain,
            # The name a cap would be written against. A per-session hostname is no use
            # for that — occ-0-3310-1490.1.nflxso.net is one appliance for one session,
            # while nflxso.net is the name that keeps matching — so the registrable
            # domain is offered alongside it.
            "remote_registrable": shaper.registrable(remote_domain) if remote_domain else None,
            # Whether that name could be added to a service, and if not, why.
            "cap_hint": cap_hint(remote_domain, owners),
            "service": consumers.transport_label(state["protocol"], state["remote_port"]),
            # A stable identity for the flow, so a reader can match the same session
            # across refreshes and measure how fast it is actually moving. Rebuilding
            # this in the interface from separate fields would drift from the key used
            # here to deduplicate NAT twins.
            "key": "|".join(str(part) for part in (
                state["protocol"], state["device"], state["device_port"],
                state["remote"], state["remote_port"])),
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
            "device": row["device"], "name": row["name"], "sessions": 0,
            "bytes": 0, "download": 0, "upload": 0})
        entry["sessions"] += 1
        entry["bytes"] += row["bytes"]
        entry["download"] += row["download"]
        entry["upload"] += row["upload"]
    return {
        "status": "ok",
        "total_states": len(states),
        "shown": len(sessions),
        "limit": limit,
        "sessions": sessions,
        "devices": sorted(by_device.values(), key=lambda item: item["bytes"], reverse=True),
        "collected_at": int(time.time()),
        "note": (
            "State counters are per state and reset when a state is created, so these "
            "byte figures are not quota accounting. Download and upload are read from "
            "the state's own counter pair, which is oriented by who opened the "
            "connection. Sessions are shown whether or not the destination has a known "
            "name, so traffic missing from the domain reports still appears here. Rates "
            "are computed by the interface from the change between two refreshes, so the "
            "first reading after opening the tab shows totals only."
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
