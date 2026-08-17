#!/usr/local/bin/python3
"""Persistent analytics, policy recommendations, notifications and exports."""

import datetime as dt
import csv
import fcntl
import hashlib
import ipaddress
import json
import math
import os
import smtplib
import socket
import sqlite3
import statistics
import io
import subprocess
import sys
import urllib.request
import urllib.parse
from email.message import EmailMessage
import xml.etree.ElementTree as ET

import consumers
import report

STATE_DIR = "/var/db/wanquota"
DB_PATH = os.path.join(STATE_DIR, "intelligence.sqlite")
CONFIG_PATH = "/conf/config.xml"
# App-oriented categories, matched by domain suffix. Named for what the traffic is
# *for* rather than who operates it, because "28% Media Streaming" answers a
# question about the household and "28% googlevideo.com" does not.
#
# The list is deliberately suffix-based and conservative: a domain that matches
# nothing lands in Uncategorised rather than being guessed into a bucket, so the
# breakdown never overstates how much it understands. Extend it from the settings
# page with domain_categories_json; user entries win over these.
BUILTIN_CATEGORIES = {
    "Media Streaming": (
        "youtube.com", "googlevideo.com", "ytimg.com", "netflix.com", "nflxvideo.net",
        "tiktok.com", "tiktokcdn.com", "twitch.tv", "ttvnw.net", "spotify.com",
        "scdn.co", "primevideo.com", "aiv-cdn.net", "hbomax.com", "max.com",
        "disneyplus.com", "dssott.com", "shahid.net", "osn.com", "soundcloud.com",
        "vimeo.com", "plex.tv", "plex.direct", "jellyfin.org", "sndcdn.com",
    ),
    "Secure Web Browsing": (
        "cloudflare.com", "cloudflare-dns.com", "cloudflaressl.com", "akamai.net",
        "akamaiedge.net", "akamaihd.net", "akadns.net", "fastly.net", "fastlylb.net",
        "edgekey.net", "edgesuite.net", "cloudfront.net", "gstatic.com",
        "googleusercontent.com", "jsdelivr.net", "unpkg.com", "letsencrypt.org",
        "digicert.com", "sectigo.com", "ocsp.pki.goog",
    ),
    "Online Utility": (
        "windowsupdate.com", "update.microsoft.com", "delivery.mp.microsoft.com",
        "ubuntu.com", "canonical.com", "debian.org", "pop-os.org", "archlinux.org",
        "githubusercontent.com", "github.com", "githubassets.com", "ghcr.io",
        "docker.io", "docker.com", "npmjs.org", "pypi.org", "pythonhosted.org",
        "gvt1.com", "gvt2.com", "aaplimg.com", "mzstatic.com", "swcdn.apple.com",
        "storjshare.io", "db-ip.com",
    ),
    "A.I. Tools": (
        "anthropic.com", "claude.ai", "openai.com", "chatgpt.com", "oaistatic.com",
        "oaiusercontent.com", "gemini.google.com", "bard.google.com",
        "generativelanguage.googleapis.com", "perplexity.ai", "huggingface.co",
        "mistral.ai", "cohere.ai", "copilot.microsoft.com", "githubcopilot.com",
        "x.ai", "grok.com", "deepseek.com", "ollama.com", "ollama.ai",
    ),
    "Business Tools": (
        "office.com", "office365.com", "officeapps.live.com", "sharepoint.com",
        "outlook.com", "microsoftonline.com", "atlassian.net", "atlassian.com",
        "salesforce.com", "workday.com", "zoho.com", "notion.so", "asana.com",
        "monday.com", "hubspot.com", "docusign.net", "adobe.com", "adobelogin.com",
    ),
    "Instant Messaging": (
        "whatsapp.com", "whatsapp.net", "telegram.org", "t.me", "telegram-cdn.org",
        "signal.org", "messenger.com", "discord.com", "discordapp.net", "discord.gg",
        "slack.com", "slack-edge.com", "imessage.apple.com",
    ),
    "Web Browsing": (
        "google.com", "bing.com", "duckduckgo.com", "yahoo.com", "wikipedia.org",
        "wikimedia.org", "reddit.com", "redd.it", "medium.com", "stackoverflow.com",
        "stackexchange.com", "bbc.co.uk", "cnn.com", "aljazeera.net", "youm7.com",
    ),
    "Conferencing": (
        "zoom.us", "zoomgov.com", "teams.microsoft.com", "teams.live.com",
        "skype.com", "webex.com", "gotomeeting.com", "bluejeans.com",
        "meet.google.com", "whereby.com",
    ),
    "Network Management": (
        "opnsense.org", "pfsense.org", "ntp.org", "pool.ntp.org", "tailscale.com",
        "tailscale.io", "ui.com", "ubnt.com", "unifi.ui.com", "asus.com",
        "asuscomm.com", "ddns.net", "no-ip.com", "duckdns.org", "grafana.com",
        "elastic.co", "sunnyvalley.io", "zenarmor.com",
    ),
    "Cloud Services": (
        "icloud.com", "icloud-content.com", "dropbox.com", "dropboxusercontent.com",
        "onedrive.com", "live.com", "drive.google.com", "googleapis.com",
        "amazonaws.com", "s3.amazonaws.com", "backblazeb2.com", "b2-api.backblazeb2.com",
        "digitaloceanspaces.com", "wasabisys.com", "mega.nz", "pcloud.com",
    ),
    "Social Networks": (
        "facebook.com", "fbcdn.net", "instagram.com", "cdninstagram.com",
        "twitter.com", "x.com", "twimg.com", "snapchat.com", "sc-cdn.net",
        "linkedin.com", "licdn.com", "pinterest.com", "threads.net",
    ),
    "Gaming": (
        "steampowered.com", "steamcontent.com", "steamstatic.com", "playstation.net",
        "playstation.com", "xboxlive.com", "xbox.com", "epicgames.com",
        "easebar.com", "riotgames.com", "nintendo.net", "roblox.com", "battle.net",
    ),
    "Smart Home and IoT": (
        "amazonalexa.com", "alexa.amazon.com", "avs-alexa-na.amazon.com",
        "tuyaus.com", "tuyaeu.com", "tuya.com", "sonoff.tech", "ewelink.cc",
        "home-assistant.io", "nabucasa.com", "lgtvsdp.com", "lgeapi.com",
        "samsungcloudsolution.com", "samsungiotcloud.com", "shelly.cloud",
    ),
    "Advertising and Tracking": (
        "doubleclick.net", "googlesyndication.com", "googleadservices.com",
        "google-analytics.com", "analytics.google.com", "scorecardresearch.com",
        "criteo.com", "taboola.com", "outbrain.com", "adnxs.com", "sentry.io",
        "bugsnag.com", "crashlytics.com", "app-measurement.com",
    ),
}

