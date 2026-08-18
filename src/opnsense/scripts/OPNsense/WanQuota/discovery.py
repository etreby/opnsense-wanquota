#!/usr/local/bin/python3
"""Find services on the network that the catalog does not know yet.

What this is, stated plainly
----------------------------
This is not a language model and it does not consult anything off the firewall. It is
inference over two things the plugin already collects: the domains devices resolved
through Unbound, and the bytes the flow database attributes to those domains. From
those it answers three questions:

  1. Which registrable domains are moving real traffic and belong to no known service?
     Those are candidate services — this is how Viber, Snapchat or a regional
     messenger appears without anyone adding it by hand.

  2. Do a candidate's addresses overlap a service already in the catalog? If most of
     them do, it is almost certainly a new delivery domain for that service rather
     than a new service, and it is proposed as an extra suffix instead. That is how a
     service picks up new URLs as its provider rotates them.

  3. Could it be capped if accepted? A candidate on dedicated addresses can be shaped;
     one sharing addresses with unrelated traffic cannot, and saying so up front avoids
     accepting something that would then be refused.

Why a candidate is not applied automatically
--------------------------------------------
Accepting a candidate makes it shapeable, and shaping the wrong thing throttles
traffic the household needs. Discovery therefore proposes and records evidence; a
person accepts. An ignored candidate stays ignored rather than reappearing every five
minutes, because a discovery feature that nags is one that gets switched off.

Naming
------
Where a registrable domain is recognised it is given its proper name and category from
a seed table. Where it is not, the candidate is named after the domain itself and
labelled as such. Guessing a friendly name from an unknown domain would produce
confident nonsense, so it is not attempted.
"""

import json
import os
import sqlite3
import sys
import time

import consumers

STATE_DIR = "/var/db/wanquota"
DB_PATH = os.path.join(STATE_DIR, "discovery.sqlite")

# Traffic below this is not evidence of a service worth capping, only of a lookup.
MINIMUM_BYTES = 5 * 1024 * 1024

# How much of a candidate's addresses must be shared with a catalogued service before
# it is read as that service's new delivery domain rather than a service of its own.
OVERLAP_FRACTION = 0.5

# Registrable domains worth naming properly when they turn up. Deliberately a naming
# aid and nothing more: presence here does not accept a candidate, and absence does not
# hide one. Categories match the reporting categories already in use.
SEED_NAMES = {
    "whatsapp.com": ("WhatsApp", "Messaging"),
    "whatsapp.net": ("WhatsApp", "Messaging"),
    "viber.com": ("Viber", "Messaging"),
    "vibercdn.com": ("Viber", "Messaging"),
    "telegram.org": ("Telegram", "Messaging"),
    "t.me": ("Telegram", "Messaging"),
    "telegram-cdn.org": ("Telegram", "Messaging"),
    "snapchat.com": ("Snapchat", "Social"),
    "sc-cdn.net": ("Snapchat", "Social"),
    "snap-dev.net": ("Snapchat", "Social"),
    "signal.org": ("Signal", "Messaging"),
    "signal.art": ("Signal", "Messaging"),
    "messenger.com": ("Facebook Messenger", "Messaging"),
    "imo.im": ("imo", "Messaging"),
    "botim.me": ("BOTIM", "Messaging"),
    "skype.com": ("Skype", "Messaging"),
    "discord.com": ("Discord", "Messaging"),
    "discord.gg": ("Discord", "Messaging"),
    "zoom.us": ("Zoom", "Conferencing"),
    "teams.microsoft.com": ("Microsoft Teams", "Conferencing"),
    "webex.com": ("Webex", "Conferencing"),
    "tiktokcdn.com": ("TikTok", "Streaming"),
    "twitch.tv": ("Twitch", "Streaming"),
    "vimeo.com": ("Vimeo", "Streaming"),
    "dailymotion.com": ("Dailymotion", "Streaming"),
    "soundcloud.com": ("SoundCloud", "Streaming"),
    "anghami.com": ("Anghami", "Streaming"),
    "deezer.com": ("Deezer", "Streaming"),
    "shahid.net": ("Shahid", "Streaming"),
    "starzplay.com": ("STARZPLAY", "Streaming"),
    "osn.com": ("OSN+", "Streaming"),
    "linkedin.com": ("LinkedIn", "Social"),
    "x.com": ("X", "Social"),
    "twitter.com": ("X", "Social"),
    "twimg.com": ("X", "Social"),
    "reddit.com": ("Reddit", "Social"),
    "redditmedia.com": ("Reddit", "Social"),
    "pinterest.com": ("Pinterest", "Social"),
    "roblox.com": ("Roblox", "Gaming"),
    "riotgames.com": ("Riot Games", "Gaming"),
    "blizzard.com": ("Blizzard", "Gaming"),
    "nintendo.net": ("Nintendo", "Gaming"),
    "dropbox.com": ("Dropbox", "Cloud storage"),
    "onedrive.com": ("OneDrive", "Cloud storage"),
    "mega.nz": ("MEGA", "Cloud storage"),
    "backblazeb2.com": ("Backblaze", "Cloud storage"),
}


