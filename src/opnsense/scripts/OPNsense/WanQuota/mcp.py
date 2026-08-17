#!/usr/local/bin/python3
"""Model Context Protocol server exposing WAN quota data and controls to AI agents.

Most tools read. A named few write: settings, per-service limits and per-device
limits can be changed through this server, because the owner asked for full control
rather than a reporting window. Each tool declares which it is, so a client can
prompt before a change and not before a report, and the set of writers is asserted
in the tests rather than left to inspection.

What stays off the surface, stated precisely because the imprecise version is
flattering and wrong: there is no tool that *performs* a guardrail override, so an
agent cannot move a household onto a different WAN in one call. It can, however, set
`enforcement_enabled` and `enforcement_dry_run` through wanquota_set_settings, and
the guardrail engine then acts on its own schedule. Full control was asked for and
that is what full control means; the honest boundary is "no override verb", not
"cannot change routing". Credentials can be set but never read back.

Writes go through configure.php, which validates them with the same model the web
interface uses, so a value the interface would reject is rejected here too and
nothing is half-applied.

Two transports share one dispatcher:
  mcp.py --stdio                     newline-delimited JSON-RPC on stdin/stdout
  mcp.py --once <base64> [client]    single base64-encoded request, for configd

The base64 wrapper on --once exists because configd passes parameters as
space-separated tokens; encoding sidesteps quoting entirely.

When a client address is supplied it must fall inside the LAN network defined in
config.xml, or be loopback. Anything else is refused before the request is even
parsed. This fails closed: if the LAN cannot be determined, nothing is served.
The stdio transport carries no client address and is not filtered, because
reaching it already requires shell access to the firewall.

No third-party modules: JSON-RPC 2.0 is small enough to implement directly,
and the plugin ships with a stdlib-only Python surface.
"""

import base64
import binascii
import ipaddress
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

import consumers
import explain as explain_module
import shaper
import health
import sessions
import intelligence
import report

PROTOCOL_VERSION = "2024-11-05"
# Revisions this server can actually speak. Anything else is answered with
# PROTOCOL_VERSION so the client can decide whether to proceed; claiming a
# version we do not implement would be a false statement of capability.
SUPPORTED_PROTOCOL_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18")
SERVER_NAME = "wanquota"
SERVER_VERSION = "0.13"

PERIODS = ("today", "week", "thirty", "month")

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Outside the JSON-RPC reserved range, so a client can tell "you are not allowed
# to reach this from here" apart from a malformed call.
NOT_PERMITTED = -32000


class UnknownTool(Exception):
    """Requested tool does not exist."""


class InvalidParams(Exception):
    """Tool arguments failed validation."""


def lan_networks(config_path=None):
    """LAN networks permitted to reach the MCP endpoint.

    Loopback is always included. Returns an empty list when the LAN cannot be
    determined, which the caller treats as deny-all rather than allow-all.
    """
    networks = [ipaddress.ip_network("127.0.0.0/8"), ipaddress.ip_network("::1/128")]
    try:
        root = ET.parse(config_path or report.CONFIG_PATH).getroot()
    except (OSError, ET.ParseError):
        return []
    # Both families: a LAN client reaching the GUI over IPv6 is still on the LAN,
    # and refusing it would be a confusing lockout. Addresses that are not literal
    # (dhcp, track6, an empty element) simply contribute no network.
    found = False
    for address_key, prefix_key in (("ipaddr", "subnet"), ("ipaddrv6", "subnetv6")):
        address = consumers.node_text(root, f"./interfaces/lan/{address_key}")
        prefix = consumers.node_text(root, f"./interfaces/lan/{prefix_key}")
        if not address or not prefix:
            continue
        try:
            networks.append(ipaddress.ip_network(f"{address}/{int(prefix)}", strict=False))
            found = True
        except (ValueError, TypeError):
            continue
    if not found:
        return []
    return networks


def is_permitted(client, config_path=None):
    """True when the client address sits on the LAN (or is loopback)."""
    if client is None or client == "":
        # stdio: reaching it already required shell access to the firewall.
        return True
    try:
        address = ipaddress.ip_address(client.strip())
    except ValueError:
        return False
    return any(address in network for network in lan_networks(config_path))


def _period(arguments, default="thirty"):
    period = arguments.get("period", default)
    if period not in PERIODS:
        raise InvalidParams(f"period must be one of {', '.join(PERIODS)}")
    return period


def tool_summary(_arguments):
    enabled, providers = report.configuration()
    return report.summary(enabled, providers)


def tool_daily(_arguments):
    enabled, providers = report.configuration()
    return report.history(enabled, providers, "daily")


def tool_monthly(_arguments):
    enabled, providers = report.configuration()
    return report.history(enabled, providers, "monthly")


def tool_health(_arguments):
    return health.document()


def tool_consumers(arguments):
    return consumers.report(_period(arguments))


def tool_intelligence(arguments):
    return intelligence.dashboard(_period(arguments))