# Everything below the top slice is rolled into one entry so the chart stays
# readable, and a category that matched nothing is never invented.
CATEGORY_TOP_N = 10
OTHERS_LABEL = "Others"
UNCATEGORISED_LABEL = "Uncategorised"


def value(node, name, default=""):
    item = node.find(name) if node is not None else None
    return item.text.strip() if item is not None and item.text else default


def number(node, name, default, minimum=0, maximum=1000000):
    try:
        return max(minimum, min(maximum, float(value(node, name, default))))
    except ValueError:
        return float(default)


def options():
    root = ET.parse(CONFIG_PATH).getroot()
    general = root.find("./OPNsense/WanQuota/general")
    try:
        groups = json.loads(value(general, "device_groups_json", "[]"))
        groups = groups if isinstance(groups, list) else []
    except json.JSONDecodeError:
        groups = []
    try:
        devices = json.loads(value(general, "device_policies_json", "[]"))
        devices = devices if isinstance(devices, list) else []
    except json.JSONDecodeError:
        devices = []
    known_groups = {
        "INFRASTRUCTURE_DEVICES": "Protected Infrastructure",
        "MY_DEVICES": "My Devices",
        "HOME_IOT_DEVICES": "Home and IoT",
        "UNCLASSIFIED_DEVICES": "Unclassified",
    }
    configured_names = {group.get("name") for group in groups}
    for alias in root.findall("./OPNsense/Firewall/Alias/aliases/alias"):
        alias_name = value(alias, "name")
        display = known_groups.get(alias_name)
        if display and display not in configured_names:
            members = value(alias, "content").replace("\n", ",").split(",")
            groups.append({"name": display, "members": [member.strip() for member in members if member.strip()], "source": alias_name})
    try:
        categories = json.loads(value(general, "domain_categories_json", "{}"))
        categories = categories if isinstance(categories, dict) else {}
    except json.JSONDecodeError:
        categories = {}
    return {
        "enabled": value(general, "intelligence_enabled", "1") == "1",
        "retention": int(number(general, "intelligence_retention_days", 730, 30, 3650)),
        "anomaly_sigma": number(general, "anomaly_sigma", 3, 1, 10),
        "enforcement": value(general, "enforcement_enabled", "0") == "1",
        "dry_run": value(general, "enforcement_dry_run", "1") == "1",
        # Per-device enforcement is separate from the gateway guardrails and both
        # default to the safe position: off, and dry-run when switched on.
        "device_enforcement": value(general, "device_enforcement_enabled", "0") == "1",
        "device_dry_run": value(general, "device_enforcement_dry_run", "1") == "1",
        "thresholds": [int(x) for x in value(general, "guardrail_thresholds", "50,75,90,100").split(",") if x.strip().isdigit()],
        "reserve_gb": number(general, "emergency_reserve_gb", 5, 0, 100000),
        "policy": value(general, "enforcement_policy", "observe"),
        "groups": groups,
        "devices": devices,
        "categories": {**BUILTIN_CATEGORIES, **{k: tuple(v) for k, v in categories.items() if isinstance(v, list)}},
        "webhook_enabled": value(general, "webhook_enabled", "0") == "1",
        "webhook_url": value(general, "webhook_url", ""),
        "webhook_format": value(general, "webhook_format", "generic"),
        "webhook_recipient": value(general, "webhook_recipient", ""),
        "scheduled_reports": value(general, "scheduled_reports_enabled", "0") == "1",
        "email_enabled": value(general, "email_enabled", "0") == "1",
        "email_to": value(general, "email_to", ""),
        "smtp_host": value(general, "smtp_host", ""),
        "smtp_port": int(number(general, "smtp_port", 587, 1, 65535)),
        "smtp_username": value(general, "smtp_username", ""),
        "smtp_password": value(general, "smtp_password", ""),
        "prometheus": value(general, "prometheus_enabled", "0") == "1",
        "accent": value(general, "dashboard_accent", "#3b82f6"),
    }