def database(path=None):
    target = path or DB_PATH
    os.makedirs(os.path.dirname(target), mode=0o750, exist_ok=True)
    connection = sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS discovered_services (
            domain      TEXT PRIMARY KEY,
            label       TEXT NOT NULL,
            category    TEXT NOT NULL,
            named_from  TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'new',
            belongs_to  TEXT NOT NULL DEFAULT '',
            cappable    INTEGER NOT NULL DEFAULT 0,
            infrastructure INTEGER NOT NULL DEFAULT 0,
            addresses   INTEGER NOT NULL DEFAULT 0,
            shared      INTEGER NOT NULL DEFAULT 0,
            hostnames   TEXT NOT NULL DEFAULT '[]',
            bytes_seen  INTEGER NOT NULL DEFAULT 0,
            first_seen  INTEGER NOT NULL,
            last_seen   INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS discovered_status
            ON discovered_services(status, bytes_seen);
    """)
    return connection


def registrable(domain):
    """Reuse the shaper's notion of a registrable domain, so both agree."""
    import shaper
    return shaper.registrable(domain)


def covered_domains(catalog=None, apps=None, custom=None):
    """Registrable domains already claimed by something, so they are not "new"."""
    import shaper
    import intelligence

    known = set()
    for entry in (catalog if catalog is not None else shaper.STREAMING_SERVICES).values():
        for suffix in entry.get("suffixes", ()):
            known.add(registrable(suffix))
        for suffix in entry.get("co_delivery", ()) or ():
            known.add(registrable(suffix))
    definitions = apps if apps is not None else intelligence.APP_DEFINITIONS
    for suffixes in definitions.values():
        for suffix in suffixes:
            known.add(registrable(suffix))
    for entry in (custom or []):
        for suffix in entry.get("suffixes", ()) or ():
            known.add(registrable(suffix))
    known.discard("")
    return known


def _addresses_by_registrable(mappings):
    grouped = {}
    hostnames = {}
    for domain, address in mappings or ():
        name = (domain or "").strip().lower().rstrip(".")
        if not name:
            continue
        key = registrable(name)
        if not key:
            continue
        grouped.setdefault(key, set()).add(address)
        hostnames.setdefault(key, set()).add(name)
    return grouped, hostnames


def _traffic_by_registrable(domain_totals):
    totals = {}
    for row in domain_totals or ():
        name = (row.get("domain") or "").strip().lower().rstrip(".")
        amount = float(row.get("total") or 0)
        if not name or amount <= 0:
            continue
        key = registrable(name)
        if key:
            totals[key] = totals.get(key, 0) + amount
    return totals


def owning_service(addresses, mappings, catalog=None, fraction=OVERLAP_FRACTION):
    """A catalogued service whose addresses these mostly are, if there is one.

    Address overlap is stronger evidence than a name: a provider that starts serving
    from a new domain keeps serving from the same machines. This is what turns "an
    unknown domain appeared" into "this service gained a delivery domain".
    """
    import shaper

    entries = catalog if catalog is not None else shaper.STREAMING_SERVICES
    wanted = set(addresses or ())
    if not wanted:
        return ""

    def observed_for(suffixes):
        """Every address seen under these suffixes, exclusive or not.

        Deliberately not service_addresses(): that excludes an address shared with
        another name, and the new domain being investigated is exactly such a name. The
        question here is "are these the same machines", not "may they be capped".
        """
        wanted_suffixes = [s.strip().lower().rstrip(".") for s in suffixes if s]
        seen = set()
        for domain, address in mappings or ():
            name = (domain or "").strip().lower().rstrip(".")
            if any(name == suffix or name.endswith("." + suffix)
                   for suffix in wanted_suffixes):
                seen.add(address)
        return seen

    best, best_share = "", 0.0
    for key, entry in entries.items():
        overlap = wanted & observed_for(entry["suffixes"])
        share = len(overlap) / len(wanted)
        if share > best_share:
            best, best_share = key, share
    return best if best_share >= fraction else ""


def candidates(mappings, domain_totals, catalog=None, apps=None, custom=None,
               minimum_bytes=MINIMUM_BYTES, now=None):
    """Services the network is using that nothing in the catalog accounts for."""
    import shaper

    now = int(now if now is not None else time.time())
    known = covered_domains(catalog, apps, custom)
    grouped, hostnames = _addresses_by_registrable(mappings)
    traffic = _traffic_by_registrable(domain_totals)

    found = []
    for key, addresses in grouped.items():
        if key in known:
            continue
        moved = traffic.get(key, 0)
        if moved < minimum_bytes:
            continue
        if key in SEED_NAMES:
            label, category = SEED_NAMES[key]
            basis = "known domain"
        else:
            # Guessing a friendly name from an unknown domain would produce confident
            # nonsense, so the domain is the name and the basis says so.
            label, category = key, "Unclassified"
            basis = "named after the domain, which is all the evidence supports"
        exclusive, shared, _incidental = shaper.service_addresses(
            (key,), mappings, ())
        belongs = owning_service(addresses, mappings, catalog)
        # A CDN is not a service anyone means to limit, and it will always be near the
        # top by traffic, so it is flagged and sorted below real candidates rather than
        # dominating the list.
        infrastructure = shaper.is_shared_cdn(key)
        found.append({
            "domain": key,
            "label": label,
            "category": category,
            "named_from": basis,
            "hostnames": sorted(hostnames.get(key, ()))[:20],
            "hostname_count": len(hostnames.get(key, ())),
            "addresses": len(exclusive),
            "shared": len(shared),
            # Whether accepting it would produce a limit that can actually match.
            "cappable": bool(exclusive) and not infrastructure,
            "infrastructure": infrastructure,
            "belongs_to": belongs,
            "bytes_seen": int(moved),
            "first_seen": now,
            "last_seen": now,
        })
    found.sort(key=lambda item: (item["infrastructure"], -item["bytes_seen"]))
    return found


def record(found, connection=None, now=None):
    """Store candidates, preserving a decision already made about one."""
    now = int(now if now is not None else time.time())
    owned = connection or database()
    added = updated = 0
    try:
        with owned:
            for item in found:
                existing = owned.execute(
                    "SELECT status, first_seen FROM discovered_services WHERE domain=?",
                    (item["domain"],)).fetchone()
                if existing is None:
                    owned.execute(
                        """INSERT INTO discovered_services
                           (domain,label,category,named_from,status,belongs_to,cappable,
                            infrastructure,addresses,shared,hostnames,bytes_seen,
                            first_seen,last_seen)
                           VALUES(?,?,?,?,'new',?,?,?,?,?,?,?,?,?)""",
                        (item["domain"], item["label"], item["category"], item["named_from"],
                         item["belongs_to"], int(item["cappable"]),
                         int(item.get("infrastructure", False)), item["addresses"],
                         item["shared"], json.dumps(item["hostnames"]), item["bytes_seen"],
                         now, now))
                    added += 1
                else:
                    # The evidence is refreshed; the decision is not revisited, so an
                    # ignored candidate stays ignored instead of returning every run.
                    owned.execute(
                        """UPDATE discovered_services SET label=?,category=?,named_from=?,
                               belongs_to=?,cappable=?,infrastructure=?,addresses=?,
                               shared=?,hostnames=?,bytes_seen=?,last_seen=?
                           WHERE domain=?""",
                        (item["label"], item["category"], item["named_from"],
                         item["belongs_to"], int(item["cappable"]),
                         int(item.get("infrastructure", False)), item["addresses"],
                         item["shared"], json.dumps(item["hostnames"]), item["bytes_seen"],
                         now, item["domain"]))
                    updated += 1
    finally:
        if connection is None:
            owned.close()
    return {"added": added, "updated": updated}


def prune_covered(connection=None, catalog=None, apps=None):
    """Forget candidates that a service now claims.

    A candidate is stored when nothing accounted for it. Once something does — because
    it was added to the catalogue, or accepted, or the app classifier gained it — the
    row is stale and listing it says the opposite of the truth. nflxso.net stayed on the
    list as 'Unclassified, likely part of netflix' after being added to Netflix, which is
    exactly the confusion the discovery panel exists to remove.
    """
    known = covered_domains(catalog, apps)
    owned = connection or database()
    try:
        rows = [row["domain"] for row in
                owned.execute("SELECT domain FROM discovered_services").fetchall()]
        stale = [domain for domain in rows if domain in known]
        if stale:
            with owned:
                owned.executemany("DELETE FROM discovered_services WHERE domain=?",
                                  [(domain,) for domain in stale])
    finally:
        if connection is None:
            owned.close()
    return stale


def listing(status=None, connection=None, prune=True):
    # A row for a domain a service now claims is stale, so it is dropped rather than
    # shown: the panel is meant to answer "what is not accounted for".
    if prune:
        try:
            prune_covered(connection)
        except Exception:
            pass
    owned = connection or database()
    try:
        if status:
            rows = owned.execute(
                """SELECT * FROM discovered_services WHERE status=?
                   ORDER BY infrastructure ASC, bytes_seen DESC""",
                (status,)).fetchall()
        else:
            rows = owned.execute(
                """SELECT * FROM discovered_services
                   ORDER BY infrastructure ASC, bytes_seen DESC""").fetchall()
    finally:
        if connection is None:
            owned.close()
    result = []
    for row in rows:
        item = dict(row)
        item["cappable"] = bool(item["cappable"])
        item["infrastructure"] = bool(item.get("infrastructure"))
        try:
            item["hostnames"] = json.loads(item["hostnames"])
        except ValueError:
            item["hostnames"] = []
        result.append(item)
    return result


def set_status(domain, status, connection=None):
    if status not in ("new", "accepted", "ignored"):
        raise ValueError("status must be new, accepted or ignored")
    key = (domain or "").strip().lower()
    if not key:
        raise ValueError("a domain is required")
    owned = connection or database()
    try:
        with owned:
            changed = owned.execute(
                "UPDATE discovered_services SET status=? WHERE domain=?",
                (status, key)).rowcount
    finally:
        if connection is None:
            owned.close()
    if not changed:
        raise ValueError(f"{key} has not been discovered")
    return {"status": "ok", "domain": key, "state": status}


def accepted_services(connection=None):
    """Accepted candidates in the shape the shaper catalog uses.

    This is the point of the whole feature: an accepted candidate becomes something the
    Limits tab can cap, rather than an entry on a list.
    """
    services = {}
    # No pruning here: this is called while the shaper builds its catalogue, and a
    # database write on every plan would be wasted work.
    for item in listing("accepted", connection, prune=False):
        key = item["domain"].replace(".", "_")
        services[key] = {
            "label": item["label"],
            "suffixes": (item["domain"],),
            "discovered": True,
        }
    return services


def run(period="thirty", connection=None):
    import shaper

    try:
        report = consumers.report(period)
    except Exception as error:
        return {"status": "failed", "error": str(error), "candidates": []}
    found = candidates(shaper.load_mappings(), report.get("domains") or [])
    stored = record(found, connection)
    return {
        "status": "ok",
        "period": period,
        "found": len(found),
        **stored,
        "candidates": listing("new", connection),
        "note": (
            "Inferred from observed DNS answers and attributed flow bytes, on this "
            "firewall only. A candidate is proposed, never applied: accepting one makes "
            "it shapeable, and shaping the wrong thing throttles traffic the household "
            "needs. 'belongs_to' means most of its addresses are already served by that "
            "service, so it is likely a new delivery domain rather than a new service."
        ),
    }


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "scan"
    if mode == "list":
        print(json.dumps({"status": "ok", "services": listing()}, separators=(",", ":")))
        return
    if mode in ("accept", "ignore", "reset") and len(sys.argv) >= 3:
        state = {"accept": "accepted", "ignore": "ignored", "reset": "new"}[mode]
        try:
            print(json.dumps(set_status(sys.argv[2], state), separators=(",", ":")))
        except ValueError as error:
            print(json.dumps({"status": "failed", "error": str(error)}))
        return
    period = sys.argv[2] if len(sys.argv) > 2 else "thirty"
    print(json.dumps(run(period), separators=(",", ":")))


if __name__ == "__main__":
    main()
