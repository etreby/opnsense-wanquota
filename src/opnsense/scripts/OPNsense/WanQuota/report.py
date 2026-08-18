#!/usr/local/bin/python3
"""Configurable vnStat billing-cycle reports for the OPNsense WAN Quota plugin."""

import calendar
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


CONFIG_PATH = "/conf/config.xml"
VERSION_PATH = "/usr/local/opnsense/version/wanquota"
STATE_DIR = "/var/db/wanquota"
ALERT_STATE = os.path.join(STATE_DIR, "alerts.json")
DEFAULTS = tuple(
    {"name": f"ISP {index}", "logical_interface": "opt1" if index == 2 else "wan",
     "quota_gb": 100, "cycle_day": 1, "warning_percent": 80}
    for index in range(1, 5)
)



def plugin_version(path=None):
    """The installed package version, or None when it cannot be determined.

    Read from the version file the package build writes rather than hardcoded, so
    the interface cannot claim a version the running code is not.
    """
    try:
        with open(path or VERSION_PATH, encoding="utf-8") as handle:
            return (json.load(handle).get("product_version") or "").strip() or None
    except (OSError, ValueError, AttributeError):
        return None


def text(node, path, default):
    child = node.find(path) if node is not None else None
    return child.text.strip() if child is not None and child.text else default


def bounded_int(value, default, minimum, maximum):
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError):
        return default


def configuration():
    root = ET.parse(CONFIG_PATH).getroot()
    settings = root.find("./OPNsense/WanQuota/general")
    enabled = text(settings, "enabled", "1") == "1"
    providers = []
    for index, defaults in enumerate(DEFAULTS, 1):
        default_enabled = "1" if index <= 2 else "0"
        if text(settings, f"provider{index}_enabled", default_enabled) != "1":
            continue
        logical = text(settings, f"provider{index}_interface", defaults["logical_interface"])
        physical = text(root, f"./interfaces/{logical}/if", logical)
        providers.append({
            "slot": index,
            "name": text(settings, f"provider{index}_name", defaults["name"]),
            "logical_interface": logical,
            "interface": physical,
            "quota_gb": bounded_int(text(settings, f"provider{index}_quota_gb", defaults["quota_gb"]), defaults["quota_gb"], 1, 100000),
            "cycle_day": bounded_int(text(settings, f"provider{index}_cycle_day", defaults["cycle_day"]), defaults["cycle_day"], 1, 31),
            "warning_percent": bounded_int(text(settings, f"provider{index}_warning_percent", defaults["warning_percent"]), defaults["warning_percent"], 1, 100),
            "cycle_cost": bounded_int(text(settings, f"provider{index}_cycle_cost", 0), 0, 0, 1000000),
            "baseline_gb": bounded_int(text(settings, f"provider{index}_baseline_gb", 0), 0, 0, 100000),
            "baseline_cycle": text(settings, f"provider{index}_baseline_cycle", ""),
        })
    return enabled, providers


def alert_configuration():
    root = ET.parse(CONFIG_PATH).getroot()
    settings = root.find("./OPNsense/WanQuota/general")
    return {
        "enabled": text(settings, "alerts_enabled", "1") == "1",
        "projection": text(settings, "projection_alert_enabled", "1") == "1",
        "repeat_hours": bounded_int(text(settings, "alert_repeat_hours", "24"), 24, 1, 168),
    }


