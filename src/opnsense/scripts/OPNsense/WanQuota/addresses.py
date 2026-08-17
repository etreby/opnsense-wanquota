#!/usr/local/bin/python3
"""A local address book for limitable services.

Until now a service could only be capped if some device had recently resolved its
hostnames through Unbound. That made coverage depend on chance: Windows Update was
refused outright on a live network because nothing had asked for it lately.

This keeps the plugin's own SQLite store — /var/db/wanquota/services.sqlite — filled
from two sources and updated on the existing collector schedule:

  observed  addresses devices actually used, from the DNS attribution database.
            These are ground truth: traffic really went there.
  resolved  addresses the firewall looked up itself for a service's hostnames.
            These fill the gaps, but they are weaker evidence and are recorded as
            such rather than blended in silently.

The distinction is not bookkeeping. Measuring showed active resolution works well
for update mirrors, which publish stable hostnames — archive.ubuntu.com returns
eighteen addresses — and poorly for video services, whose delivery hostnames are
per-session and geographic. Resolving netflix.com returns the website, not the
appliance a television streams from, so capping it would limit the wrong thing while
appearing to work. Every row therefore records which hostname produced it and by
which method, so a limit built on weak evidence can be recognised as such.
"""

import json
import os
import socket
import sqlite3
import sys
import time

import consumers

STATE_DIR = "/var/db/wanquota"
DB_PATH = os.path.join(STATE_DIR, "services.sqlite")

# How long a resolved address is trusted without being seen again. Long enough to
# survive a collector hiccup, short enough that a retired CDN address ages out.
RESOLVED_TTL = 7 * 86400
OBSERVED_TTL = 30 * 86400

SOURCE_OBSERVED = "observed"
SOURCE_RESOLVED = "resolved"


