#!/usr/local/bin/python3
"""Per-service bandwidth limits for streaming and other bulk services.

The point is to cap a service rather than a device: hold Netflix to a 1080p-ish
rate so it stops reaching for 4K, while leaving the rest of the household alone.

How it necessarily works, and what that costs:

  * A shaper matches packets, so it needs addresses. The addresses come from the
    same DNS observations that drive domain attribution: whatever Unbound recently
    answered for the service's hostnames. That makes coverage *partial by
    construction*. A device using DoH/DoT, a VPN, or ECH never populates those
    mappings, so its streams are not matched and run uncapped. The plugin reports
    the address count so the limit is never mistaken for a guarantee.

  * Only services on dedicated hostnames are offered. Capping a shared CDN would
    throttle unrelated traffic that happens to share an address, which is a far
    worse outcome than not capping at all, so those are refused rather than
    approximated.

  * Bitrates are honest about resolution. A cap does not select a resolution; it
    constrains what the player can sustain, and players pick a ladder rung that
    fits. The presets use the rates the services themselves publish.

Computing the plan is pure so it can be tested. Applying it is a thin PHP shim,
because pipes and rules live in the OPNsense TrafficShaper model, and the model is
what makes ipfw load safely through the system's own rc scripts.
"""

import json
import os
import sqlite3
import sys

import consumers

STATE_DIR = "/var/db/wanquota"
PLAN_PATH = os.path.join(STATE_DIR, "shaper-plan.json")

# Pipe numbers the plugin owns. Kept high to stay clear of hand-made pipes.
PIPE_BASE = 21000

# Rates the providers publish for a sustained stream, in Mbit/s. A cap does not
# pick a resolution — it bounds what the player can sustain, and the player picks
# a rung that fits. Naming them after the resolution they support keeps the choice
# meaningful without implying the cap forces it.
RESOLUTION_PRESETS = {
    "4k": 15.0,
    "1080p": 5.0,
    "720p": 3.0,
    "480p": 1.5,
    "audio_only": 0.5,
}

# Services whose media traffic sits on hostnames dedicated to them. A shared CDN
# is deliberately absent: throttling it would hit unrelated traffic on the same
# addresses.
STREAMING_SERVICES = {
    "netflix": {
        "label": "Netflix",
        "suffixes": ("nflxvideo.net", "nflximg.net", "netflix.com"),
    },
    "youtube": {
        "label": "YouTube",
        "suffixes": ("googlevideo.com", "youtube.com", "ytimg.com"),
    },
    "twitch": {
        "label": "Twitch",
        "suffixes": ("ttvnw.net", "twitch.tv", "jtvnw.net"),
    },
    "tiktok": {
        "label": "TikTok",
        "suffixes": ("tiktokcdn.com", "tiktokcdn-us.com", "tiktokv.com", "tiktok.com"),
    },
    "disney": {
        "label": "Disney+",
        "suffixes": ("dssott.com", "disneyplus.com", "bamgrid.com"),
    },
    "prime_video": {
        "label": "Prime Video",
        "suffixes": ("aiv-cdn.net", "aiv-delivery.net", "primevideo.com"),
    },
    "spotify": {
        "label": "Spotify",
        "suffixes": ("scdn.co", "spotify.com", "spotifycdn.com"),
    },
    "appletv": {
        "label": "Apple TV+",
        "suffixes": ("tv.apple.com", "vod-ak-aoc.tv.apple.com"),
    },
    "shahid": {
        "label": "Shahid",
        "suffixes": ("shahid.net", "shahid.mbc.net"),
    },
    "osn": {
        "label": "OSN+",
        "suffixes": ("osn.com", "osnplus.com"),
    },
}

# Suffixes that must never be shaped, whatever a user configures: an address here
# serves many unrelated things, so a cap would land on traffic the user never
# meant to touch.
SHARED_CDN_SUFFIXES = (
    "cloudflare.com", "cloudflare-dns.com", "akamai.net", "akamaiedge.net",
    "akamaihd.net", "akadns.net", "fastly.net", "fastlylb.net", "edgekey.net",
    "edgesuite.net", "cloudfront.net", "gstatic.com", "googleusercontent.com",
    "googleapis.com", "amazonaws.com", "azureedge.net", "windows.net",
)


def is_shared_cdn(suffix):
    """True when a suffix names infrastructure shared with unrelated services."""
    value = (suffix or "").strip().lower().rstrip(".")
    return any(value == shared or value.endswith("." + shared) for shared in SHARED_CDN_SUFFIXES)


def resolve_rate(limit):
    """Mbit/s for a configured limit: an explicit rate, or a resolution preset."""
    if limit.get("mbit") not in (None, "", 0):
        try:
            rate = float(limit["mbit"])
        except (TypeError, ValueError):
            raise ValueError(f"mbit must be a number, got {limit['mbit']!r}")
        if rate <= 0:
            raise ValueError("mbit must be greater than zero")
        return rate
    preset = str(limit.get("resolution") or "").strip().lower()
    if preset in RESOLUTION_PRESETS:
        return RESOLUTION_PRESETS[preset]
    raise ValueError(
        "each limit needs either mbit, or a resolution from: "
        + ", ".join(sorted(RESOLUTION_PRESETS))
    )