def database():
    os.makedirs(STATE_DIR, mode=0o750, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript("""
      CREATE TABLE IF NOT EXISTS provider_samples(ts INTEGER,provider TEXT,logical TEXT,used REAL,quota REAL,percent REAL,rx REAL,tx REAL,latency REAL,loss REAL,status TEXT);
      CREATE INDEX IF NOT EXISTS provider_samples_idx ON provider_samples(provider,ts);
      CREATE TABLE IF NOT EXISTS consumer_samples(ts INTEGER,device TEXT,name TEXT,total REAL,download REAL,upload REAL,mac TEXT);
      CREATE INDEX IF NOT EXISTS consumer_samples_idx ON consumer_samples(device,ts);
      CREATE TABLE IF NOT EXISTS cycle_archive(provider TEXT,start TEXT,end TEXT,used REAL,quota REAL,rx REAL,tx REAL,complete INTEGER,PRIMARY KEY(provider,start));
      CREATE TABLE IF NOT EXISTS anomalies(ts INTEGER,kind TEXT,subject TEXT,severity TEXT,observed REAL,baseline REAL,message TEXT);
      CREATE TABLE IF NOT EXISTS overrides(provider TEXT PRIMARY KEY,mode TEXT,expires INTEGER,reason TEXT);
      CREATE TABLE IF NOT EXISTS policy_state(provider TEXT PRIMARY KEY,action TEXT,updated INTEGER,detail TEXT);
      CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT);
    """)
    # Older installs predate the mac column. Adding it is the whole migration:
    # existing rows keep a NULL mac and continue to match by address.
    try:
        db.execute("ALTER TABLE consumer_samples ADD COLUMN mac TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("CREATE INDEX IF NOT EXISTS consumer_samples_mac ON consumer_samples(mac,ts)")
    except sqlite3.OperationalError:
        pass
    return db


def gateway_quality():
    try:
        raw = subprocess.check_output(["/usr/local/sbin/configctl", "interface", "gateways", "status"], text=True, timeout=15)
        rows = json.loads(raw)
    except (subprocess.SubprocessError, json.JSONDecodeError):
        return {}
    root = ET.parse(CONFIG_PATH).getroot()
    mapping = {}
    for item in root.findall("./OPNsense/Gateways/gateway_item"):
        mapping[value(item, "interface")] = value(item, "name")
    result = {}
    for logical, name in mapping.items():
        item = rows.get(name, {})
        def metric(key):
            try: return float(str(item.get(key, "0")).replace("ms", "").replace("%", ""))
            except ValueError: return 0.0
        result[logical] = {"gateway": name, "status": item.get("status", "unknown"), "latency": metric("delay"), "loss": metric("loss"), "stddev": metric("stddev")}
    return result


def suffix_category(domain, categories):
    for category, suffixes in categories.items():
        if any(domain == suffix or domain.endswith("." + suffix) for suffix in suffixes):
            return category
    return "Other"



def category_breakdown(domains, categories, top_n=CATEGORY_TOP_N):
    """Traffic share per app category, largest first, with a rolled-up remainder.

    Returns rows carrying both bytes and percent so a caller never has to divide,
    and so the percentages shown always sum against the same total. Domains that
    match no suffix are reported as Uncategorised rather than distributed into
    whatever looks closest: an honest unknown slice is the point, since attribution
    is already an estimate upstream.

    Everything past top_n becomes one Others row, which keeps a pie chart legible
    without hiding the tail — the row states how many categories it covers.
    """
    totals = {}
    for domain in domains:
        name = domain.get("domain") or ""
        amount = float(domain.get("total") or 0)
        if amount <= 0:
            continue
        category = suffix_category(name, categories)
        if category == "Other":
            category = UNCATEGORISED_LABEL
        totals[category] = totals.get(category, 0) + amount

    grand_total = sum(totals.values())
    ordered = sorted(totals.items(), key=lambda item: item[1], reverse=True)

    def row(label, amount, folded=0):
        entry = {
            "name": label,
            "total": amount,
            "percent": (amount / grand_total * 100) if grand_total else 0,
        }
        if folded:
            entry["categories_folded"] = folded
        return entry

    rows = [row(name, amount) for name, amount in ordered[:top_n]]
    tail = ordered[top_n:]
    if tail:
        rows.append(row(OTHERS_LABEL, sum(amount for _, amount in tail), folded=len(tail)))
    return {
        "total": grand_total,
        "categories": rows,
        "known_percent": (
            sum(r["percent"] for r in rows if r["name"] != UNCATEGORISED_LABEL)
            if grand_total else 0
        ),
        "top_n": top_n,
        "note": (
            "Shares are of DNS-attributed traffic, not of the whole quota. "
            "Uncategorised means the domain matched no known category; unattributed "
            "traffic never reaches this breakdown at all."
        ),
    }



# Individual applications, a finer grain than the category breakdown: "GitHub"
# rather than "Online Utility". Same suffix matching, same honesty about unknowns.
APP_DEFINITIONS = {
    "GitHub": ("github.com", "githubusercontent.com", "githubassets.com", "ghcr.io", "github.io"),
    "ChatGPT": ("chatgpt.com", "openai.com", "oaistatic.com", "oaiusercontent.com"),
    "Claude": ("claude.ai", "anthropic.com"),
    "Apple iTunes": ("mzstatic.com", "itunes.apple.com", "aaplimg.com", "swcdn.apple.com",
                     "updates.cdn-apple.com", "osxapps.itunes.apple.com"),
    "Apple": ("apple.com", "apple-dns.net", "icloud.com", "icloud-content.com",
              "push.apple.com", "aapl.com"),
    "Google Services": ("google.com", "googleapis.com", "gstatic.com", "googleusercontent.com",
                        "gvt1.com", "gvt2.com", "google-analytics.com", "doubleclick.net",
                        "googlesyndication.com", "goog"),
    "YouTube": ("youtube.com", "googlevideo.com", "ytimg.com", "youtu.be"),
    "WhatsApp": ("whatsapp.com", "whatsapp.net"),
    "Netflix": ("netflix.com", "nflxvideo.net", "nflximg.net", "nflxext.com"),
    "Microsoft": ("microsoft.com", "windowsupdate.com", "office.com", "office365.com",
                  "microsoftonline.com", "live.com", "msftconnecttest.com", "azureedge.net"),
    "Telegram": ("telegram.org", "t.me", "telegram-cdn.org", "telegra.ph"),
    "Spotify": ("spotify.com", "scdn.co", "spotifycdn.com"),
    "Steam": ("steampowered.com", "steamcontent.com", "steamstatic.com"),
    "Tailscale": ("tailscale.com", "tailscale.io"),
    "Home Assistant": ("home-assistant.io", "nabucasa.com"),
    "Plex": ("plex.tv", "plex.direct"),
    "Storj": ("storjshare.io", "storj.io"),
    "Cloudflare": ("cloudflare.com", "cloudflare-dns.com", "cloudflareinsights.com"),
    "Docker": ("docker.io", "docker.com", "dockerhub.com"),
    "LG": ("lgtvsdp.com", "lgeapi.com", "lgtvcommon.com"),
    "Samsung": ("samsungcloudsolution.com", "samsungiotcloud.com", "samsungqbe.com"),
    "Amazon Alexa": ("amazonalexa.com", "alexa.amazon.com", "avs-alexa-na.amazon.com"),
    "Tuya": ("tuya.com", "tuyaus.com", "tuyaeu.com"),
    "Zoom": ("zoom.us", "zoomgov.com"),
    "Slack": ("slack.com", "slack-edge.com"),
    "Discord": ("discord.com", "discordapp.net", "discord.gg"),
}


def app_breakdown(domains, transports=None, definitions=None, top_n=CATEGORY_TOP_N):
    """Traffic share per application, with unnamed traffic labelled by transport.

    Two sources are combined deliberately. Domains that match an application are
    reported under its name. Bytes with no known domain cannot be named that way at
    all, so they arrive already labelled by how they were carried — "Quic UDP
    Connection", "Secure Web Browsing" — which keeps the largest slice meaningful
    instead of collapsing every blind spot into one anonymous remainder.

    A domain that matches no application is reported under its own registrable
    name rather than being folded away, so the tail stays inspectable.
    """
    definitions = definitions or APP_DEFINITIONS
    totals = {}
    for domain in domains or []:
        name = (domain.get("domain") or "").strip().lower().rstrip(".")
        amount = float(domain.get("total") or 0)
        if not name or amount <= 0:
            continue
        app = None
        for candidate, suffixes in definitions.items():
            if any(name == suffix or name.endswith("." + suffix) for suffix in suffixes):
                app = candidate
                break
        if app is None:
            parts = name.split(".")
            app = ".".join(parts[-2:]) if len(parts) >= 2 else name
        totals[app] = totals.get(app, 0) + amount

    for entry in transports or []:
        label = entry.get("name")
        amount = float(entry.get("total") or 0)
        if label and amount > 0:
            totals[label] = totals.get(label, 0) + amount

    grand_total = sum(totals.values())
    ordered = sorted(totals.items(), key=lambda item: item[1], reverse=True)

    def row(label, amount, folded=0):
        entry = {"name": label, "total": amount,
                 "percent": (amount / grand_total * 100) if grand_total else 0}
        if folded:
            entry["apps_folded"] = folded
        return entry

    rows = [row(name, amount) for name, amount in ordered[:top_n]]
    tail = ordered[top_n:]
    if tail:
        rows.append(row(OTHERS_LABEL, sum(a for _, a in tail), folded=len(tail)))
    return {
        "total": grand_total,
        "apps": rows,
        "top_n": top_n,
        "note": (
            "Applications are matched from observed DNS answers. Traffic with no known "
            "domain is named by how it was carried instead, so entries like 'Quic UDP "
            "Connection' or 'Secure Web Browsing' are unnamed traffic grouped by "
            "transport rather than a single application."
        ),
    }

def category_detail(name, domains, device_domains, categories, top_n=None):
    """Everything behind one category: its domains, and the devices that used them.

    Kept separate from category_breakdown so a caller can ask about one slice
    without receiving every slice's contents, and so the rollup stays a summary.

    `Others` is not a real category — it is the fold of everything past the top
    slice — so asking for it returns the categories it covers rather than pretending
    to be one.
    """
    label = (name or "").strip()
    matching = []
    for domain in domains:
        category = domain.get("category")
        if category is None:
            category = suffix_category(domain.get("domain") or "", categories)
            if category == "Other":
                category = UNCATEGORISED_LABEL
        if category.lower() == label.lower():
            matching.append(domain)
    matching.sort(key=lambda item: item.get("total") or 0, reverse=True)

    names = {item.get("domain") for item in matching}
    devices = {}
    for row in device_domains or []:
        if row.get("domain") in names:
            key = row.get("device")
            entry = devices.setdefault(key, {
                "device": key, "name": row.get("name", key), "total": 0, "domains": 0,
            })
            entry["total"] += row.get("total") or 0
            entry["domains"] += 1
    device_rows = sorted(devices.values(), key=lambda item: item["total"], reverse=True)

    total = sum(item.get("total") or 0 for item in matching)
    return {
        "category": label,
        "total": total,
        "domain_count": len(matching),
        "domains": [
            {"domain": item.get("domain"), "total": item.get("total") or 0,
             "first_seen": item.get("first_seen"), "last_seen": item.get("last_seen")}
            for item in (matching[:top_n] if top_n else matching)
        ],
        "devices": device_rows[:top_n] if top_n else device_rows,
        "found": bool(matching),
        "empty_reason": None if matching else (
            f"No attributed traffic in {label!r} for this period. The name may be "
            f"misspelled, or nothing matched that category. 'Others' is a rollup of the "
            f"categories below the top slice rather than a category itself."
        ),
        "devices_total": sum(row["total"] for row in device_rows),
        "device_note": (
            "Device totals count only this category's domains, so they are not each "
            "device's overall usage. They can also sum to less than the category total: "
            "the device/domain matrix is capped, so a domain counted in the category may "
            "have no matrix row. Compare devices_total with total to see the shortfall."
        ),
    }

def group_for(address, groups):
    for group in groups:
        for member in group.get("members", []):
            try:
                if ipaddress.ip_address(address) in ipaddress.ip_network(member, strict=False):
                    return group.get("name", "Unnamed")
            except ValueError:
                if address == member:
                    return group.get("name", "Unnamed")
    return "Ungrouped"


def delta_baseline(db, table, subject_column, subject, metric, before, limit=97):
    allowed = {("provider_samples", "provider", "used"), ("consumer_samples", "device", "total"), ("consumer_samples", "device", "upload")}
    if (table, subject_column, metric) not in allowed:
        raise ValueError("Unsupported baseline metric")
    rows = db.execute(f"SELECT {metric} value FROM {table} WHERE {subject_column}=? AND ts<? ORDER BY ts DESC LIMIT ?", (subject, before, limit)).fetchall()
    values = [float(row["value"]) for row in reversed(rows)]
    deltas = [max(0, current - previous) for previous, current in zip(values, values[1:])]
    return (statistics.mean(deltas), statistics.pstdev(deltas)) if len(deltas) >= 6 else (None, None)


def record_anomaly(db, ts, kind, subject, observed, mean, deviation, sigma):
    if mean is None or deviation is None or deviation <= 0 or observed <= mean + sigma * deviation:
        return None
    severity = "critical" if observed > mean + (sigma + 2) * deviation else "warning"
    message = f"{subject} {kind} is {observed:.2f}, normally {mean:.2f}"
    db.execute("INSERT INTO anomalies VALUES(?,?,?,?,?,?,?)", (ts, kind, subject, severity, observed, mean, message))
    return {"kind": kind, "subject": subject, "severity": severity, "observed": observed, "baseline": mean, "message": message}


def forecasts(item):
    end = dt.date.fromisoformat(item["end"])
    start = dt.date.fromisoformat(item["start"])
    # Same measured-days basis as report.provider_summary: dividing by elapsed days
    # would understate the rate whenever vnStat has no history for part of the cycle.
    rate = item.get("daily_average")
    if rate is None:
        elapsed = max(1, (dt.date.today() - start).days + 1)
        rate = item["used"] / elapsed
    exhaustion = start + dt.timedelta(days=math.ceil(item["quota"] / rate)) if rate > 0 else None
    previous = None
    with database() as db:
        row = db.execute("SELECT used FROM cycle_archive WHERE provider=? AND start<? ORDER BY start DESC LIMIT 1", (item["name"], item["start"])).fetchone()
        previous = row["used"] if row else None
    return {
        "daily_average": rate,
        "basis": item.get("projection_basis", "measured"),
        "basis_note": item.get("projection_note"),
        "exhaustion_date": exhaustion.isoformat() if exhaustion and exhaustion < end else None,
        "risk": "exceeded" if item["percent"] >= 100 else "high" if item["projected"] > item["quota"] else "watch" if item["percent"] >= item["warning_percent"] else "on_track",
        "previous_cycle": previous,
        "change_percent": ((item["used"] - previous) / previous * 100) if previous else None,
    }


def policy_for(host, policies):
    """Find a per-device policy by address, MAC, or DHCP hostname.

    Matching on address alone silently stopped applying whenever DHCP moved a
    device, and a device that rotates its MAC per network holds several leases at
    once. Accepting any of the three means a policy set once keeps applying.
    """
    for key in (host.get("ip"), (host.get("mac") or "").lower(), (host.get("hostname") or "").lower()):
        if key and key in policies:
            return policies[key]
    return {}


def policy_index(devices):
    """Index configured device policies by every identifier they may carry."""
    index = {}
    for item in devices:
        for field in ("address", "mac", "hostname"):
            value = item.get(field)
            if value:
                index[str(value).lower() if field != "address" else str(value)] = item
    return index


def policy_decision(item, cfg, override=None):
    percent = item["percent"]
    reserve_hit = item["remaining"] <= cfg["reserve_gb"] * 1e9
    thresholds = sorted(set(cfg.get("thresholds", [])))
    thresholds = thresholds[:4] if len(thresholds) >= 4 else [50, 75, 90, 100]
    _, deprioritize_at, failover_at, cutoff_at = thresholds
    action = "observe"
    if percent >= cutoff_at or reserve_hit: action = "cutoff"
    elif percent >= failover_at: action = "failover"
    elif percent >= deprioritize_at: action = "deprioritize"
    if override and override["expires"] > int(dt.datetime.now().timestamp()): action = override["mode"]
    permitted = cfg["enforcement"] and not cfg["dry_run"] and cfg["policy"] != "observe"
    levels = ["observe", "deprioritize", "failover", "cutoff"]
    capped = levels[min(levels.index(action), levels.index(cfg["policy"]))] if cfg["policy"] in levels else "observe"
    return {"recommended": action, "applied": capped if permitted else "none", "dry_run": not permitted, "reserve_hit": reserve_hit, "thresholds": thresholds}


def send_webhook(cfg, event, payload):
    if not cfg["webhook_enabled"] or not cfg["webhook_url"].startswith("https://"):
        return "disabled"
    parsed = urllib.parse.urlparse(cfg["webhook_url"])
    try:
        addresses = {ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)}
    except (socket.gaierror, ValueError) as error:
        return f"failed: invalid webhook destination: {error}"
    if any(address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified or address.is_reserved for address in addresses):
        return "failed: unsafe webhook destination"
    message = f"WAN Quota {event}: " + json.dumps(payload, separators=(",", ":"))
    if cfg.get("webhook_format") == "discord": document = {"content": message[:1900]}
    elif cfg.get("webhook_format") == "slack": document = {"text": message}
    elif cfg.get("webhook_format") == "telegram": document = {"chat_id": cfg.get("webhook_recipient", ""), "text": message[:4000]}
    else: document = {"event": event, "payload": payload}
    body = json.dumps(document).encode()
    request = urllib.request.Request(cfg["webhook_url"], body, {"Content-Type": "application/json", "User-Agent": "os-wanquota/0.13"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return str(response.status)
    except Exception as error:
        return f"failed: {error}"


def fresh_events(events, repeat_hours=24):
    now = int(dt.datetime.now().timestamp()); fresh = []
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        for event in events:
            fingerprint = hashlib.sha256(f"{event.get('kind')}|{event.get('subject')}|{event.get('severity')}".encode()).hexdigest()
            key = "event:" + fingerprint
            row = db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
            if row and now - int(row["value"]) < repeat_hours * 3600: continue
            fresh.append(event); db.execute("INSERT OR REPLACE INTO metadata VALUES(?,?)", (key, str(now)))
        db.commit()
    return fresh


def send_email(cfg, subject, payload):
    if not cfg["email_enabled"] or not cfg["email_to"] or not cfg["smtp_host"]: return "disabled"
    message = EmailMessage(); message["Subject"] = subject; message["From"] = cfg["smtp_username"] or "opnsense@localhost"; message["To"] = cfg["email_to"]
    message.set_content(json.dumps(payload, indent=2, default=str))
    providers = payload.get("providers", []) if isinstance(payload, dict) else []
    if providers:
        output = io.StringIO(); writer = csv.writer(output); writer.writerow(["provider","cycle_start","cycle_end","used_bytes","quota_bytes","remaining_bytes","percent"])
        for item in providers: writer.writerow([item.get("name"),item.get("start"),item.get("end"),item.get("used"),item.get("quota"),item.get("remaining"),item.get("percent")])
        message.add_attachment(output.getvalue().encode(), maintype="text", subtype="csv", filename="wan-quota-summary.csv")
    try:
        with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=15) as smtp:
            smtp.starttls()
            if cfg["smtp_username"]: smtp.login(cfg["smtp_username"], cfg["smtp_password"])
            smtp.send_message(message)
        return "sent"
    except Exception as error:
        return f"failed: {error}"


def snapshot(notify=True):
    cfg = options()
    if not cfg["enabled"]: return {"status": "disabled"}
    enabled, providers = report.configuration()
    summary = report.summary(enabled, providers)
    consumer = consumers.report("month")
    device_policies = policy_index(cfg["devices"])
    consumer["hosts"] = [host for host in consumer.get("hosts", []) if not policy_for(host, device_policies).get("exclude")]
    quality = gateway_quality()
    ts = int(dt.datetime.now().timestamp())
    events = []
    with database() as db:
        cutoff = ts - cfg["retention"] * 86400
        db.execute("DELETE FROM provider_samples WHERE ts<?", (cutoff,)); db.execute("DELETE FROM consumer_samples WHERE ts<?", (cutoff,)); db.execute("DELETE FROM anomalies WHERE ts<?", (cutoff,))
        overrides = {row["provider"]: row for row in db.execute("SELECT * FROM overrides WHERE expires>?", (ts,))}
        for item in summary.get("providers", []):
            q = quality.get(item["logical_interface"], {})
            previous = db.execute("SELECT used FROM provider_samples WHERE provider=? ORDER BY ts DESC LIMIT 1", (item["name"],)).fetchone()
            delta = max(0, item["used"] - (previous["used"] if previous else item["used"]))
            mean, deviation = delta_baseline(db, "provider_samples", "provider", item["name"], "used", ts)
            event = record_anomaly(db, ts, "provider usage interval", item["name"], delta, mean, deviation, cfg["anomaly_sigma"])
            if event: events.append(event)
            if q.get("status") not in {"none", "online", "unknown"}:
                events.append({"kind":"provider quality","subject":item["name"],"severity":"critical" if q.get("status") in {"down","force_down"} else "warning","observed":q.get("status"),"baseline":"online","message":f"{item['name']} gateway reports {q.get('status')}"})
            db.execute("INSERT INTO provider_samples VALUES(?,?,?,?,?,?,?,?,?,?,?)", (ts,item["name"],item["logical_interface"],item["used"],item["quota"],item["percent"],item["rx"],item["tx"],q.get("latency",0),q.get("loss",0),q.get("status","unknown")))
            if item["complete"]:
                db.execute("INSERT OR REPLACE INTO cycle_archive VALUES(?,?,?,?,?,?,?,?)", (item["name"],item["start"],item["end"],item["used"],item["quota"],item["rx"],item["tx"],1))
            decision = policy_decision(item, cfg, overrides.get(item["name"]))
            previous_policy = db.execute("SELECT action FROM policy_state WHERE provider=?", (item["name"],)).fetchone()
            previous_action = previous_policy["action"] if previous_policy else "none"
            if decision["applied"] == "none" and previous_action not in {"none", "observe"}:
                try:
                    subprocess.run(["/usr/local/bin/php", "/usr/local/opnsense/scripts/OPNsense/WanQuota/enforce.php", item["logical_interface"], "observe"], check=True, capture_output=True, text=True, timeout=60)
                    previous_action = "none"
                except subprocess.SubprocessError as error:
                    decision["error"] = f"restore failed: {error}"
            if decision["applied"] != "none" and decision["applied"] != previous_action:
                try:
                    subprocess.run(["/usr/local/bin/php", "/usr/local/opnsense/scripts/OPNsense/WanQuota/enforce.php", item["logical_interface"], decision["applied"]], check=True, capture_output=True, text=True, timeout=60)
                except subprocess.SubprocessError as error:
                    decision["error"] = str(error)
                    decision["applied"] = previous_action
            db.execute("INSERT OR REPLACE INTO policy_state VALUES(?,?,?,?)", (item["name"], decision["applied"], ts, json.dumps(decision)))
        for host in consumer.get("hosts", []):
            # Prefer the MAC so a device keeps its baseline across a DHCP change;
            # fall back to the address for rows written before the mac column.
            mac = (host.get("mac") or "").lower()
            previous = None
            if mac:
                previous = db.execute("SELECT total,upload FROM consumer_samples WHERE mac=? ORDER BY ts DESC LIMIT 1", (mac,)).fetchone()
            if previous is None:
                previous = db.execute("SELECT total,upload FROM consumer_samples WHERE device=? ORDER BY ts DESC LIMIT 1", (host["ip"],)).fetchone()
            has_history = db.execute("SELECT 1 FROM consumer_samples LIMIT 1").fetchone() is not None
            delta = max(0, host["total"] - (previous["total"] if previous else host["total"]))
            mean, deviation = delta_baseline(db, "consumer_samples", "device", host["ip"], "total", ts)
            event = record_anomaly(db, ts, "device traffic interval", host["name"], delta, mean, deviation, cfg["anomaly_sigma"])
            if event: events.append(event)
            upload_delta = max(0, host["upload"] - (previous["upload"] if previous else host["upload"]))
            upload_mean, upload_deviation = delta_baseline(db, "consumer_samples", "device", host["ip"], "upload", ts)
            event = record_anomaly(db, ts, "upload interval", host["name"], upload_delta, upload_mean, upload_deviation, cfg["anomaly_sigma"])
            if event: events.append(event)
            if previous is None and has_history:
                events.append({"kind":"new device","subject":host["name"],"severity":"warning","observed":host["ip"],"baseline":"known inventory","message":f"New traffic-producing device {host['name']} ({host['ip']})"})
            if 1 <= dt.datetime.now().hour < 6 and delta > 500_000_000:
                events.append({"kind":"quiet-hours traffic","subject":host["name"],"severity":"warning","observed":delta,"baseline":500_000_000,"message":f"{host['name']} transferred {delta/1e9:.2f} GB during quiet hours"})
            device_budget = float(policy_for(host, device_policies).get("budget_gb", 0) or 0) * 1e9
            if device_budget and host["total"] >= device_budget:
                events.append({"kind":"device budget","subject":host["name"],"severity":"critical","observed":host["total"],"baseline":device_budget,"message":f"{host['name']} exceeded its {device_budget/1e9:.2f} GB monthly budget"})
            db.execute("INSERT INTO consumer_samples(ts,device,name,total,download,upload,mac) VALUES(?,?,?,?,?,?,?)", (ts,host["ip"],host["name"],host["total"],host["download"],host["upload"],(host.get("mac") or "") or None))
        group_totals = {}
        for host in consumer.get("hosts", []):
            group_name = group_for(host["ip"], cfg["groups"]); group_totals[group_name] = group_totals.get(group_name, 0) + host["total"]
        for group in cfg["groups"]:
            budget = float(group.get("budget_gb", 0) or 0) * 1e9
            used = group_totals.get(group.get("name"), 0)
            if budget and used >= budget:
                events.append({"kind":"group budget","subject":group.get("name","Unnamed"),"severity":"critical","observed":used,"baseline":budget,"message":f"{group.get('name','Unnamed')} used {used/1e9:.2f} GB of its {budget/1e9:.2f} GB monthly budget"})
        db.commit()
    notifications = fresh_events(events) if events and notify else []
    for event in notifications:
        subprocess.run(["/usr/bin/logger", "-t", "wanquota", event["message"]], check=False)
    if notifications and cfg["webhook_enabled"]: send_webhook(cfg, "anomalies", notifications)
    if notifications and cfg["email_enabled"]: send_email(cfg, "OPNsense WAN quota alerts", notifications)
    if cfg["scheduled_reports"] and notify:
        today = dt.date.today().isoformat()
        with database() as db:
            sent = db.execute("SELECT value FROM metadata WHERE key='daily_report' ").fetchone()
            if dt.datetime.now().hour >= 8 and (not sent or sent["value"] != today):
                webhook_status = send_webhook(cfg, "daily_report", {"generated_at": summary.get("generated_at"), "providers": summary.get("providers", [])}) if cfg["webhook_enabled"] else "disabled"
                email_status = send_email(cfg, "OPNsense daily WAN quota report", summary) if cfg["email_enabled"] else "disabled"
                if (cfg["webhook_enabled"] and not webhook_status.startswith("failed")) or (cfg["email_enabled"] and not email_status.startswith("failed")):
                    db.execute("INSERT OR REPLACE INTO metadata VALUES('daily_report',?)", (today,)); db.commit()
    return {"status": "ok", "timestamp": ts, "events": events, "notifications": len(notifications), "providers": len(summary.get("providers", [])), "hosts": len(consumer.get("hosts", []))}


def dashboard(period="thirty"):
    cfg = options(); enabled, providers = report.configuration(); summary = report.summary(enabled, providers); consumer = consumers.report(period); quality = gateway_quality()
    device_policies = policy_index(cfg["devices"])
    for host in consumer.get("hosts", []):
        policy = policy_for(host, device_policies); host["excluded"] = bool(policy.get("exclude")); host["budget"] = float(policy.get("budget_gb",0) or 0)*1e9 or None
    with database() as db:
        archives = [dict(row) for row in db.execute("SELECT * FROM cycle_archive ORDER BY start DESC LIMIT 48")]
        anomalies = [dict(row) for row in db.execute("SELECT * FROM anomalies ORDER BY ts DESC LIMIT 50")]
        overrides = {row["provider"]: dict(row) for row in db.execute("SELECT * FROM overrides WHERE expires>?", (int(dt.datetime.now().timestamp()),))}
        prior = {row["provider"]: dict(row) for row in db.execute("SELECT p.* FROM provider_samples p JOIN (SELECT provider,max(ts) ts FROM provider_samples WHERE ts<=? GROUP BY provider) x ON p.provider=x.provider AND p.ts=x.ts", (int(dt.datetime.now().timestamp())-86400,))}
        pattern_rows = [dict(row) for row in db.execute("SELECT provider,ts,used FROM provider_samples WHERE ts>? ORDER BY provider,ts", (int(dt.datetime.now().timestamp())-90*86400,))]
    pattern_days = {}
    last = {}
    for row in pattern_rows:
        previous = last.get(row["provider"]); last[row["provider"]] = row
        if not previous: continue
        delta = max(0, row["used"] - previous["used"]); bucket = "weekend" if dt.datetime.fromtimestamp(row["ts"]).weekday() >= 5 else "weekday"
        date = dt.datetime.fromtimestamp(row["ts"]).date().isoformat(); pattern_days[(row["provider"], bucket, date)] = pattern_days.get((row["provider"], bucket, date), 0) + delta
    patterns = {}
    for (provider,bucket,_),total in pattern_days.items(): patterns.setdefault(provider,{"weekday":[],"weekend":[]})[bucket].append(total)
    pattern_summary = [{"provider":name,"weekday_average":statistics.mean(values["weekday"]) if values["weekday"] else 0,"weekend_average":statistics.mean(values["weekend"]) if values["weekend"] else 0} for name,values in patterns.items()]
    groups = {}
    for host in consumer.get("hosts", []):
        if host.get("excluded"): continue
        name = group_for(host["ip"], cfg["groups"]); item = groups.setdefault(name, {"name":name,"total":0,"download":0,"upload":0,"devices":0,"budget":None})
        item["total"] += host["total"]; item["download"] += host["download"]; item["upload"] += host["upload"]; item["devices"] += 1
    for spec in cfg["groups"]:
        if spec.get("name") in groups: groups[spec["name"]]["budget"] = float(spec.get("budget_gb",0))*1e9 or None
    categories = {}
    domain_seen = {}
    try:
        with consumers.database() as domain_db:
            domain_seen = {row[0]: {"first_seen": row[1], "last_seen": row[2]} for row in domain_db.execute("SELECT domain,min(first_seen),max(last_seen) FROM ip_domains GROUP BY domain")}
    except sqlite3.Error:
        pass
    for domain in consumer.get("domains", []):
        category = suffix_category(domain["domain"], cfg["categories"])
        if category == "Other":
            category = UNCATEGORISED_LABEL
        categories[category] = categories.get(category, 0) + domain["total"]
        domain["category"] = category
        domain.update(domain_seen.get(domain["domain"], {}))
    for item in summary.get("providers", []):
        item["forecast"] = forecasts(item); item["quality"] = quality.get(item["logical_interface"], {}); item["policy"] = policy_decision(item, cfg, overrides.get(item["name"]))
        old = prior.get(item["name"]); item["movement"] = {"period":"24h","used_delta":item["used"]-old["used"],"percent_delta":item["percent"]-old["percent"]} if old else None
    accent = cfg["accent"] if len(cfg["accent"]) == 7 and cfg["accent"].startswith("#") else "#3b82f6"
    # summary is per billing cycle and each provider's cycle can start on a
    # different day; consumers is one fixed window. Comparing their totals without
    # knowing that reads as missing traffic, so state the windows in the payload.
    windows = {
        "consumers_period": period,
        "consumers_start": consumer.get("start"),
        "consumers_end": consumer.get("end"),
        "summary_cycles": [
            {"provider": item["name"], "start": item["start"], "end": item["end"]}
            for item in summary.get("providers", [])
        ],
        "note": (
            "summary totals cover each provider's own billing cycle; consumers totals cover "
            "the requested period. The windows differ, so the two sets of totals are not "
            "expected to reconcile."
        ),
    }
    return {"status":"ok","generated_at":dt.datetime.now().astimezone().isoformat(timespec="seconds"),"windows":windows,"summary":summary,"consumers":consumer,"groups":sorted(groups.values(),key=lambda x:x["total"],reverse=True),"categories":[{"name":k,"total":v} for k,v in sorted(categories.items(),key=lambda x:x[1],reverse=True)],"category_breakdown":category_breakdown((consumer.get("domains") or []),cfg["categories"]),"app_breakdown":app_breakdown((consumer.get("domains") or []),consumer.get("transports")),"archives":archives,"anomalies":anomalies,"patterns":pattern_summary,"settings":{"enforcement":cfg["enforcement"],"dry_run":cfg["dry_run"],"policy":cfg["policy"],"prometheus":cfg["prometheus"],"accent":accent}}


def prometheus():
    data = dashboard("today"); lines = ["# HELP wanquota_used_bytes WAN billing-cycle usage", "# TYPE wanquota_used_bytes gauge"]
    for item in data["summary"].get("providers", []):
        label = item["name"].replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        lines += [f'wanquota_used_bytes{{provider="{label}"}} {item["used"]}',f'wanquota_quota_bytes{{provider="{label}"}} {item["quota"]}',f'wanquota_percent{{provider="{label}"}} {item["percent"]}',f'wanquota_gateway_latency_ms{{provider="{label}"}} {item["quality"].get("latency",0)}',f'wanquota_gateway_loss_percent{{provider="{label}"}} {item["quality"].get("loss",0)}']
    return "\n".join(lines) + "\n"


def set_override(provider, mode, hours, reason="manual"):
    expires = int(dt.datetime.now().timestamp()) + max(1, min(168, int(hours))) * 3600
    with database() as db: db.execute("INSERT OR REPLACE INTO overrides VALUES(?,?,?,?)", (provider, mode, expires, reason)); db.commit()
    return {"status":"ok","provider":provider,"mode":mode,"expires":expires}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "dashboard"
    if mode == "snapshot":
        os.makedirs(STATE_DIR, mode=0o750, exist_ok=True)
        with open(os.path.join(STATE_DIR, "snapshot.lock"), "w", encoding="utf-8") as lock:
            try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: print('{"status":"busy"}'); return
            result = snapshot()
    elif mode == "prometheus": print(prometheus(), end=""); return
    elif mode == "override" and len(sys.argv) >= 5: result = set_override(sys.argv[2], sys.argv[3], sys.argv[4], " ".join(sys.argv[5:]) or "manual")
    else: result = dashboard(sys.argv[2] if len(sys.argv) > 2 else "thirty")
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__": main()
