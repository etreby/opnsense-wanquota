#!/usr/local/bin/python3
"""Report freshness and availability of WAN quota data sources."""

import datetime as dt
import glob
import json
import os
import sqlite3
import xml.etree.ElementTree as ET

import consumers
import report

INTELLIGENCE_DB = "/var/db/wanquota/intelligence.sqlite"


def age_seconds(path, now):
    try:
        return max(0, int(now - os.path.getmtime(path)))
    except OSError:
        return None


def status(name, available, detail, freshness=None, required=True):
    if not available:
        state = "failed" if required else "disabled"
    elif freshness is not None and freshness > 900:
        state = "stale"
    else:
        state = "ok"
    return {"name": name, "status": state, "detail": detail, "age_seconds": freshness, "required": required}


def domain_database_health(now, enabled):
    if not enabled:
        return status("Domain attribution", False, "Disabled in plugin settings", required=False)
    if not os.path.exists(consumers.DOMAIN_DB):
        return status("Domain attribution", False, "DNS mapping database has not been created")
    try:
        with sqlite3.connect(f"file:{consumers.DOMAIN_DB}?mode=ro", uri=True) as connection:
            count, last_seen = connection.execute("SELECT count(*), max(last_seen) FROM ip_domains").fetchone()
        freshness = max(0, int(now - last_seen)) if last_seen else age_seconds(consumers.DOMAIN_DB, now)
        return status("Domain attribution", True, f"{count} current IP-to-domain mappings", freshness)
    except sqlite3.Error as error:
        return status("Domain attribution", False, f"Database error: {error}")


def main():
    now = dt.datetime.now().timestamp()
    settings, _ = consumers.settings_and_names()
    checks = []

    flow_db = consumers.flow_database()
    checks.append(status(
        "Insight/NetFlow",
        flow_db is not None,
        os.path.basename(flow_db) if flow_db else "Daily flow database unavailable",
        age_seconds(flow_db, now) if flow_db else None,
        settings["domain_enabled"],
    ))

    rrd_roots = glob.glob(consumers.NTOP_RRD_PATTERN)
    rrd_files = [path for root in rrd_roots for path in glob.glob(os.path.join(root, "*", "*", "*", "*", "bytes.rrd"))]
    newest_rrd = max((os.path.getmtime(path) for path in rrd_files), default=None)
    checks.append(status(
        "ntopng host accounting",
        bool(rrd_files),
        f"{len(rrd_files)} host RRDs" if rrd_files else "No host RRDs discovered",
        max(0, int(now - newest_rrd)) if newest_rrd else None,
        settings["enabled"],
    ))

    checks.append(domain_database_health(now, settings["domain_enabled"]))

    enabled, providers = report.configuration()
    for provider in providers:
        rows, error = report.vnstat_rows(provider["interface"], "d")
        checks.append(status(
            f"vnStat: {provider['name']}",
            error is None,
            f"{len(rows)} daily records on {provider['interface']}" if error is None else error,
            required=enabled,
        ))

    alert_state_age = age_seconds(report.ALERT_STATE, now)
    alert_options = report.alert_configuration()
    checks.append(status(
        "Quota alert monitor",
        alert_options["enabled"],
        f"Repeat interval {alert_options['repeat_hours']} hours" if alert_options["enabled"] else "Disabled in plugin settings",
        alert_state_age,
        required=False,
    ))
    intelligence_age = age_seconds(INTELLIGENCE_DB, now)
    intelligence_enabled = False
    try:
        root = ET.parse(report.CONFIG_PATH).getroot()
        intelligence_enabled = report.text(root.find("./OPNsense/WanQuota/general"), "intelligence_enabled", "1") == "1"
    except (OSError, ET.ParseError):
        pass
    checks.append(status("WAN intelligence history", os.path.exists(INTELLIGENCE_DB), "Forecast, quality, anomaly and cycle archive database" if os.path.exists(INTELLIGENCE_DB) else "No intelligence snapshots collected", intelligence_age, intelligence_enabled))

    overall = "ok"
    if any(item["status"] == "failed" and item["required"] for item in checks):
        overall = "failed"
    elif any(item["status"] in {"failed", "stale"} for item in checks):
        overall = "degraded"
    print(json.dumps({
        "status": overall,
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "checks": checks,
    }, separators=(",", ":")))


if __name__ == "__main__":
    main()
