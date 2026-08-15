#!/usr/local/bin/python3
"""Rank LAN consumers and DNS-attributed domains from OPNsense Insight flows."""

import datetime as dt
import glob
import ipaddress
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET


CONFIG_PATH = "/conf/config.xml"
FLOW_DB_PATTERN = "/var/netflow/src_addr_details_*.sqlite"
STATE_DIR = "/var/db/wanquota"
DOMAIN_DB = os.path.join(STATE_DIR, "domains.sqlite")
NTOP_RRD_PATTERN = "/var/db/ntopng/*/rrd"


def node_text(node, name, default=""):
    child = node.find(name) if node is not None else None
    return child.text.strip() if child is not None and child.text else default


def settings_and_names():
    root = ET.parse(CONFIG_PATH).getroot()
    settings = root.find("./OPNsense/WanQuota/general")
    names = {}
    for host in root.findall(".//hosts"):
        address = node_text(host, "ip")
        if address:
            names[address] = node_text(host, "descr") or node_text(host, "host") or address
    lan_ip = node_text(root, "./interfaces/lan/ipaddr", "192.168.1.1")
    prefix = int(node_text(root, "./interfaces/lan/subnet", "24"))
    lan_interface = node_text(root, "./interfaces/lan/if", "lan")
    return {
        "enabled": node_text(settings, "consumers_enabled", "1") == "1",
        "domain_enabled": node_text(settings, "domain_enabled", "1") == "1",
        "top_limit": max(5, min(100, int(node_text(settings, "top_limit", "20")))),
        "default_period": node_text(settings, "default_period", "thirty"),
        "retention_days": max(7, min(365, int(node_text(settings, "domain_retention_days", "90")))),
        "network": ipaddress.ip_network(f"{lan_ip}/{prefix}", strict=False),
        "router": lan_ip,
        "lan_interface": lan_interface,
    }, names


def database():
    os.makedirs(STATE_DIR, mode=0o750, exist_ok=True)
    connection = sqlite3.connect(DOMAIN_DB)
    connection.execute("""CREATE TABLE IF NOT EXISTS ip_domains (
        ip TEXT NOT NULL,
        domain TEXT NOT NULL,
        first_seen INTEGER NOT NULL,
        last_seen INTEGER NOT NULL,
        expires_at INTEGER NOT NULL,
        PRIMARY KEY (ip, domain)
    )""")
    connection.execute("CREATE INDEX IF NOT EXISTS ip_domains_recent ON ip_domains(ip, last_seen DESC)")
    return connection


def normalize_domain(value):
    return value.rstrip(".").lower()


def collect_dns():
    settings, _ = settings_and_names()
    if not settings["domain_enabled"]:
        return {"status": "disabled", "collected": 0}
    raw = subprocess.check_output(
        ["/usr/local/opnsense/scripts/unbound/wrapper.py", "-c"], text=True, timeout=30
    )
    records = json.loads(raw)
    now = int(dt.datetime.now().timestamp())
    collected = 0
    with database() as connection:
        for record in records:
            if record.get("rrtype") not in {"A", "AAAA"}:
                continue
            try:
                ipaddress.ip_address(record.get("value", ""))
            except ValueError:
                continue
            domain = normalize_domain(record.get("host", ""))
            if not domain:
                continue
            ttl = max(300, int(record.get("ttl") or 0))
            connection.execute(
                """INSERT INTO ip_domains(ip,domain,first_seen,last_seen,expires_at)
                   VALUES(?,?,?,?,?) ON CONFLICT(ip,domain) DO UPDATE SET
                   last_seen=excluded.last_seen, expires_at=excluded.expires_at""",
                (record["value"], domain, now, now, now + ttl),
            )
            collected += 1
        cutoff = now - settings["retention_days"] * 86400
        connection.execute("DELETE FROM ip_domains WHERE last_seen < ?", (cutoff,))
    return {"status": "ok", "collected": collected, "timestamp": now}


def period_start(period):
    today = dt.date.today()
    if period == "today":
        return today
    if period == "week":
        return today - dt.timedelta(days=6)
    if period == "thirty":
        return today - dt.timedelta(days=29)
    if period == "month":
        return today.replace(day=1)
    raise ValueError("unsupported reporting period")


def is_local(value, network):
    try:
        return ipaddress.ip_address(value) in network
    except ValueError:
        return False


def flow_database():
    candidates = glob.glob(FLOW_DB_PATTERN)
    if not candidates:
        return None
    preferred = [path for path in candidates if path.endswith("_086400.sqlite")]
    return (preferred or sorted(candidates))[0]


def flow_rows(start):
    flow_db = flow_database()
    if flow_db is None:
        raise RuntimeError("Insight daily flow database is unavailable")
    connection = sqlite3.connect(f"file:{flow_db}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(
            "SELECT mtime,if,direction,src_addr,dst_addr,octets FROM timeserie WHERE date(mtime) >= date(?)",
            (start.isoformat(),),
        ).fetchall()
    finally:
        connection.close()