def tool_metrics(_arguments):
    return {"content_type": "text/plain; version=0.0.4", "metrics": intelligence.prometheus()}


def tool_categories(arguments):
    """App category shares. A small, stable answer to "what is the traffic for?"."""
    period = _period(arguments)
    payload = consumers.report(period)
    breakdown = intelligence.category_breakdown(
        payload.get("domains") or [], intelligence.options()["categories"]
    )
    breakdown["period"] = period
    breakdown["status"] = payload.get("status")
    return breakdown


def tool_limits(_arguments):
    """What is currently limited, and what the limits would match.

    Reporting only in itself; the limit-editing tools are separate and declare
    themselves as writers. Read this first when asked why a limit is not working:
    it reports whether limits are enabled, whether dry-run is on, whether this
    firewall can shape uploads at all, and what each running rule has matched.
    """
    cfg = shaper.options()
    plan = shaper.run() if cfg["enabled"] else None
    interception = shaper.netmap_interception()
    document = {
        "status": "ok",
        "enabled": cfg["enabled"],
        "dry_run": cfg["dry_run"],
        "service_limits": cfg["limits"],
        "device_limits": cfg.get("device_limits", []),
        # Whether this firewall can shape uploads at all, so an agent asked why an
        # upload cap is not working can answer from the capability rather than
        # guessing at the configuration.
        "upload_supported": not interception["active"],
        "interception": interception,
        # What the running rules have actually matched: the only direct evidence
        # that a limit is doing something.
        "observed_rules": shaper.verify(interception=interception).get("rules", []),
        "note": (
            "Reporting only. A limit shapes nothing while dry_run is true. Rates are "
            "in Mbit/s, and a cap bounds what a client can sustain rather than "
            "selecting a quality level. A rule in observed_rules with zero bytes has "
            "matched no traffic since it was installed and is limiting nothing."
        ),
    }
    if plan is not None:
        document["planned_services"] = [
            {"service": p["service"], "label": p["label"], "mbit": p["mbit"],
             "addresses": p["address_count"], "shared_excluded": p["shared_excluded"],
             "observed_addresses": p.get("observed_addresses")}
            for p in plan.get("pipes", [])
        ]
        document["planned_devices"] = [
            {"device": p["device"], "name": p["name"], "mbit": p["mbit"],
             "upload_mbit": p.get("upload_mbit")}
            for p in plan.get("device_pipes", [])
        ]
        document["refused"] = (plan.get("rejected") or []) + (plan.get("device_rejected") or [])
        # A device whose download cap was applied but whose upload cap was declined
        # is not a refused device, and reporting it as one would be misleading.
        document["upload_refused"] = plan.get("upload_rejected") or []
    return document


def tool_explain_domain(arguments):
    """What a domain is, which service owns it, and the rule behind each answer."""
    return explain_module.explain(_require(arguments, "domain"), _period(arguments))


def tool_apps(arguments):
    """App-level shares, the finer grain below categories."""
    period = _period(arguments)
    payload = consumers.report(period)
    breakdown = intelligence.app_breakdown(
        payload.get("domains") or [], payload.get("transports") or [])
    breakdown["period"] = period
    breakdown["status"] = payload.get("status")
    return breakdown


def tool_sessions(_arguments):
    """Conversations open right now, from the firewall's own state table."""
    return sessions.document()


def tool_category(arguments):
    """One category's sites and the devices behind them."""
    wanted = _require(arguments, "category")
    period = _period(arguments)
    payload = consumers.report(period)
    cfg_categories = intelligence.options()["categories"]
    detail = intelligence.category_detail(
        wanted, payload.get("domains") or [], payload.get("device_domains") or [],
        cfg_categories,
    )
    if not detail["found"]:
        breakdown = intelligence.category_breakdown(payload.get("domains") or [], cfg_categories)
        known = [row["name"] for row in breakdown["categories"] if row["name"] != "Others"]
        if known:
            detail["available_categories"] = known
    detail["period"] = period
    detail["status"] = payload.get("status")
    return detail


def _require(arguments, key):
    if key not in arguments or arguments[key] is None:
        raise InvalidParams(f"{key} is required")
    value = arguments[key]
    if not isinstance(value, str):
        # Distinguish absent from wrong type: reporting a supplied integer as
        # "required" sends the caller looking for a missing argument it did pass.
        raise InvalidParams(f"{key} must be a string, received {type(value).__name__}")
    if not value.strip():
        raise InvalidParams(f"{key} must not be empty")
    return value.strip()


