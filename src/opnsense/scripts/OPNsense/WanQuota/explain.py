#!/usr/local/bin/python3
"""Explain a single domain: which service owns it, and how it was classified.

A breakdown shows that a domain moved traffic; it cannot say what the domain is or
why it landed where it did. This answers that, and shows the rule behind every
conclusion so the answer can be checked rather than believed.
"""

import json
import sys

import consumers
import intelligence
import shaper


def explain(domain, period="thirty"):
    payload = consumers.report(period)
    result = intelligence.explain_domain(
        domain,
        payload.get("domains") or [],
        payload.get("device_domains") or [],
        intelligence.options()["categories"],
        None,
        shaper.STREAMING_SERVICES,
        shaper.load_mappings(),
    )
    result["period"] = period
    result["status"] = payload.get("status")
    return result


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"status": "failed", "error": "a domain is required"}))
        return
    period = sys.argv[2] if len(sys.argv) > 2 else "thirty"
    print(json.dumps(explain(sys.argv[1], period), separators=(",", ":")))


if __name__ == "__main__":
    main()