def domain_map():
    if not os.path.exists(DOMAIN_DB):
        return {}
    connection = sqlite3.connect(f"file:{DOMAIN_DB}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            """SELECT ip,domain FROM ip_domains d WHERE last_seen=(
                   SELECT max(last_seen) FROM ip_domains WHERE ip=d.ip)"""
        ).fetchall()
        return dict(rows)
    finally:
        connection.close()


def host_rrds(network):
    for root in glob.glob(NTOP_RRD_PATTERN):
        for directory, _, files in os.walk(root):
            if "bytes.rrd" not in files:
                continue
            relative = os.path.relpath(directory, root)
            parts = relative.split(os.sep)
            if len(parts) != 4 or not all(part.isdigit() for part in parts):
                continue
            address = ".".join(parts)
            if is_local(address, network):
                yield address, os.path.join(directory, "bytes.rrd")


def rrd_totals(path, start):
    start_epoch = int(dt.datetime.combine(start, dt.time.min).astimezone().timestamp())
    end_epoch = int(dt.datetime.now().timestamp())
    output = subprocess.check_output(
        ["/usr/local/bin/rrdtool", "fetch", path, "AVERAGE", "--start", str(start_epoch), "--end", str(end_epoch)],
        text=True,
        timeout=30,
    )
    samples = []
    for line in output.splitlines():
        match = re.match(r"\s*(\d+):\s+(\S+)\s+(\S+)", line)
        if not match:
            continue
        timestamp = int(match.group(1))
        try:
            sent, received = float(match.group(2)), float(match.group(3))
        except ValueError:
            continue
        samples.append((timestamp, sent, received))
    steps = [samples[index][0] - samples[index - 1][0] for index in range(1, len(samples)) if samples[index][0] > samples[index - 1][0]]
    step = min(steps) if steps else 300
    sent = sum(value * step for _, value, _ in samples if math.isfinite(value))
    received = sum(value * step for _, _, value in samples if math.isfinite(value))
    return sent, received


def report(period):
    settings, names = settings_and_names()
    if not settings["enabled"]:
        return {"status": "disabled", "period": period, "hosts": [], "domains": []}
    start = period_start(period)
    hosts = []
    remote_totals = {}
    for address, path in host_rrds(settings["network"]):
        if address == settings["router"]:
            continue
        upload, download = rrd_totals(path, start)
        total = upload + download
        if total > 0:
            hosts.append({"ip": address, "name": names.get(address, address), "download": download, "upload": upload, "total": total})
    flow_error = None
    if settings["domain_enabled"]:
        try:
            rows = flow_rows(start)
        except (OSError, RuntimeError, sqlite3.Error) as error:
            rows = []
            flow_error = str(error)
        for row in rows:
            if row["if"] != settings["lan_interface"] or row["direction"] != "out":
                continue
            if not is_local(row["src_addr"], settings["network"]) or is_local(row["dst_addr"], settings["network"]):
                continue
            if row["src_addr"] == settings["router"]:
                continue
            remote_totals[row["dst_addr"]] = remote_totals.get(row["dst_addr"], 0) + float(row["octets"] or 0)
    host_rows = sorted(hosts, key=lambda item: item["total"], reverse=True)[: settings["top_limit"]]

    mappings = domain_map() if settings["domain_enabled"] else {}
    domains = {}
    attributed = 0
    total_external = 0
    for remote, amount in remote_totals.items():
        total_external += amount
        domain = mappings.get(remote)
        if not domain:
            continue
        attributed += amount
        entry = domains.setdefault(domain, {"domain": domain, "total": 0, "ips": set()})
        entry["total"] += amount
        entry["ips"].add(remote)
    domain_rows = []
    for entry in domains.values():
        domain_rows.append({
            "domain": entry["domain"],
            "total": entry["total"],
            "ip_count": len(entry["ips"]),
        })
    domain_rows.sort(key=lambda item: item["total"], reverse=True)
    return {
        "status": "ok",
        "period": period,
        "start": start.isoformat(),
        "end": dt.date.today().isoformat(),
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "hosts": host_rows,
        "domains": domain_rows[: settings["top_limit"]],
        "domain_attribution": {
            "attributed_bytes": attributed,
            "total_external_bytes": total_external,
            "coverage_percent": attributed / total_external * 100 if total_external else 0,
            "method": "Insight flow bytes correlated with recently observed Unbound DNS answers",
            "error": flow_error,
        },
    }


def main():
    if "collect-dns" in sys.argv:
        result = collect_dns()
    else:
        period = next((value for value in ("today", "week", "thirty", "month") if value in sys.argv), None)
        if period is None:
            period = settings_and_names()[0]["default_period"]
        result = report(period)
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