def database(path=None):
    os.makedirs(STATE_DIR, mode=0o750, exist_ok=True)
    connection = sqlite3.connect(path or DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS service_addresses (
            service   TEXT NOT NULL,
            address   TEXT NOT NULL,
            hostname  TEXT NOT NULL,
            source    TEXT NOT NULL,
            first_seen INTEGER NOT NULL,
            last_seen  INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            PRIMARY KEY (service, address, hostname)
        );
        CREATE INDEX IF NOT EXISTS service_addresses_service
            ON service_addresses(service, expires_at);
        -- Hostnames a user adds for a service, so the catalog can be extended
        -- without editing the plugin.
        CREATE TABLE IF NOT EXISTS service_hostnames (
            service  TEXT NOT NULL,
            hostname TEXT NOT NULL,
            added    INTEGER NOT NULL,
            PRIMARY KEY (service, hostname)
        );
    """)
    return connection


def extra_hostnames(connection, service):
    return [row["hostname"] for row in connection.execute(
        "SELECT hostname FROM service_hostnames WHERE service=?", (service,))]


def add_hostname(service, hostname, connection=None):
    """Register an extra hostname for a service."""
    name = (hostname or "").strip().lower().rstrip(".")
    if not name or "." not in name:
        raise ValueError("a hostname is required")
    owned = connection or database()
    try:
        with owned:
            owned.execute(
                "INSERT OR IGNORE INTO service_hostnames(service,hostname,added) VALUES(?,?,?)",
                (service, name, int(time.time())))
    finally:
        if connection is None:
            owned.close()
    return name


def resolve_hostnames(hostnames, resolver=None):
    """Look up each hostname, returning {hostname: [addresses]}.

    A name that does not resolve is simply absent: several catalogued suffixes are
    not hostnames at all (steamcontent.com has no address record), and that is
    normal rather than an error.
    """
    lookup = resolver or _resolve
    found = {}
    for hostname in hostnames:
        name = (hostname or "").strip().lower().rstrip(".")
        if not name:
            continue
        try:
            addresses = sorted(set(lookup(name)))
        except Exception:
            continue
        if addresses:
            found[name] = addresses
    return found


def _resolve(hostname):
    return [info[4][0] for info in socket.getaddrinfo(hostname, None)]


def record(connection, service, hostname, addresses, source, now=None, ttl=None):
    now = int(now if now is not None else time.time())
    ttl = ttl if ttl is not None else (
        OBSERVED_TTL if source == SOURCE_OBSERVED else RESOLVED_TTL)
    for address in addresses:
        connection.execute(
            """INSERT INTO service_addresses(service,address,hostname,source,
                   first_seen,last_seen,expires_at)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(service,address,hostname) DO UPDATE SET
                   last_seen=excluded.last_seen,
                   expires_at=excluded.expires_at,
                   -- An address seen in real traffic outranks one merely looked up.
                   source=CASE WHEN service_addresses.source=? THEN ? ELSE excluded.source END""",
            (service, address, hostname, source, now, now, now + ttl,
             SOURCE_OBSERVED, SOURCE_OBSERVED))


def observed_for(suffixes, mappings):
    """{hostname: [addresses]} from names devices actually resolved."""
    wanted = [s.strip().lower().rstrip(".") for s in suffixes if s and s.strip()]
    found = {}
    for domain, address in mappings or ():
        name = (domain or "").strip().lower().rstrip(".")
        if any(name == suffix or name.endswith("." + suffix) for suffix in wanted):
            found.setdefault(name, set()).add(address)
    return {name: sorted(addresses) for name, addresses in found.items()}


def refresh(catalog, mappings, connection=None, resolver=None, now=None):
    """Update the store from both sources and prune what has expired."""
    now = int(now if now is not None else time.time())
    owned = connection or database()
    summary = []
    try:
        with owned:
            for service, entry in (catalog or {}).items():
                suffixes = list(entry.get("suffixes") or ())
                suffixes += extra_hostnames(owned, service)

                observed = observed_for(suffixes, mappings)
                for hostname, addresses in observed.items():
                    record(owned, service, hostname, addresses, SOURCE_OBSERVED, now)

                resolved = resolve_hostnames(suffixes, resolver)
                for hostname, addresses in resolved.items():
                    record(owned, service, hostname, addresses, SOURCE_RESOLVED, now)

                summary.append({
                    "service": service,
                    "observed_hostnames": len(observed),
                    "observed_addresses": len({a for v in observed.values() for a in v}),
                    "resolved_hostnames": len(resolved),
                    "resolved_addresses": len({a for v in resolved.values() for a in v}),
                })
            pruned = owned.execute(
                "DELETE FROM service_addresses WHERE expires_at < ?", (now,)).rowcount
    finally:
        if connection is None:
            owned.close()
    return {"status": "ok", "services": summary, "pruned": max(0, pruned)}


def addresses_for(service, connection=None, now=None):
    """Live addresses for a service, with the evidence behind each."""
    now = int(now if now is not None else time.time())
    owned = connection or database()
    try:
        rows = owned.execute(
            """SELECT address, source, hostname, last_seen FROM service_addresses
               WHERE service=? AND expires_at >= ? ORDER BY address""",
            (service, now)).fetchall()
    finally:
        if connection is None:
            owned.close()
    result = {}
    for row in rows:
        entry = result.setdefault(row["address"], {
            "address": row["address"], "source": row["source"],
            "hostnames": [], "last_seen": row["last_seen"]})
        entry["hostnames"].append(row["hostname"])
        # Real traffic outranks a lookup when both produced the same address.
        if row["source"] == SOURCE_OBSERVED:
            entry["source"] = SOURCE_OBSERVED
        entry["last_seen"] = max(entry["last_seen"], row["last_seen"])
    return sorted(result.values(), key=lambda item: item["address"])


def inventory(catalog, connection=None, now=None):
    owned = connection or database()
    try:
        result = []
        for service, entry in (catalog or {}).items():
            rows = addresses_for(service, owned, now)
            result.append({
                "service": service,
                "label": entry.get("label", service),
                "total": len(rows),
                "observed": sum(1 for r in rows if r["source"] == SOURCE_OBSERVED),
                "resolved": sum(1 for r in rows if r["source"] == SOURCE_RESOLVED),
            })
        return sorted(result, key=lambda item: item["total"], reverse=True)
    finally:
        if connection is None:
            owned.close()


def main():
    import shaper
    mode = sys.argv[1] if len(sys.argv) > 1 else "refresh"
    if mode == "add" and len(sys.argv) >= 4:
        try:
            name = add_hostname(sys.argv[2], sys.argv[3])
        except ValueError as error:
            print(json.dumps({"status": "failed", "error": str(error)}))
            return
        print(json.dumps({"status": "ok", "service": sys.argv[2], "hostname": name}))
        return
    if mode == "inventory":
        print(json.dumps({"status": "ok",
                          "services": inventory(shaper.STREAMING_SERVICES)},
                         separators=(",", ":")))
        return
    print(json.dumps(refresh(shaper.STREAMING_SERVICES, shaper.load_mappings()),
                     separators=(",", ":")))


if __name__ == "__main__":
    main()
