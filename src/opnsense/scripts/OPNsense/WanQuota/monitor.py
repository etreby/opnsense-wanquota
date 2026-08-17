#!/usr/local/bin/python3
"""Run periodic DNS collection and deduplicated quota-alert evaluation."""

import json

import addresses
import consumers
import intelligence
import report
import shaper


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
    # Keep the service address book current on the same schedule as DNS collection:
    # a limit is only as good as the addresses behind it, and waiting for a device
    # to resolve a service by chance is what made some services uncappable.
    try:
        result["addresses"] = addresses.refresh(shaper.STREAMING_SERVICES, shaper.load_mappings())
    except Exception as error:
        result["addresses"] = {"status": "failed", "error": str(error)}
        result["status"] = "degraded"
    # Refreshing the address book is not enough on its own: the running rule matches a
    # snapshot of addresses taken when the plan was applied. Measured on a live
    # network, a 720p YouTube stream ran untouched past a 0.5 Mbit cap because it used
    # a cache node learned after the last apply — the cap was correct and simply did
    # not contain the address. Re-applying when, and only when, the shaped set has
    # changed keeps a service cap tracking its CDN instead of decaying.
    try:
        result["shaper"] = shaper.sync()
    except Exception as error:
        result["shaper"] = {"status": "failed", "error": str(error)}
        result["status"] = "degraded"
    try:
        result["intelligence"] = intelligence.snapshot()
    except Exception as error:
        result["intelligence"] = {"status": "failed", "error": str(error)}
        result["status"] = "degraded"
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