def service_addresses(suffixes, mappings):
    """Addresses currently observed for a service's hostnames.

    `mappings` is the domain -> address relation already collected for attribution,
    so no new observation mechanism is introduced and expired entries age out with
    it.
    """
    wanted = [s.strip().lower().rstrip(".") for s in suffixes if s and s.strip()]
    found = set()
    for domain, address in mappings:
        name = (domain or "").strip().lower().rstrip(".")
        if any(name == suffix or name.endswith("." + suffix) for suffix in wanted):
            found.add(address)
    return sorted(found)


def load_mappings(database=None):
    """(domain, address) pairs from the DNS attribution database."""
    path = database or consumers.DOMAIN_DB
    if not os.path.exists(path):
        return []
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return [(row[0], row[1]) for row in
                connection.execute("SELECT domain, ip FROM ip_domains")]
    except sqlite3.Error:
        return []
    finally:
        connection.close()


def build_plan(limits, mappings, catalog=None):
    """Turn configured limits into pipes and rules, with every refusal explained."""
    catalog = catalog or STREAMING_SERVICES
    entries = []
    rejected = []
    number = PIPE_BASE
    for limit in limits or []:
        key = str(limit.get("service") or "").strip().lower()
        if not limit.get("enabled", True):
            continue
        service = catalog.get(key)
        if service is None:
            rejected.append({"service": key or "(unnamed)",
                             "reason": "not a known service; add it to the catalog first"})
            continue
        shared = [s for s in service["suffixes"] if is_shared_cdn(s)]
        if shared:
            rejected.append({
                "service": key,
                "reason": f"refused: {', '.join(shared)} is shared infrastructure, "
                          f"capping it would throttle unrelated traffic",
            })
            continue
        try:
            rate = resolve_rate(limit)
        except ValueError as error:
            rejected.append({"service": key, "reason": str(error)})
            continue
        addresses = service_addresses(service["suffixes"], mappings)
        if not addresses:
            rejected.append({
                "service": key,
                "reason": "no addresses observed yet for this service; nothing to match. "
                          "The list fills in as devices resolve its hostnames.",
            })
            continue
        entries.append({
            "service": key,
            "label": service["label"],
            "mbit": rate,
            "basis": "explicit" if limit.get("mbit") else str(limit.get("resolution", "")).lower(),
            "pipe": number,
            "addresses": addresses,
            "address_count": len(addresses),
        })
        number += 1
    return {
        "pipes": entries,
        "rejected": rejected,
        "note": (
            "Addresses come from recently observed DNS answers, so coverage is partial: "
            "a device using encrypted DNS, a VPN or ECH is not matched and streams "
            "uncapped. A cap bounds the rate a player can sustain rather than selecting "
            "a resolution."
        ),
    }


def write_plan(document):
    os.makedirs(STATE_DIR, mode=0o750, exist_ok=True)
    with open(PLAN_PATH, "w", encoding="utf-8") as handle:
        json.dump(document, handle, separators=(",", ":"))


def options():
    """Shaper settings, read without importing the heavier intelligence module."""
    import xml.etree.ElementTree as ET
    try:
        root = ET.parse(consumers.CONFIG_PATH).getroot()
    except (OSError, ET.ParseError):
        return {"enabled": False, "dry_run": True, "limits": []}
    general = root.find("./OPNsense/WanQuota/general")
    raw = consumers.node_text(general, "service_limits_json", "[]")
    try:
        limits = json.loads(raw)
        limits = limits if isinstance(limits, list) else []
    except json.JSONDecodeError:
        limits = []
    return {
        "enabled": consumers.node_text(general, "shaper_enabled", "0") == "1",
        "dry_run": consumers.node_text(general, "shaper_dry_run", "1") == "1",
        "limits": limits,
    }


def run():
    cfg = options()
    if not cfg["enabled"]:
        document = {"status": "disabled", "pipes": [], "rejected": [],
                    "note": "Per-service limits are disabled."}
        write_plan(document)
        return document
    plan = build_plan(cfg["limits"], load_mappings())
    plan["status"] = "ok"
    plan["dry_run"] = cfg["dry_run"]
    if cfg["dry_run"]:
        plan["note"] = "Dry run: no pipe or rule was created. " + plan["note"]
    write_plan(plan)
    return plan


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if mode == "catalog":
        print(json.dumps({
            "services": [{"service": key, "label": item["label"],
                          "suffixes": list(item["suffixes"])}
                         for key, item in sorted(STREAMING_SERVICES.items())],
            "resolutions": RESOLUTION_PRESETS,
        }, separators=(",", ":")))
        return
    print(json.dumps(run(), separators=(",", ":")))


if __name__ == "__main__":
    main()
