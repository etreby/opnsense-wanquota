#!/usr/local/bin/python3
"""Run periodic DNS collection and deduplicated quota-alert evaluation."""

import json

import consumers
import intelligence
import report


def main():
    result = {"status": "ok", "dns": None, "quota": None, "intelligence": None}
    try:
        result["dns"] = consumers.collect_dns()
    except Exception as error:  # keep quota monitoring alive when DNS collection fails
        result["dns"] = {"status": "failed", "error": str(error)}
        result["status"] = "degraded"
    try:
        enabled, providers = report.configuration()
        result["quota"] = report.monitor(enabled, providers)
    except Exception as error:
        result["quota"] = {"status": "failed", "error": str(error)}
        result["status"] = "degraded"
    if result.get("quota", {}).get("alerts", {}).get("events"):
        try:
            intelligence.send_webhook(intelligence.options(), "quota_alerts", result["quota"]["alerts"]["events"])
        except Exception as error:
            result["webhook"] = {"status": "failed", "error": str(error)}
            result["status"] = "degraded"
    try:
        result["intelligence"] = intelligence.snapshot()
    except Exception as error:
        result["intelligence"] = {"status": "failed", "error": str(error)}
        result["status"] = "degraded"
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