def tool_device(arguments):
    """One device's sites. Returns a slice, not the whole consumers payload.

    The full report runs to tens of kilobytes; an agent asking what a single
    device did should not have to read all of it to find out.
    """
    wanted = _require(arguments, "device")
    payload = consumers.report(_period(arguments))
    lowered = wanted.lower()
    attribution = payload.get("device_attribution", [])
    match = next(
        (row for row in attribution
         if row["device"] == wanted or str(row["name"]).lower() == lowered),
        None,
    )
    address = match["device"] if match else wanted
    if match is None:
        # Fall back to the RRD host list: a device can appear there with no
        # attributable external flow at all, which is itself the answer.
        host = next(
            (row for row in payload.get("hosts", [])
             if row["ip"] == wanted or str(row["name"]).lower() == lowered),
            None,
        )
        if host is None:
            # Name the busiest devices, not the alphabetically first. Truncating a
            # sorted list silently omitted the largest consumers, so the error
            # implied they were unknown when they were the likeliest thing meant.
            ranked = [row["name"] for row in attribution]
            ranked += [
                row["name"] for row in sorted(
                    payload.get("hosts", []), key=lambda row: row["total"], reverse=True
                ) if row["name"] not in ranked
            ]
            message = f"Unknown device: {wanted}"
            if ranked:
                shown = ranked[:15]
                message += ". Busiest known devices: " + ", ".join(shown)
                if len(ranked) > len(shown):
                    message += f", and {len(ranked) - len(shown)} more"
            raise InvalidParams(message)
        address = host["ip"]
    sites = sorted(
        (row for row in payload.get("device_domains", []) if row["device"] == address),
        key=lambda row: row["total"],
        reverse=True,
    )
    host = next((row for row in payload.get("hosts", []) if row["ip"] == address), None)
    return {
        "status": payload.get("status"),
        "period": payload.get("period"),
        "device": address,
        "name": (match or host or {}).get("name", address),
        "device_total": host.get("total") if host else None,
        "attribution": match,
        "sites": [{"domain": row["domain"], "total": row["total"]} for row in sites],
        "providers": [
            {"name": provider["name"], "total": entry["total"]}
            for provider in payload.get("providers", [])
            for entry in provider.get("devices", []) if entry["ip"] == address
        ],
        "note": (
            "device_total comes from ntopng and counts all this device's traffic, including "
            "LAN-to-LAN. external and the site totals come from firewall flow records and count "
            "only traffic leaving the network. Neither is a subset of the other, so either can "
            "be the larger number: use external, not device_total, to reason about quota."
        ),
        "empty_reason": None if sites else (
            "No site could be attributed for this period. Either the device sent nothing "
            "outbound, or its destinations had no recent DNS answer to match against. Shorter "
            "periods are the common case: flow records are collected in daily buckets, so "
            "period='today' can be empty until the current bucket rolls over."
        ),
    }


def tool_site(arguments):
    """One site's devices. The reciprocal slice of wanquota_device."""
    wanted = _require(arguments, "site").lower().strip(".")
    payload = consumers.report(_period(arguments))
    devices = sorted(
        (row for row in payload.get("device_domains", []) if row["domain"].lower() == wanted),
        key=lambda row: row["total"],
        reverse=True,
    )
    summary = next(
        (row for row in payload.get("domains", []) if row["domain"].lower() == wanted),
        None,
    )
    providers = [
        {"name": provider["name"], "total": entry["total"]}
        for provider in payload.get("providers", [])
        for entry in provider.get("domains", []) if entry["domain"].lower() == wanted
    ]
    # Deliberately not an error. wanquota_device returns a result for a device
    # with no attributable flow, and the reciprocal tool should behave the same:
    # "no traffic" is an answer, not a malformed request, and the server cannot
    # tell a mistyped domain from a real one nobody visited.
    return {
        "status": payload.get("status"),
        "period": payload.get("period"),
        "site": wanted,
        "found": bool(devices or summary or providers),
        "empty_reason": None if (devices or summary or providers) else (
            "No attributed traffic for this site in this period. The domain may be misspelled, "
            "may not have been visited, or its traffic may not have been attributable."
        ),
        "total": summary["total"] if summary else sum(row["total"] for row in devices),
        "observed_ip_count": summary["ip_count"] if summary else None,
        "devices": [
            {"device": row["device"], "name": row["name"], "total": row["total"]}
            for row in devices
        ],
        "providers": providers,
    }


# Output schemas are declared only for the tools whose shape is small and stable.
# The big report payloads are deliberately left undeclared rather than described
# approximately: a schema that drifts from the payload is worse than none, since
# a client will reject valid data.
_BYTES = {"type": "integer", "description": "Bytes."}

DEVICE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string"},
        "period": {"type": "string"},
        "device": {"type": "string", "description": "Resolved IP address."},
        "name": {"type": "string"},
        "device_total": {"type": ["integer", "null"], "description": "ntopng total, all traffic."},
        "sites": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"domain": {"type": "string"}, "total": _BYTES},
                "required": ["domain", "total"],
            },
        },
        "providers": {"type": "array", "items": {"type": "object"}},
        "attribution": {"type": ["object", "null"]},
        "note": {"type": "string"},
        "empty_reason": {"type": ["string", "null"]},
    },
    "required": ["status", "device", "name", "sites"],
}