def load_alert_state():
    try:
        with open(ALERT_STATE, encoding="utf-8") as handle:
            document = json.load(handle)
            return document if isinstance(document, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_alert_state(state):
    os.makedirs(STATE_DIR, mode=0o750, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="alerts-", suffix=".json", dir=STATE_DIR)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(state, handle, separators=(",", ":"), sort_keys=True)
        os.chmod(temporary, 0o640)
        os.replace(temporary, ALERT_STATE)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def evaluate_alerts(document, now=None, emit=True):
    options = alert_configuration()
    if not options["enabled"]:
        return {"status": "disabled", "events": []}
    now = int(now if now is not None else dt.datetime.now().timestamp())
    repeat_seconds = options["repeat_hours"] * 3600
    state = load_alert_state()
    events = []
    active_keys = set()
    for provider in document.get("providers", []):
        if not provider.get("available"):
            continue
        conditions = []
        if provider["percent"] >= provider["warning_percent"]:
            conditions.append(("threshold", f"usage reached {provider['percent']:.1f}%"))
        if options["projection"] and provider["projected"] > provider["quota"]:
            projected_percent = provider["projected"] / provider["quota"] * 100
            conditions.append(("projection", f"projected usage is {projected_percent:.1f}% of quota"))
        for condition, detail in conditions:
            key = f"{provider['logical_interface']}:{provider['start']}:{condition}"
            active_keys.add(key)
            last_sent = int(state.get(key, 0) or 0)
            if now - last_sent < repeat_seconds:
                continue
            message = f"{provider['name']}: {detail}; {provider['remaining'] / 1e9:.2f} GB remaining"
            if emit:
                subprocess.run(["/usr/bin/logger", "-t", "wanquota", message], check=False)
            state[key] = now
            events.append({"provider": provider["name"], "condition": condition, "message": message})
    state = {key: value for key, value in state.items() if key in active_keys}
    save_alert_state(state)
    return {"status": "ok", "events": events, "repeat_hours": options["repeat_hours"]}


def monitor(enabled, providers):
    document = summary(enabled, providers)
    return {"status": document["status"], "alerts": evaluate_alerts(document), "summary": document}


def add_month(value):
    year = value.year + (value.month == 12)
    month = 1 if value.month == 12 else value.month + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def cycle_bounds(today, cycle_day):
    candidate = today.replace(day=min(cycle_day, calendar.monthrange(today.year, today.month)[1]))
    if today < candidate:
        previous = today.replace(day=1) - dt.timedelta(days=1)
        candidate = previous.replace(day=min(cycle_day, calendar.monthrange(previous.year, previous.month)[1]))
    return candidate, add_month(candidate)


def vnstat_rows(interface, period):
    try:
        output = subprocess.check_output(
            ["/usr/local/bin/vnstat", "--json", period, "-i", interface],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=15,
        )
        document = json.loads(output)
        return document["interfaces"][0]["traffic"].get({"d": "day", "m": "month"}[period], []), None
    except (subprocess.SubprocessError, json.JSONDecodeError, KeyError, IndexError) as error:
        return [], str(error)


def row_date(row):
    stamp = row["date"]
    return dt.date(stamp["year"], stamp["month"], stamp.get("day", 1))


def provider_summary(provider, today):
    start, end = cycle_bounds(today, provider["cycle_day"])
    rows, error = vnstat_rows(provider["interface"], "d")
    relevant = [(row_date(row), row) for row in rows if start <= row_date(row) < end]
    rx = sum(row["rx"] for _, row in relevant)
    tx = sum(row["tx"] for _, row in relevant)
    baseline = provider.get("baseline_gb", 0) * 1_000_000_000 if provider.get("baseline_cycle") == start.isoformat() else 0
    used = rx + tx + baseline
    quota = provider["quota_gb"] * 1_000_000_000
    remaining = max(0, quota - used)
    elapsed = max(1, (today - start).days + 1)
    days_left = max(0, (end - today).days)
    percent = used / quota * 100
    first_seen = min((date for date, _ in relevant), default=None)
    # Project from the days actually measured, not from the days elapsed. vnStat
    # only holds history from when it started collecting, so a cycle that began
    # before that has days with no data at all. Dividing the total by elapsed days
    # spreads real traffic across days that were never observed and reports a rate
    # several times lower than the measured one.
    measured_days = len({date for date, _ in relevant})
    missing_days = max(0, elapsed - measured_days)
    # The rate comes from the traffic actually observed, never from the baseline.
    # A baseline stands for the days vnStat never recorded, so dividing it by the
    # measured days charges five days with a fortnight of traffic. Entering the ISP
    # figure the note below asks for used to inflate the rate tenfold and project an
    # overrun on a provider sitting at a third of its quota.
    rate = (rx + tx) / measured_days if measured_days else 0
    projected = used + rate * days_left
    if not missing_days:
        basis, note = "measured", None
    elif baseline:
        basis = "baselined"
        note = (
            f"{missing_days} of {elapsed} elapsed cycle days have no vnStat data, but the "
            f"baseline covers them: the cycle total is anchored to the {baseline / 1e9:.0f} GB "
            f"reported by the ISP plus what has been measured since. The rate comes from the "
            f"{measured_days} measured day(s), so it describes current traffic rather than the "
            f"cycle as a whole."
        )
    else:
        basis = "partial"
        note = (
            f"{missing_days} of {elapsed} elapsed cycle days have no vnStat data, so "
            f"'used' is a floor and the projection is a lower bound. The rate comes from "
            f"the {measured_days} measured day(s). To close the gap, enter the usage your "
            f"ISP reports for this cycle as this provider's baseline and set its baseline "
            f"cycle to {start.isoformat()}; the baseline is added to the measured total."
        )
    return {
        **provider,
        "quota": quota,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "rx": rx,
        "tx": tx,
        "baseline": baseline,
        "used": used,
        "remaining": remaining,
        "percent": percent,
        "days_left": days_left,
        "daily_budget": remaining / days_left if days_left else 0,
        "projected": projected,
        "daily_average": rate,
        "elapsed_days": elapsed,
        "measured_days": measured_days,
        "missing_days": missing_days,
        "first_seen": first_seen.isoformat() if first_seen else None,
        "complete": first_seen == start,
        "projection_basis": basis,
        "projection_note": note,
        "warning": percent >= provider["warning_percent"],
        "available": error is None,
        "error": error,
        "cost_per_quota_gb": provider.get("cycle_cost", 0) / provider["quota_gb"] if provider["quota_gb"] else 0,
        "cost_per_used_gb": provider.get("cycle_cost", 0) / (used / 1e9) if used else 0,
    }


def summary(enabled, providers):
    today = dt.date.today()
    return {
        "status": "ok" if enabled else "disabled",
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "plugin_version": plugin_version(),
        "providers": [provider_summary(provider, today) for provider in providers] if enabled else [],
    }


def history(enabled, providers, period):
    result = {"status": "ok" if enabled else "disabled", "period": period, "providers": []}
    if not enabled:
        return result
    for provider in providers:
        rows, error = vnstat_rows(provider["interface"], "d" if period == "daily" else "m")
        result["providers"].append({
            "name": provider["name"],
            "logical_interface": provider["logical_interface"],
            "interface": provider["interface"],
            "available": error is None,
            "error": error,
            "rows": [{"date": row_date(row).isoformat(), "rx": row["rx"], "tx": row["tx"], "total": row["rx"] + row["tx"]} for row in rows],
        })
    return result


def human_report(document):
    print(f"WAN quota report — {document['generated_at']}")
    for item in document["providers"]:
        print(f"\n{item['name']} ({item['logical_interface']} → {item['interface']})")
        print(f"  Cycle: {item['start']} through {(dt.date.fromisoformat(item['end']) - dt.timedelta(days=1)).isoformat()}")
        print(f"  Download: {item['rx'] / 1e9:.3f} GB; upload: {item['tx'] / 1e9:.3f} GB")
        print(f"  Used: {item['used'] / 1e9:.3f} / {item['quota'] / 1e9:.3f} GB ({item['percent']:.2f}%)")
        print(f"  Remaining: {item['remaining'] / 1e9:.3f} GB; projected: {item['projected'] / 1e9:.3f} GB")
        if item["error"]:
            print(f"  ERROR: {item['error']}")


def main():
    enabled, providers = configuration()
    mode = next((arg for arg in sys.argv[1:] if arg in {"summary", "daily", "monthly", "monitor"}), "summary")
    if mode == "summary":
        document = summary(enabled, providers)
    elif mode == "monitor":
        document = monitor(enabled, providers)
    else:
        document = history(enabled, providers, mode)
    if "--json" in sys.argv or mode != "summary":
        print(json.dumps(document, separators=(",", ":")))
    else:
        human_report(document)


if __name__ == "__main__":
    main()
