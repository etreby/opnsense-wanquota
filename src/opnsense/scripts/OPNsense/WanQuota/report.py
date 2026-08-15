#!/usr/local/bin/python3
"""Configurable vnStat billing-cycle reports for the OPNsense WAN Quota plugin."""

import calendar
import datetime as dt
import json
import subprocess
import sys
import xml.etree.ElementTree as ET


CONFIG_PATH = "/conf/config.xml"
DEFAULTS = (
    {"name": "ISP 1", "logical_interface": "wan", "quota_gb": 100, "cycle_day": 1, "warning_percent": 80},
    {"name": "ISP 2", "logical_interface": "opt1", "quota_gb": 100, "cycle_day": 1, "warning_percent": 80},
)


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
        logical = text(settings, f"provider{index}_interface", defaults["logical_interface"])
        physical = text(root, f"./interfaces/{logical}/if", logical)
        providers.append({
            "name": text(settings, f"provider{index}_name", defaults["name"]),
            "logical_interface": logical,
            "interface": physical,
            "quota_gb": bounded_int(text(settings, f"provider{index}_quota_gb", defaults["quota_gb"]), defaults["quota_gb"], 1, 100000),
            "cycle_day": bounded_int(text(settings, f"provider{index}_cycle_day", defaults["cycle_day"]), defaults["cycle_day"], 1, 31),
            "warning_percent": bounded_int(text(settings, f"provider{index}_warning_percent", defaults["warning_percent"]), defaults["warning_percent"], 1, 100),
        })
    return enabled, providers


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
    used = rx + tx
    quota = provider["quota_gb"] * 1_000_000_000
    remaining = max(0, quota - used)
    elapsed = max(1, (today - start).days + 1)
    days_left = max(0, (end - today).days)
    percent = used / quota * 100
    first_seen = min((date for date, _ in relevant), default=None)
    return {
        **provider,
        "quota": quota,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "rx": rx,
        "tx": tx,
        "used": used,
        "remaining": remaining,
        "percent": percent,
        "days_left": days_left,
        "daily_budget": remaining / days_left if days_left else 0,
        "projected": used / elapsed * (end - start).days,
        "first_seen": first_seen.isoformat() if first_seen else None,
        "complete": first_seen == start,
        "warning": percent >= provider["warning_percent"],
        "available": error is None,
        "error": error,
    }


def summary(enabled, providers):
    today = dt.date.today()
    return {
        "status": "ok" if enabled else "disabled",
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
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
    mode = next((arg for arg in sys.argv[1:] if arg in {"summary", "daily", "monthly"}), "summary")
    document = summary(enabled, providers) if mode == "summary" else history(enabled, providers, mode)
    if "--json" in sys.argv or mode != "summary":
        print(json.dumps(document, separators=(",", ":")))
    else:
        human_report(document)


if __name__ == "__main__":
    main()