SITE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string"},
        "period": {"type": "string"},
        "site": {"type": "string"},
        "found": {"type": "boolean"},
        "total": _BYTES,
        "observed_ip_count": {"type": ["integer", "null"]},
        "devices": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "device": {"type": "string"},
                    "name": {"type": "string"},
                    "total": _BYTES,
                },
                "required": ["device", "total"],
            },
        },
        "providers": {"type": "array", "items": {"type": "object"}},
        "empty_reason": {"type": ["string", "null"]},
    },
    "required": ["status", "site", "found", "devices"],
}

CATEGORY_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string"},
        "period": {"type": "string"},
        "total": {"type": "number", "description": "Attributed bytes covered by the shares."},
        "known_percent": {"type": "number", "description": "Share that matched a category."},
        "top_n": {"type": "integer"},
        "categories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "total": {"type": "number"},
                    "percent": {"type": "number"},
                    "categories_folded": {
                        "type": "integer",
                        "description": "Only on the Others row: how many categories it covers.",
                    },
                },
                "required": ["name", "total", "percent"],
            },
        },
        "note": {"type": "string"},
    },
    "required": ["status", "total", "categories"],
}

HEALTH_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["ok", "degraded", "failed"]},
        "generated_at": {"type": "string"},
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "status": {"type": "string", "enum": ["ok", "stale", "failed", "disabled"]},
                    "detail": {"type": "string"},
                    "age_seconds": {"type": ["integer", "null"]},
                    "required": {"type": "boolean"},
                },
                "required": ["name", "status", "detail"],
            },
        },
    },
    "required": ["status", "checks"],
}


_PERIOD_SCHEMA = {
    "type": "object",
    "properties": {
        "period": {
            "type": "string",
            "enum": list(PERIODS),
            "default": "thirty",
            "description": "Reporting window to cover.",
        }
    },
}

_NO_ARGUMENTS = {"type": "object", "properties": {}}

