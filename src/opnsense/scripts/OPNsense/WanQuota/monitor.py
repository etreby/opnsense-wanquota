#!/usr/local/bin/python3
"""Run periodic DNS collection and deduplicated quota-alert evaluation."""

import json

import consumers
import report


def main():
    result = {"status": "ok", "dns": None, "quota": None}
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
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
