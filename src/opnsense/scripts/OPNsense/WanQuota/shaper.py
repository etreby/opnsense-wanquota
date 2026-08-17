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

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time

import addresses as address_book
import consumers

STATE_DIR = "/var/db/wanquota"
PLAN_PATH = os.path.join(STATE_DIR, "shaper-plan.json")
# Touched by shaper.php whenever rules are installed. Applying reloads the
# shaper, which resets every ipfw counter, so this is the zero point for
# "bytes matched" and the difference between "nothing yet" and "nothing".
INSTALLED_PATH = os.path.join(STATE_DIR, "shaper-installed")

# A packet-capture engine holding /dev/netmap takes traffic off the normal kernel
# path before ipfw's inbound hook runs. Measured on a live firewall running
# Zenarmor: during a 3 MB upload, an ipfw rule matching the device as source with
# no direction and no interface qualifier counted 3 packets / 231 bytes, while a
# download rule on the same device counted 29 MB. Egress from a LAN device is
# therefore invisible to ipfw, so an upload pipe cannot fire no matter how it is
# written. Download shaping is unaffected: it matches on the way out of the LAN
# interface, which ipfw still sees.
NETMAP_DEVICE = "/dev/netmap"

# Pipe numbers the plugin owns. Kept high to stay clear of hand-made pipes.
PIPE_BASE = 21000
# A separate range for device limits, so a service pipe and a device pipe can never
# collide and either can be rebuilt without disturbing the other.
DEVICE_PIPE_BASE = 22000

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
        # Google's cache nodes answer to both names: the address serving a live 720p
        # stream resolved from rr4.sn-vg5obxxb-j5pk.googlevideo.com *and*
        # rr4.sn-vg5obxxb-j5pk.gvt1.com. Without this, those nodes are treated as
        # shared and excluded, which left a YouTube cap matching the page and never
        # the video. gvt1.com also delivers Chrome and Play Store downloads from the
        # same nodes, so a YouTube cap limits those too; the plan reports it.
        "co_delivery": ("gvt1.com",),
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
    "instagram": {
        "label": "Instagram",
        "suffixes": ("instagram.com", "cdninstagram.com"),
    },
    "facebook": {
        "label": "Facebook",
        "suffixes": ("facebook.com", "fb.com", "facebook.net"),
    },
    # fbcdn.net carries media for both Facebook and Instagram, so it is offered on
    # its own rather than filed under either. Putting it under one service would
    # quietly cap the other, and splitting it between both would give two pipes the
    # same addresses.
    "meta_cdn": {
        "label": "Meta CDN (Facebook and Instagram media)",
        "suffixes": ("fbcdn.net",),
    },
    "watchit": {
        "label": "WatchIt",
        "suffixes": ("watchit.com", "watchit-mena.com", "watchit.video"),
    },
    "yango_play": {
        "label": "Yango Play",
        "suffixes": ("yango.com", "yangoplay.com", "yango-play.com"),
    },
    "tod": {
        "label": "TOD",
        "suffixes": ("tod.tv", "todtv.com", "beinsports.com"),
    },
    # Bulk background downloads. Capping these is usually more welcome than capping
    # streaming: nobody is watching them, and they saturate a link for hours.
    "windows_update": {
        "label": "Windows Update",
        "suffixes": ("windowsupdate.com", "update.microsoft.com",
                     "delivery.mp.microsoft.com", "dl.delivery.mp.microsoft.com",
                     "tlu.dl.delivery.mp.microsoft.com"),
    },
    "apple_update": {
        "label": "Apple software update",
        "suffixes": ("swcdn.apple.com", "updates.cdn-apple.com", "mesu.apple.com",
                     "gdmf.apple.com", "appldnld.apple.com"),
    },
    "linux_update": {
        "label": "Linux distribution updates",
        "suffixes": ("archive.ubuntu.com", "security.ubuntu.com", "ports.ubuntu.com",
                     "deb.debian.org", "security.debian.org", "pop-os.org",
                     "archlinux.org", "fedoraproject.org", "rpmfusion.org",
                     "download.opensuse.org", "packages.microsoft.com"),
    },
    "steam_downloads": {
        "label": "Steam downloads",
        # steamcdn-a.akamaihd.net is deliberately absent: it is Akamai, shared with
        # unrelated services, so capping it would throttle traffic that has nothing
        # to do with Steam. The shared-CDN guard rejects the whole service if it is
        # listed, which is the guard doing its job.
        "suffixes": ("steamcontent.com", "steamstatic.com", "steampowered.com",
                     "steamserver.net"),
    },
    "xbox": {
        "label": "Xbox",
        "suffixes": ("xboxlive.com", "xbox.com", "xboxservices.com",
                     "gameclipscontent.xboxlive.com", "assets1.xboxlive.com"),
    },
    "epic_games": {
        "label": "Epic Games",
        "suffixes": ("epicgames.com", "epicgames.dev", "unrealengine.com",
                     "fortnite.com", "ol.epicgames.com"),
    },
    "playstation": {
        "label": "PlayStation",
        "suffixes": ("playstation.net", "playstation.com", "sonyentertainmentnetwork.com"),
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


# A prefix is only capped when this many of its addresses have been observed, all of
# them belonging to the service. One lucky answer is not evidence that a whole /24
# belongs to a CDN, and capping a /24 on that basis could throttle a neighbouring
# service that happens to share the block.
PREFIX_MIN_ADDRESSES = 2
PREFIX_BITS = 24


def _prefix_of(address):
    """The /24 an IPv4 address sits in, or None for anything else."""
    parts = address.split(".")
    if len(parts) != 4 or not all(part.isdigit() for part in parts):
        return None
    return ".".join(parts[:3]) + ".0/24"


def safe_prefixes(suffixes, co_delivery, mappings, minimum=PREFIX_MIN_ADDRESSES):
    """Whole /24s that carry nothing but this service, with the evidence for each.

    Capping individual addresses cannot keep up with YouTube. It hands out
    per-session cache nodes, so the address serving the next video is often one that
    has never been resolved through this firewall — and until it is, that video runs
    uncapped. Measured: a cap held one node to 0.47 Mbit/s while the player simply
    moved to another.

    Where a provider keeps its delivery nodes in dedicated blocks, the block is the
    stable thing to match. The ISP-hosted Google cache on one live network is exactly
    that: every hostname ever seen in 41.91.253.0/24 was googlevideo.com or gvt1.com.
    A new node appearing there is covered the moment it is used, with no observation
    needed.

    The test is strict and it has to be: a prefix is offered only when *every* name
    observed anywhere in it belongs to the service or its co-delivery domains. On the
    same network that rejects 142.251.27.0/24 and 192.178.194.0/24, which hold video
    hostnames alongside google.com, googleapis.com, gstatic.com and doubleclick.net —
    capping those would throttle Search and ordinary browsing.
    """
    wanted = [s.strip().lower().rstrip(".") for s in suffixes if s and s.strip()]
    friendly = {d.strip().lower().rstrip(".") for d in (co_delivery or ()) if d and d.strip()}

    def belongs(name):
        if any(name == suffix or name.endswith("." + suffix) for suffix in wanted):
            return True
        return any(name == domain or name.endswith("." + domain) for domain in friendly)

    names_by_prefix = {}
    addresses_by_prefix = {}
    for domain, address in mappings or ():
        prefix = _prefix_of(address)
        if prefix is None:
            continue
        name = (domain or "").strip().lower().rstrip(".")
        names_by_prefix.setdefault(prefix, set()).add(name)
        addresses_by_prefix.setdefault(prefix, set()).add(address)

    safe = {}
    for prefix, names in names_by_prefix.items():
        addresses = addresses_by_prefix[prefix]
        if len(addresses) < minimum:
            continue
        if not any(belongs(name) for name in names):
            continue
        strangers = sorted({registrable(name) for name in names if not belongs(name)})
        if strangers:
            continue
        # A prefix on shared infrastructure is never offered, whatever its names say.
        if any(is_shared_cdn(name) for name in names):
            continue
        safe[prefix] = {
            "prefix": prefix,
            "addresses": len(addresses),
            "domains": sorted({registrable(name) for name in names}),
        }
    return safe


def collapse_into_prefixes(addresses, prefixes):
    """Replace addresses with the safe prefix that contains them.

    Returns the match list to install. An address inside a capped prefix is dropped
    from the list because the prefix already covers it, so the rule does not carry the
    same traffic twice.
    """
    kept = []
    for address in addresses:
        prefix = _prefix_of(address)
        if prefix is not None and prefix in prefixes:
            continue
        kept.append(address)
    return sorted(prefixes) + kept


def full_catalog():
    """The built-in services plus any discovered service the user accepted.

    Discovery is only worth having if an accepted candidate becomes something the
    Limits tab can cap, so the catalog is the union rather than the hard-coded list.
    A discovery failure must not take the built-in services with it, so it fails soft.
    """
    catalog = dict(STREAMING_SERVICES)
    try:
        import discovery
        for key, entry in discovery.accepted_services().items():
            # A built-in definition always wins: it carries co-delivery domains and
            # curated suffixes that a single discovered domain does not.
            catalog.setdefault(key, entry)
    except Exception:
        pass
    return catalog


def bandwidth_fields(mbit):
    """An integral bandwidth and its metric, for the shaper model.

    The model's bandwidth is an IntegerField with a minimum of 1, so a fractional
    Mbit/s rate is rejected outright: applying a 480p cap failed with "Bandwidth out
    of range." and nothing was created at all. Two of the published presets are
    fractional — 480p is 1.5 and audio-only is 0.5 — so both were unusable, as was
    any hand-entered rate like 2.5.

    Expressing a fractional rate in kbit/s keeps it exact and integral. Whole rates
    stay in Mbit/s so the pipe reads the way the user configured it.
    """
    kbit = max(1, int(round(float(mbit) * 1000)))
    if kbit % 1000 == 0:
        return kbit // 1000, "Mbit"
    return kbit, "Kbit"


def registrable(domain):
    parts = (domain or "").strip().lower().rstrip(".").split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else (parts[0] if parts else "")



def _foreign_names(suffixes, mappings):
    """address -> names on it that do not belong to this service."""
    wanted = [s.strip().lower().rstrip(".") for s in suffixes if s and s.strip()]

    def belongs(name):
        return any(name == suffix or name.endswith("." + suffix) for suffix in wanted)

    per_address = {}
    for domain, address in mappings or ():
        name = (domain or "").strip().lower().rstrip(".")
        if not belongs(name):
            per_address.setdefault(address, set()).add(registrable(name))
    return per_address


def service_addresses(suffixes, mappings, co_delivery=()):
    """Addresses observed for a service, excluding any it shares with others.

    `mappings` is the domain -> address relation already collected for attribution,
    so no new observation mechanism is introduced and expired entries age out with
    it.

    An address is only used when every domain seen on it belongs to this service.
    Checking the suffix list alone is not enough: on real data a third of Netflix's
    addresses also served amazonaws.com, and several of YouTube's also served
    google.com and analytics hosts. Shaping those would have throttled unrelated
    traffic that merely shares an address, which is a worse failure than capping
    less than asked. Returns (exclusive, shared, incidental) so the caller can report
    the cost.

    `co_delivery` names domains that ride the *same* delivery nodes as the service and
    are therefore acceptable to cap with it. This is a correction to the rule above,
    not a loophole in it. Measured on a live network: the address serving a 720p
    YouTube stream resolved from both `rr4.sn-vg5obxxb-j5pk.googlevideo.com` and
    `rr4.sn-vg5obxxb-j5pk.gvt1.com` — one cache node under two Google names. Treating
    the second as a stranger excluded 22 of the 49 observed video nodes, including the
    one actually serving the stream, so the cap matched the page and never the video.
    Anything genuinely unrelated — google.com for Search, gstatic.com, googleapis.com,
    doubleclick.net — is still a stranger and still excludes the address, because
    capping those would throttle ordinary browsing.

    Addresses kept this way are returned in `incidental` with the co-delivery domains
    found on them, so the interface can say what else the cap catches rather than
    quietly widening its reach.
    """
    wanted = [s.strip().lower().rstrip(".") for s in suffixes if s and s.strip()]

    def belongs(name):
        return any(name == suffix or name.endswith("." + suffix) for suffix in wanted)

    per_address = {}
    for domain, address in mappings:
        name = (domain or "").strip().lower().rstrip(".")
        per_address.setdefault(address, set()).add(name)

    friendly = {d.strip().lower().rstrip(".") for d in (co_delivery or ()) if d and d.strip()}

    def rides_along(name):
        """A domain delivered from the same nodes as the service."""
        return any(name == domain or name.endswith("." + domain) for domain in friendly)

    exclusive, shared, incidental = set(), {}, {}
    for address, names in per_address.items():
        if not any(belongs(name) for name in names):
            continue
        outsiders = [name for name in names if not belongs(name)]
        strangers = sorted({registrable(name) for name in outsiders if not rides_along(name)})
        if strangers:
            shared[address] = strangers
            continue
        along = sorted({registrable(name) for name in outsiders if rides_along(name)})
        if along:
            incidental[address] = along
        exclusive.add(address)
    return sorted(exclusive), shared, incidental


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


def build_plan(limits, mappings, catalog=None, stored=None):
    """Turn configured limits into pipes and rules, with every refusal explained.

    `stored` is the service address book: a callable taking a service key and
    returning rows with an address and the evidence behind it. When present its
    addresses are used in addition to whatever the DNS mappings show, which is what
    lets a service be capped before any device happens to resolve it. Addresses
    shared with other names are still excluded, whichever source produced them.
    """
    catalog = catalog if catalog is not None else full_catalog()
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
        addresses, shared, incidental = service_addresses(
            service["suffixes"], mappings, service.get("co_delivery", ()))
        # Fold in the address book, then re-check sharing so a stored address gets
        # exactly the same scrutiny as an observed one.
        book_rows = list(stored(key)) if stored else []
        sources = {}
        if book_rows:
            known_strangers = _foreign_names(service["suffixes"], mappings)
            for row in book_rows:
                candidate = row["address"]
                if candidate in shared:
                    continue
                if candidate in known_strangers:
                    shared[candidate] = sorted(known_strangers[candidate])[:4]
                    continue
                if candidate not in addresses:
                    addresses.append(candidate)
                sources[candidate] = row.get("source", "resolved")
            addresses = sorted(set(addresses))
        if not addresses:
            reason = ("no addresses observed yet for this service; nothing to match. "
                      "The list fills in as devices resolve its hostnames.")
            if shared:
                reason = (f"every observed address is shared with other services "
                          f"({len(shared)} of them), so capping any would throttle "
                          f"unrelated traffic. Nothing safe to match.")
            rejected.append({"service": key, "reason": reason})
            continue
        bandwidth, metric = bandwidth_fields(rate)
        # Prefer whole delivery blocks over individual addresses where the evidence
        # supports it: a rotated cache node inside a capped block is covered without
        # having to be observed first.
        prefixes = safe_prefixes(service["suffixes"], service.get("co_delivery", ()), mappings)
        matches = collapse_into_prefixes(addresses, prefixes)
        entries.append({
            "service": key,
            "label": service["label"],
            "mbit": rate,
            "bandwidth": bandwidth,
            "bandwidth_metric": metric,
            "prefixes": sorted(prefixes),
            "prefix_evidence": [prefixes[name] for name in sorted(prefixes)],
            "basis": "explicit" if limit.get("mbit") else str(limit.get("resolution", "")).lower(),
            "pipe": number,
            "addresses": matches,
            "observed_address_list": addresses,
            "address_count": len(addresses),
            "match_count": len(matches),
            "shared_excluded": len(shared),
            # What else this cap unavoidably limits, because it shares delivery nodes
            # with the service. Reported so the reach is visible, not assumed.
            "also_limits": sorted({d for names in incidental.values() for d in names}),
            "also_limits_addresses": len(incidental),
            "shared_examples": {a: s[:3] for a, s in list(shared.items())[:3]},
            "from_address_book": sum(1 for a in addresses if a in sources),
            "observed_addresses": sum(
                1 for a in addresses if sources.get(a, "observed") == "observed"),
        })
        number += 1
    return {
        "pipes": entries,
        "rejected": rejected,
        "note": (
            "Addresses come from recently observed DNS answers, so coverage is partial: "
            "a device using encrypted DNS, a VPN or ECH is not matched and streams "
            "uncapped. Addresses shared with other services are excluded as well, since "
            "capping them would throttle unrelated traffic; shared_excluded reports how "
            "many. Addresses also come from the plugin's own address book, which the "
            "firewall refreshes by resolving each service's hostnames; observed_addresses "
            "reports how many were seen in real traffic rather than merely looked up, and "
            "a looked-up address for a video service can be the website rather than the "
            "delivery network. A cap bounds the rate a player can sustain rather than "
            "selecting a resolution."
        ),
    }



def device_identities(config_path=None):
    """Current address for every device the firewall can name.

    Returns rows carrying address, MAC and DHCP hostname so a limit can be matched
    on whichever the user configured. A limit keyed to an address alone stops
    applying the moment DHCP moves the device, which is the whole reason MAC and
    hostname are accepted.
    """
    saved = consumers.CONFIG_PATH
    if config_path:
        consumers.CONFIG_PATH = config_path
    try:
        _settings, static_names = consumers.settings_and_names()
    except (OSError, ValueError):
        return []
    finally:
        consumers.CONFIG_PATH = saved
    leases = {**consumers.kea_leases(), **consumers.dnsmasq_leases()}
    ident = consumers.identities(static_names, leases, consumers.arp_macs())
    return [{"address": address, **entry} for address, entry in sorted(ident.items())]


def match_device(limit, devices):
    """The device a limit refers to, by address, MAC or DHCP hostname."""
    wanted = str(limit.get("device") or "").strip().lower()
    if not wanted:
        return None
    for row in devices:
        candidates = {
            str(row.get("address") or "").lower(),
            str(row.get("mac") or "").lower(),
            str(row.get("hostname") or "").lower(),
            str(row.get("name") or "").lower(),
        }
        candidates.discard("")
        if wanted in candidates:
            return row
    return None


# Engines known to take packets off the kernel path via netmap, by the name of the
# process that holds the device. Recognising the product lets the refusal name it
# instead of describing a mechanism the user never configured directly.
NETMAP_ENGINES = {
    "eastpect": "Zenarmor",
    "sensei": "Zenarmor",
    "suricata": "Suricata (netmap mode)",
}


def netmap_interception(fstat_output=None, device_present=None):
    """Report any capture engine holding packets away from ipfw's inbound hook.

    Deliberately fails open. If the state cannot be determined the answer is "no
    interception" and shaping behaves exactly as it did before: a wrong "clear"
    costs an upload cap that does not fire, which `shaper.py verify` then shows as
    zero bytes matched, whereas a wrong "intercepted" would withdraw a feature that
    works on a firewall with no capture engine at all.
    """
    present = os.path.exists(NETMAP_DEVICE) if device_present is None else device_present
    clear = {"active": False, "engine": "", "processes": [], "reason": ""}
    if not present:
        return clear
    text = fstat_output
    if text is None:
        try:
            text = subprocess.run(["/usr/bin/fstat"], capture_output=True, text=True,
                                  timeout=15).stdout
        except Exception:
            return clear
    holders = set()
    for line in (text or "").splitlines():
        fields = line.split()
        # fstat prints USER CMD PID FD MOUNT INUM MODE SZ|DV R/W; the character
        # device appears as its own field, so a path merely containing the word
        # does not count as a holder.
        if len(fields) >= 2 and "netmap" in fields[2:]:
            holders.add(fields[1])
    if not holders:
        return clear
    engines = sorted({NETMAP_ENGINES[name] for name in holders if name in NETMAP_ENGINES})
    engine = engines[0] if engines else sorted(holders)[0]
    return {
        "active": True,
        "engine": engine,
        "processes": sorted(holders),
        "reason": (
            f"{engine} is capturing packets through netmap, which takes traffic off the "
            "kernel path before ipfw sees it entering the LAN interface. Upload caps "
            "cannot fire while it is bound; download caps are unaffected because they "
            "match on the way out to the device."
        ),
    }


def build_device_plan(limits, devices, router=None, interception=None,
                      upload_experimental=False):
    """Turn per-device limits into pipes, with every refusal explained.

    A device cap is gentler than blocking, but the firewall itself is still never
    limited: throttling the router would degrade every service it provides,
    including the interface used to undo the mistake.
    """
    entries = []
    rejected = []
    upload_rejected = []
    seen = {}
    number = DEVICE_PIPE_BASE
    intercepted = bool((interception or {}).get("active"))
    # With the experimental switch on, an intercepted firewall shapes uploads through
    # ipfw's layer2 hook instead of refusing them. Measured on hardware: a layer2 rule
    # counted 3,005 packets / 4.07 MB of a device's uploads in a window where the same
    # match at layer 3 counted 3 packets, because netmap diverts the traffic before the
    # IP hook but not before the ethernet hook.
    via_layer2 = intercepted and bool(upload_experimental)
    blocked = intercepted and not via_layer2
    for limit in limits or []:
        if not limit.get("enabled", True):
            continue
        key = str(limit.get("device") or "").strip()
        if not key:
            rejected.append({"device": "(unnamed)", "reason": "no device given"})
            continue
        row = match_device(limit, devices)
        if row is None:
            rejected.append({
                "device": key,
                "reason": "no device on the network matches that address, MAC or hostname",
            })
            continue
        if router and row["address"] == router:
            rejected.append({"device": key, "reason": "refused: this is the firewall itself"})
            continue
        try:
            rate = resolve_rate(limit)
        except ValueError as error:
            rejected.append({"device": key, "reason": str(error)})
            continue
        upload = limit.get("upload_mbit")
        try:
            upload_rate = float(upload) if upload not in (None, "", 0) else None
        except (TypeError, ValueError):
            rejected.append({"device": key, "reason": "upload_mbit must be a number"})
            continue
        if upload_rate is not None and upload_rate <= 0:
            rejected.append({"device": key, "reason": "upload_mbit must be greater than zero"})
            continue
        # Two entries can name the same device by different identifiers — an address
        # and a MAC, say. Building both would give one device two pipes competing
        # over the same traffic, so the later entry is refused rather than silently
        # producing a rate nobody configured.
        if row["address"] in seen:
            rejected.append({
                "device": key,
                "reason": f"already limited by the entry for {seen[row['address']]!r}; "
                          f"one device can carry one limit",
            })
            continue
        seen[row["address"]] = key
        # An upload pipe on a firewall whose LAN ingress is intercepted would be
        # built, saved and reported as applied while shaping nothing. Refusing the
        # upload half and keeping the download cap is the honest outcome: the user
        # sees why, instead of a limit they believe in and cannot observe failing.
        if blocked and upload_rate is not None:
            upload_rejected.append({
                "device": key,
                "name": row.get("name") or row["address"],
                "upload_mbit": upload_rate,
                "reason": (interception or {}).get("reason", "LAN ingress is not visible to ipfw"),
            })
            upload_rate = None
        bandwidth, metric = bandwidth_fields(rate)
        upload_bandwidth, upload_metric = (
            bandwidth_fields(upload_rate) if upload_rate is not None else (None, None))
        entries.append({
            "device": row["address"],
            "name": row.get("name") or row["address"],
            "mac": row.get("mac", ""),
            "matched": key,
            "mbit": rate,
            "bandwidth": bandwidth,
            "bandwidth_metric": metric,
            "upload_bandwidth": upload_bandwidth,
            "upload_bandwidth_metric": upload_metric,
            "upload_mbit": upload_rate,
            "basis": "explicit" if limit.get("mbit") else str(limit.get("resolution", "")).lower(),
            "pipe": number,
            "upload_pipe": number + 500 if upload_rate is not None else None,
            # True when the upload cap needs the raw layer2 rule rather than a shaper
            # rule. shaper.php still creates the pipe; the rule comes from layer2.py.
            "upload_layer2": bool(via_layer2 and upload_rate is not None),
        })
        number += 1
    return {
        "device_pipes": entries,
        "device_rejected": rejected,
        "upload_rejected": upload_rejected,
        "interception": interception or {"active": False, "engine": "", "processes": [], "reason": ""},
        "upload_via_layer2": via_layer2,
        "device_note": (
            "A device limit caps the rate to and from one device, matched on its current "
            "address. Because the address is resolved at apply time, a limit keyed to a "
            "MAC or DHCP hostname keeps applying after the address changes; one keyed to "
            "an address alone does not."
        ),
    }

"""Rules ipfw is running for this plugin, with the bytes each has matched."""
RULE_PATTERN = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+pipe\s+(\d+)\s+(.*)$")


def parse_rule_counters(listing, service_base=PIPE_BASE, device_base=DEVICE_PIPE_BASE):
    """Extract per-rule packet and byte counters from `ipfw -a list` output.

    The counters are the only direct evidence that a limit is doing anything. A rule
    that has matched no bytes while the device is active is a limit that is not
    working, and saying so is more useful than reporting it as applied.
    """
    rows = []
    for line in (listing or "").splitlines():
        found = RULE_PATTERN.match(line)
        if not found:
            continue
        rule, packets, octets, pipe, spec = found.groups()
        pipe = int(pipe)
        if service_base <= pipe < service_base + 1000:
            kind = "service"
        elif device_base <= pipe < device_base + 500:
            kind = "device-download"
        elif device_base + 500 <= pipe < device_base + 1000:
            kind = "device-upload"
        else:
            continue
        rows.append({
            "rule": int(rule),
            "pipe": pipe,
            "kind": kind,
            "packets": int(packets),
            "bytes": int(octets),
            # The trailing uuid comment is noise for a reader trying to see which
            # traffic the rule describes.
            "match": spec.split("//")[0].strip(),
        })
    return sorted(rows, key=lambda row: row["pipe"])


# Below this age, a rule that has matched nothing is telling you nothing. Applying
# reloads the shaper, which resets every ipfw counter, so a Verify run straight after
# saving would otherwise report every limit as dead.
SETTLING_SECONDS = 180


def installed_age(path=None, now=None):
    """Seconds since rules were last installed, or None if never recorded."""
    try:
        stamp = os.path.getmtime(path or INSTALLED_PATH)
    except OSError:
        return None
    return max(0, int((now if now is not None else time.time()) - stamp))


def rule_labels(plan=None):
    """pipe number -> what a person calls it.

    The rule's own match text is an ipfw table name built from a uuid, which tells a
    reader nothing about which service they are looking at.
    """
    document = plan
    if document is None:
        try:
            with open(PLAN_PATH, encoding="utf-8") as handle:
                document = json.load(handle)
        except (OSError, ValueError):
            return {}
    labels = {}
    for entry in (document or {}).get("pipes") or ():
        labels[entry.get("pipe")] = entry.get("label") or entry.get("service") or ""
    for entry in (document or {}).get("device_pipes") or ():
        name = entry.get("name") or entry.get("device") or ""
        labels[entry.get("pipe")] = name
        if entry.get("upload_pipe"):
            labels[entry["upload_pipe"]] = name
    return {number: label for number, label in labels.items() if number is not None}


def verify(listing=None, interception=None, plan=None, age=None):
    """Report what each of the plugin's shaper rules has actually matched."""
    text = listing
    if text is None:
        try:
            text = subprocess.run(["/sbin/ipfw", "-a", "list"], capture_output=True,
                                  text=True, timeout=15).stdout
        except Exception as error:
            return {"status": "failed", "error": f"could not read ipfw rules: {error}",
                    "rules": []}
    rows = parse_rule_counters(text)
    state = interception if interception is not None else netmap_interception()
    labels = rule_labels(plan)
    for row in rows:
        row["label"] = labels.get(row["pipe"], "")
    seconds = installed_age() if age is None else age
    settling = seconds is not None and seconds < SETTLING_SECONDS
    idle = [row["pipe"] for row in rows if row["bytes"] == 0]

    if settling:
        note = (
            f"Rules were installed {seconds} seconds ago, and applying resets every "
            "counter, so a rule showing nothing here has simply had no traffic yet. "
            f"Wait until they have been running for {SETTLING_SECONDS // 60} minutes "
            "of normal use before reading anything into a zero."
        )
    elif state.get("active"):
        note = (
            "Bytes are counted since the rules were last installed. A rule that has "
            "matched nothing while its service or device was in use is not limiting "
            "anything — on this firewall that is expected for upload rules, which "
            "cannot match at all."
        )
    else:
        note = (
            "Bytes are counted since the rules were last installed. A rule that has "
            "matched nothing while its service or device was in use is not limiting "
            "anything."
        )
    return {
        "status": "ok",
        "rules": rows,
        "interception": state,
        "installed_seconds_ago": seconds,
        # True when the counters are too fresh to draw a conclusion from. The
        # interface uses this to avoid marking every rule as dead right after a save.
        "settling": settling,
        "idle": idle,
        "note": note,
    }


APPLIED_PATH = os.path.join(STATE_DIR, "shaper-applied.json")


def plan_fingerprint(plan):
    """A digest of everything about a plan that changes what gets shaped.

    Addresses are included, not just rates: a service cap is only as good as the
    address set behind it, and that set moves. YouTube hands out per-session cache
    nodes, so a cap applied an hour ago can hold none of the addresses a new stream
    uses — measured exactly that way, a 720p stream ran untouched past a 0.5 Mbit
    cap until the plan was applied again with the node it was using.
    """
    material = {
        "status": plan.get("status"),
        "dry_run": bool(plan.get("dry_run")),
        "services": sorted(
            [entry["service"], entry["bandwidth"], entry["bandwidth_metric"],
             sorted(entry.get("addresses") or ())]
            for entry in plan.get("pipes") or ()),
        "devices": sorted(
            [entry["device"], entry["bandwidth"], entry["bandwidth_metric"],
             entry.get("upload_bandwidth"), entry.get("upload_bandwidth_metric")]
            for entry in plan.get("device_pipes") or ()),
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read_applied(path=None):
    try:
        with open(path or APPLIED_PATH, encoding="utf-8") as handle:
            return json.load(handle).get("fingerprint")
    except (OSError, ValueError):
        return None


def write_applied(fingerprint, path=None):
    target = path or APPLIED_PATH
    os.makedirs(os.path.dirname(target), mode=0o750, exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump({"fingerprint": fingerprint}, handle)


def needs_apply(plan, previous):
    """Whether the running shaper no longer matches the plan.

    Applying rewrites the configuration and reloads services, so it is done only
    when something that affects shaping actually changed. A change to 'disabled' or
    to dry-run counts, because that is how a limit gets released.
    """
    return plan_fingerprint(plan) != previous


def sync(applied_path=None, runner=None):
    """Recompute the plan and apply it if what should be shaped has changed.

    Called from the five-minute collector, so a service cap follows its addresses
    instead of decaying into a rule that matches nothing. Without this the feature
    only works until the CDN moves.
    """
    plan = run()
    fingerprint = plan_fingerprint(plan)
    previous = read_applied(applied_path)
    if fingerprint == previous:
        return {"status": "ok", "applied": False, "reason": "nothing that affects shaping changed"}
    invoke = runner or _apply_now
    result = invoke()
    if result.get("ok"):
        write_applied(fingerprint, applied_path)
    return {"status": "ok" if result.get("ok") else "failed", "applied": bool(result.get("ok")),
            "addresses": sum(len(e.get("addresses") or ()) for e in plan.get("pipes") or ()),
            "detail": result.get("detail", "")}


def _apply_now():
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shaper.php")
    try:
        done = subprocess.run(["/usr/local/bin/php", script, "apply"],
                              capture_output=True, text=True, timeout=180)
    except Exception as error:
        return {"ok": False, "detail": str(error)}
    return {"ok": done.returncode == 0,
            "detail": (done.stdout or done.stderr or "").strip()[-400:]}


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
    try:
        device_limits = json.loads(consumers.node_text(general, "device_limits_json", "[]"))
        device_limits = device_limits if isinstance(device_limits, list) else []
    except json.JSONDecodeError:
        device_limits = []
    return {
        "enabled": consumers.node_text(general, "shaper_enabled", "0") == "1",
        "dry_run": consumers.node_text(general, "shaper_dry_run", "1") == "1",
        "upload_experimental": consumers.node_text(
            general, "shaper_upload_experimental", "0") == "1",
        "limits": limits,
        "device_limits": device_limits,
    }


def run():
    cfg = options()
    if not cfg["enabled"]:
        # The interception state is reported even when limits are off, so the Limits
        # tab can warn that upload caps will not work on this firewall *before* the
        # user configures one and waits for it to take effect.
        document = {"status": "disabled", "pipes": [], "rejected": [],
                    "device_pipes": [], "device_rejected": [], "upload_rejected": [],
                    "interception": netmap_interception(),
                    "note": "Per-service and per-device limits are disabled."}
        write_plan(document)
        return document
    book = address_book.database()
    try:
        plan = build_plan(
            cfg["limits"], load_mappings(),
            stored=lambda key: address_book.addresses_for(key, book),
        )
    finally:
        book.close()
    router = None
    try:
        settings, _names = consumers.settings_and_names()
        router = settings["router"]
    except (OSError, ValueError, KeyError):
        pass
    plan.update(build_device_plan(cfg["device_limits"], device_identities(), router,
                                  interception=netmap_interception(),
                                  upload_experimental=cfg.get("upload_experimental")))
    plan["status"] = "ok"
    plan["dry_run"] = cfg["dry_run"]
    if cfg["dry_run"]:
        plan["note"] = "Dry run: no pipe or rule was created. " + plan["note"]
    write_plan(plan)
    return plan


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if mode == "devices":
        print(json.dumps({"status": "ok", "devices": device_identities()},
                         separators=(",", ":")))
        return
    if mode == "sync":
        print(json.dumps(sync(), separators=(",", ":")))
        return
    if mode == "verify":
        print(json.dumps(verify(), separators=(",", ":")))
        return
    if mode == "capability":
        print(json.dumps({"status": "ok", "interception": netmap_interception()},
                         separators=(",", ":")))
        return
    if mode == "catalog":
        print(json.dumps({
            "services": [{"service": key, "label": item["label"],
                          "suffixes": list(item["suffixes"]),
                          "discovered": bool(item.get("discovered"))}
                         for key, item in sorted(full_catalog().items())],
            "resolutions": RESOLUTION_PRESETS,
        }, separators=(",", ":")))
        return
    print(json.dumps(run(), separators=(",", ":")))


if __name__ == "__main__":
    main()