TOOLS = (
    {
        "name": "wanquota_summary",
        "title": "WAN quota summary",
        "description": (
            "Current billing-cycle quota status for every enabled WAN provider: used and "
            "remaining GB, percent of allowance, daily budget, and projected cycle total."
        ),
        "inputSchema": _NO_ARGUMENTS,
        "handler": tool_summary,
    },
    {
        "name": "wanquota_daily",
        "title": "Daily history",
        "description": "Per-day download and upload history for each enabled WAN provider.",
        "inputSchema": _NO_ARGUMENTS,
        "handler": tool_daily,
    },
    {
        "name": "wanquota_monthly",
        "title": "Monthly history",
        "description": "Per-month download and upload history for each enabled WAN provider.",
        "inputSchema": _NO_ARGUMENTS,
        "handler": tool_monthly,
    },
    {
        "name": "wanquota_health",
        "title": "Data source health",
        "description": (
            "Freshness and availability of every data source the reports depend on "
            "(vnStat, ntopng, Insight/NetFlow, DNS attribution, alert monitor). Check this "
            "first when a number looks wrong: a stale collector yields stale reports."
        ),
        "inputSchema": _NO_ARGUMENTS,
        "outputSchema": HEALTH_OUTPUT_SCHEMA,
        "handler": tool_health,
    },
    {
        "name": "wanquota_consumers",
        "title": "Top consumers and domains",
        "description": (
            "Top LAN devices and attributed domains by bytes. Domain attribution is an "
            "estimate correlating flow bytes with recent DNS answers; read the coverage "
            "percentage in the response before treating the domain list as complete."
        ),
        "inputSchema": _PERIOD_SCHEMA,
        "handler": tool_consumers,
    },
    {
        "name": "wanquota_intelligence",
        "title": "Forecasts and guardrails",
        "description": (
            "Quota forecasts, gateway quality, device-group budgets, anomalies and the "
            "current guardrail recommendation per provider. Recommendations are advisory "
            "while enforcement is disabled or dry-run."
        ),
        "inputSchema": _PERIOD_SCHEMA,
        "handler": tool_intelligence,
    },
    {
        "name": "wanquota_metrics",
        "title": "Prometheus metrics",
        "description": "WAN quota metrics in Prometheus text exposition format.",
        "inputSchema": _NO_ARGUMENTS,
        "handler": tool_metrics,
    },
    {
        "name": "wanquota_categories",
        "title": "App categories breakdown",
        "description": (
            "Share of attributed traffic per app category (Media Streaming, A.I. Tools, "
            "Conferencing and so on), largest first, with the tail rolled into Others. "
            "Prefer this over wanquota_consumers when the question is what the traffic is "
            "for rather than which device or domain produced it."
        ),
        "inputSchema": _PERIOD_SCHEMA,
        "outputSchema": CATEGORY_OUTPUT_SCHEMA,
        "handler": tool_categories,
    },
    {
        "name": "wanquota_limits",
        "title": "Configured bandwidth limits",
        "description": (
            "What is currently capped, per service and per device, at what rate, and "
            "how many addresses each limit would actually match. Also reports whether "
            "limits are enabled and whether dry-run is on, since a limit shapes nothing "
            "while dry-run is on, whether this firewall can shape uploads at all, and "
            "the bytes each running rule has matched. Use this to answer 'why is my "
            "limit not working?'. Read-only: this cannot set or clear a limit."
        ),
        "inputSchema": _NO_ARGUMENTS,
        "handler": tool_limits,
    },
    {
        "name": "wanquota_explain_domain",
        "title": "Explain a domain",
        "description": (
            "Identify a domain: which limitable service owns it (Netflix, YouTube, "
            "Windows Update and so on), which application and category it is reported "
            "under, how much it moved, which devices used it, and whether its addresses "
            "are exclusive enough to be capped. Every conclusion names the rule that "
            "produced it. Use this to answer 'what is this domain and is it Netflix?'."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Domain name, e.g. ipv4-c001.ix.nflxvideo.net."},
                "period": _PERIOD_SCHEMA["properties"]["period"],
            },
            "required": ["domain"],
        },
        "handler": tool_explain_domain,
    },
    {
        "name": "wanquota_apps",
        "title": "Apps breakdown",
        "description": (
            "Share of traffic per application (GitHub, ChatGPT, YouTube and so on), "
            "largest first, with the tail rolled into Others. Traffic with no known "
            "domain is grouped by transport instead, so entries like 'Quic UDP "
            "Connection' are unnamed traffic rather than one application."
        ),
        "inputSchema": _PERIOD_SCHEMA,
        "handler": tool_apps,
    },
    {
        "name": "wanquota_sessions",
        "title": "Live sessions",
        "description": (
            "Conversations open right now: which device, to what destination, over "
            "which service, with age and per-state bytes. Read from the firewall state "
            "table, so it shows traffic even when DNS never named the destination. "
            "State byte counters are not quota accounting."
        ),
        "inputSchema": _NO_ARGUMENTS,
        "handler": tool_sessions,
    },
    {
        "name": "wanquota_category",
        "title": "One app category's contents",
        "description": (
            "What one app category is made of: the sites in it ranked by bytes, and the "
            "devices that used them. Use after wanquota_categories to explain a share. "
            "'Others' is a rollup rather than a category and returns nothing."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Category name, e.g. Media Streaming."},
                "period": _PERIOD_SCHEMA["properties"]["period"],
            },
            "required": ["category"],
        },
        "handler": tool_category,
    },
    {
        "name": "wanquota_device",
        "title": "One device's sites",
        "description": (
            "What one device exchanged traffic with: its sites ranked by bytes, its "
            "attributed share, and which providers carried it. Prefer this over "
            "wanquota_consumers when the question is about a single device. Accepts "
            "either the friendly name (TRUENAS) or the IP address."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "device": {
                    "type": "string",
                    "description": "Device name or IP address, e.g. TRUENAS or 192.168.1.10.",
                },
                "period": _PERIOD_SCHEMA["properties"]["period"],
            },
            "required": ["device"],
        },
        "outputSchema": DEVICE_OUTPUT_SCHEMA,
        "handler": tool_device,
    },
    {
        "name": "wanquota_site",
        "title": "One site's devices",
        "description": (
            "Which devices used one site, ranked by bytes, and which providers carried "
            "it. The reciprocal of wanquota_device; prefer it over wanquota_consumers "
            "when the question is about a single domain."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "site": {"type": "string", "description": "Domain name, e.g. video.example.com."},
                "period": _PERIOD_SCHEMA["properties"]["period"],
            },
            "required": ["site"],
        },
        "outputSchema": SITE_OUTPUT_SCHEMA,
        "handler": tool_site,
    },
)

# A reading tool declares itself read-only so a cautious client can call it without
# asking the user to approve each one. The hint is only worth stating because it is
# not true of every tool any more: this server can change configuration, and a client
# that cannot tell the two apart would have to treat reports as dangerous or edits as
# safe. Every tool therefore carries its own annotations, and the default is the
# careful one.
READ_ONLY_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}

# A writing tool. Not idempotent in general — setting a limit twice is harmless, but
# the client should not assume a retry is free.
WRITE_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}

# A writing tool that removes something the user configured.
REMOVE_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": True,
    "idempotentHint": False,
    "openWorldHint": False,
}


CONFIGURE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "configure.php")

# Never returned to a caller. Reading configuration is useful; handing out the SMTP
# password because it happens to live in the same model is not.
REDACTED_SETTINGS = ("smtp_password",)


def configure(instruction, script=None, runner=None):
    """Apply one configuration change through the model, and report what it did.

    Writes go through configure.php because the configuration lives in a PHP model
    that validates it. Reimplementing that validation here would mean an agent could
    write values the interface would reject.
    """
    invoke = runner or _run_configure
    return invoke(script or CONFIGURE_SCRIPT, instruction)


def _run_configure(script, instruction):
    try:
        done = subprocess.run(["/usr/local/bin/php", script],
                              input=json.dumps(instruction), capture_output=True,
                              text=True, timeout=180)
    except Exception as error:
        return {"status": "failed", "error": str(error)}
    text = (done.stdout or "").strip()
    try:
        return json.loads(text.splitlines()[-1]) if text else {
            "status": "failed", "error": (done.stderr or "no output").strip()[:400]}
    except (ValueError, IndexError):
        return {"status": "failed", "error": text[:400] or "unreadable result"}


def tool_settings(_arguments):
    """Current plugin settings, with credentials withheld."""
    try:
        root = ET.parse(consumers.CONFIG_PATH).getroot()
    except (OSError, ET.ParseError) as error:
        return {"status": "failed", "error": f"could not read the configuration: {error}"}
    general = root.find("./OPNsense/WanQuota/general")
    if general is None:
        return {"status": "failed", "error": "the plugin has no saved configuration yet"}
    values = {}
    for child in general:
        name = child.tag
        values[name] = "(withheld)" if name in REDACTED_SETTINGS else (child.text or "")
    return {
        "status": "ok",
        "settings": values,
        "note": (
            "Values as stored. Booleans are '1' or '0'. A credential is reported as "
            "(withheld) and cannot be read through this server, though it can be set."
        ),
    }


def tool_set_settings(arguments):
    fields = arguments.get("fields")
    if not isinstance(fields, dict) or not fields:
        raise InvalidParams("fields must be a non-empty object of setting names to values")
    return configure({"action": "set_settings", "fields": fields})


def _limit_state(arguments):
    """The optional shaper switches shared by the limit-editing tools."""
    state = {}
    for key in ("enabled", "dry_run"):
        if arguments.get(key) is not None:
            state[key] = bool(arguments[key])
    return state


def tool_set_service_limit(arguments):
    service = str(arguments.get("service") or "").strip().lower()
    if not service:
        raise InvalidParams("service is required")
    if service not in shaper.STREAMING_SERVICES:
        raise InvalidParams(
            f"unknown service: {service}. Call wanquota_limits for the catalogue.")
    if arguments.get("mbit") is None and not str(arguments.get("resolution") or "").strip():
        raise InvalidParams("either mbit or resolution is required")
    return configure({"action": "set_service_limit", "service": service,
                      "mbit": arguments.get("mbit"),
                      "resolution": arguments.get("resolution"),
                      **_limit_state(arguments)})


def tool_remove_service_limit(arguments):
    service = str(arguments.get("service") or "").strip().lower()
    if not service:
        raise InvalidParams("service is required")
    return configure({"action": "remove_service_limit", "service": service,
                      **_limit_state(arguments)})


def tool_set_device_limit(arguments):
    device = str(arguments.get("device") or "").strip()
    if not device:
        raise InvalidParams("device is required: an address, MAC or DHCP hostname")
    if arguments.get("mbit") is None:
        raise InvalidParams("mbit is required")
    return configure({"action": "set_device_limit", "device": device,
                      "mbit": arguments.get("mbit"),
                      "upload_mbit": arguments.get("upload_mbit"),
                      **_limit_state(arguments)})


def tool_remove_device_limit(arguments):
    device = str(arguments.get("device") or "").strip()
    if not device:
        raise InvalidParams("device is required")
    return configure({"action": "remove_device_limit", "device": device,
                      **_limit_state(arguments)})


_STATE_PROPERTIES = {
    "enabled": {"type": "boolean",
                "description": "Turn limits on or off. Omit to leave the current state."},
    "dry_run": {"type": "boolean",
                "description": "When true a limit is recorded and nothing is shaped. "
                               "Omit to leave the current state."},
}

WRITE_TOOLS = (
    {
        "name": "wanquota_settings",
        "title": "Read plugin settings",
        "description": (
            "Every plugin setting as currently stored: providers and their quotas, "
            "reporting and retention, alerting, enforcement and limit state. Booleans "
            "are '1' or '0'. Credentials are withheld. Read this before changing a "
            "setting so the value being replaced is known."
        ),
        "inputSchema": _NO_ARGUMENTS,
        "handler": tool_settings,
    },
    {
        "name": "wanquota_set_settings",
        "title": "Change plugin settings",
        "description": (
            "Set one or more plugin settings. Pass `fields` as an object of setting "
            "name to value, using the names wanquota_settings returns; booleans accept "
            "true/false or '1'/'0'. The whole change is validated by the same model the "
            "web interface uses, and a rejected value changes nothing and returns the "
            "reason. An unknown setting name is an error rather than a silent no-op."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "fields": {"type": "object",
                           "description": "Setting name to value, e.g. "
                                          "{\"shaper_enabled\": true, \"top_limit\": 20}."},
            },
            "required": ["fields"],
            "additionalProperties": False,
        },
        "annotations": WRITE_ANNOTATIONS,
        "handler": tool_set_settings,
    },
    {
        "name": "wanquota_set_service_limit",
        "title": "Cap a service",
        "description": (
            "Cap a catalogued service's bandwidth. Give either `mbit` for an explicit "
            "rate or `resolution` for a published preset (4k, 1080p, 720p, 480p, "
            "audio_only). Setting a limit for a service that already has one replaces "
            "it. The limit is applied immediately unless dry-run is on, and the result "
            "reports how many addresses it matched — a cap matching none shapes "
            "nothing. Coverage is partial by construction: a device using encrypted "
            "DNS or a VPN is not matched."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "service": {"type": "string",
                            "description": "Catalogue key, e.g. netflix, youtube, windows_update."},
                "mbit": {"type": "number", "description": "Rate in Mbit/s. Wins over resolution."},
                "resolution": {"type": "string",
                               "enum": sorted(shaper.RESOLUTION_PRESETS),
                               "description": "A published quality preset."},
                **_STATE_PROPERTIES,
            },
            "required": ["service"],
            "additionalProperties": False,
        },
        "annotations": WRITE_ANNOTATIONS,
        "handler": tool_set_service_limit,
    },
    {
        "name": "wanquota_remove_service_limit",
        "title": "Remove a service cap",
        "description": (
            "Remove the bandwidth cap on a service. The limit is released immediately. "
            "Removing a limit that is not set is an error, so a caller is told rather "
            "than believing it removed something."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Catalogue key."},
                **_STATE_PROPERTIES,
            },
            "required": ["service"],
            "additionalProperties": False,
        },
        "annotations": REMOVE_ANNOTATIONS,
        "handler": tool_remove_service_limit,
    },
    {
        "name": "wanquota_set_device_limit",
        "title": "Cap a device",
        "description": (
            "Cap one device's bandwidth. Identify it by address, MAC or DHCP hostname; "
            "a MAC is preferred because it keeps applying after DHCP changes the "
            "address. `mbit` caps download and `upload_mbit` caps upload. Unlike a "
            "service cap this does not depend on identifying addresses, so it is the "
            "reliable way to limit a device. The firewall itself is always refused. "
            "Upload caps do not work on a firewall whose LAN ingress is intercepted by "
            "a netmap capture engine; check upload_supported from wanquota_limits."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "device": {"type": "string",
                           "description": "Address, MAC or DHCP hostname. MAC is preferred."},
                "mbit": {"type": "number", "description": "Download cap in Mbit/s."},
                "upload_mbit": {"type": "number",
                                "description": "Upload cap in Mbit/s. Optional."},
                **_STATE_PROPERTIES,
            },
            "required": ["device", "mbit"],
            "additionalProperties": False,
        },
        "annotations": WRITE_ANNOTATIONS,
        "handler": tool_set_device_limit,
    },
    {
        "name": "wanquota_remove_device_limit",
        "title": "Remove a device cap",
        "description": (
            "Remove the bandwidth cap on a device, identified the same way it was set. "
            "The limit is released immediately. Removing one that is not set is an "
            "error."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "device": {"type": "string", "description": "Address, MAC or DHCP hostname."},
                **_STATE_PROPERTIES,
            },
            "required": ["device"],
            "additionalProperties": False,
        },
        "annotations": REMOVE_ANNOTATIONS,
        "handler": tool_remove_device_limit,
    },
)

TOOLS = TOOLS + WRITE_TOOLS

TOOLS_BY_NAME = {tool["name"]: tool for tool in TOOLS}


def tool_descriptors():
    descriptors = []
    for tool in TOOLS:
        descriptor = {
            **{key: tool[key] for key in ("name", "description", "inputSchema")},
            "annotations": {"title": tool["title"],
                            **tool.get("annotations", READ_ONLY_ANNOTATIONS)},
        }
        if "outputSchema" in tool:
            descriptor["outputSchema"] = tool["outputSchema"]
        descriptors.append(descriptor)
    return descriptors


def call_tool(name, arguments):
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        raise UnknownTool(f"Unknown tool: {name}")
    if not isinstance(arguments, dict):
        raise InvalidParams("arguments must be an object")
    return tool["handler"](arguments)



# Two of the reports read naturally as documents rather than actions, so they are
# also offered as resources. Same read-only data, addressed rather than invoked.
RESOURCES = (
    {
        "uri": "wanquota://summary",
        "name": "WAN quota summary",
        "description": "Current billing-cycle status for every enabled provider.",
        "mimeType": "application/json",
        "handler": tool_summary,
    },
    {
        "uri": "wanquota://health",
        "name": "WAN quota data health",
        "description": "Freshness and availability of every data source the reports depend on.",
        "mimeType": "application/json",
        "handler": tool_health,
    },
)

RESOURCES_BY_URI = {item["uri"]: item for item in RESOURCES}


def resource_descriptors():
    return [
        {key: item[key] for key in ("uri", "name", "description", "mimeType")}
        for item in RESOURCES
    ]


def read_resource(uri):
    item = RESOURCES_BY_URI.get(uri)
    if item is None:
        raise InvalidParams(
            f"Unknown resource: {uri}. Available: " + ", ".join(sorted(RESOURCES_BY_URI))
        )
    return {
        "uri": uri,
        "mimeType": item["mimeType"],
        "text": json.dumps(item["handler"]({}), separators=(",", ":")),
    }


def _result(request_id, payload):
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}


def _error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle(request):
    """Dispatch one decoded JSON-RPC request. Returns a response dict, or None for notifications."""
    if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
        return _error(None, INVALID_REQUEST, "Expected a JSON-RPC 2.0 request object")

    method = request.get("method")
    request_id = request.get("id")
    params = request.get("params") or {}
    is_notification = "id" not in request

    if method == "initialize":
        # Answer with the requested revision only when it is one this server
        # actually speaks. Echoing anything the client asked for claimed support
        # for revisions that were never implemented; a client negotiating on that
        # answer would proceed on a false premise. Otherwise name our own version
        # and let the client decide whether it can continue.
        requested = params.get("protocolVersion") if isinstance(params, dict) else None
        agreed = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else PROTOCOL_VERSION
        return _result(request_id, {
            "protocolVersion": agreed,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
            },
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })

    if method in ("notifications/initialized", "initialized"):
        return None

    if method == "ping":
        return None if is_notification else _result(request_id, {})

    if method == "tools/list":
        return _result(request_id, {"tools": tool_descriptors()})

    if method == "resources/list":
        return _result(request_id, {"resources": resource_descriptors()})

    if method == "resources/read":
        uri = params.get("uri") if isinstance(params, dict) else None
        try:
            contents = read_resource(uri)
        except InvalidParams as error:
            return _error(request_id, INVALID_PARAMS, str(error))
        except Exception as error:
            return _error(request_id, INTERNAL_ERROR, f"{type(error).__name__}: {error}")
        return _result(request_id, {"contents": [contents]})

    if method == "tools/call":
        name = params.get("name") if isinstance(params, dict) else None
        arguments = params.get("arguments") or {} if isinstance(params, dict) else {}
        try:
            payload = call_tool(name, arguments)
        except UnknownTool as error:
            return _error(request_id, METHOD_NOT_FOUND, str(error))
        except InvalidParams as error:
            return _error(request_id, INVALID_PARAMS, str(error))
        except Exception as error:
            # Anything raised inside a tool is a collector or data problem, not a
            # bad request. It must not kill the session, and it must not be
            # reported as the caller's fault: a KeyError from a report helper is
            # a LookupError, and would otherwise read as "unknown tool".
            return _result(request_id, {
                "content": [{"type": "text", "text": f"{type(error).__name__}: {error}"}],
                "isError": True,
            })
        result = {
            "content": [{"type": "text", "text": json.dumps(payload, separators=(",", ":"))}],
            "isError": False,
        }
        # A tool that advertises an outputSchema must also return the parsed form,
        # so a client can use the data without re-parsing the text block.
        if "outputSchema" in TOOLS_BY_NAME[name] and isinstance(payload, dict):
            result["structuredContent"] = payload
        return _result(request_id, result)

    if is_notification:
        return None
    return _error(request_id, METHOD_NOT_FOUND, f"Unknown method: {method}")


def handle_raw(line):
    """Decode one JSON-RPC line and dispatch it. Returns a response dict or None."""
    try:
        request = json.loads(line)
    except (ValueError, TypeError):
        return _error(None, PARSE_ERROR, "Invalid JSON")
    return handle(request)


def serve_stdio(stdin=None, stdout=None):
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        response = handle_raw(line)
        if response is None:
            continue
        stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
        stdout.flush()


def serve_once(encoded, client=None, config_path=None):
    """Answer one request for the HTTP transport.

    A JSON-RPC notification has no response. Rather than teach the controller to
    parse JSON-RPC, signal it with a sentinel so it can reply 202 Accepted with
    no body, which is what an MCP client over HTTP expects. Protocol decisions
    stay here where they are covered by tests; the controller only moves bytes.
    """
    if not is_permitted(client, config_path):
        return _error(None, NOT_PERMITTED, "WAN quota MCP is reachable from the LAN only")
    # Strip whitespace before validating: PHP's base64_encode emits one line, but
    # a hand-run configctl using a wrapping encoder (FreeBSD b64encode) does not,
    # and validate=True rejects the embedded newline.
    encoded = "".join((encoded or "").split())
    try:
        payload = base64.b64decode(encoded, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return _error(None, PARSE_ERROR, "Request body was not valid base64 UTF-8")
    return handle_raw(payload) or {"_notification": True}


def main():
    arguments = sys.argv[1:]
    if arguments and arguments[0] == "--once":
        encoded = arguments[1] if len(arguments) > 1 else ""
        client = arguments[2] if len(arguments) > 2 else None
        print(json.dumps(serve_once(encoded, client), separators=(",", ":")))
        return
    serve_stdio()


if __name__ == "__main__":
    main()
