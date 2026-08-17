#!/usr/local/bin/python3
"""Per-device budget enforcement.

The gateway guardrails act on a whole provider. This acts on individual devices
that have exceeded a configured budget, by maintaining a pf table that a firewall
rule blocks.

Safety is the design, not a setting:

  * Disabled by default, and dry-run by default when enabled. Dry run writes the
    membership it *would* apply and touches nothing.
  * The router is never a member. Neither is any device marked excluded, nor any
    device in a group named as protected infrastructure. A budget cannot lock the
    firewall out of its own network or take down the things the network needs.
  * Membership is derived fresh every run and applied with a single atomic
    replace, so the table always reflects current state and clearing a budget
    releases the device on the next run.
  * flush() empties the table, which is the whole rollback.

Deciding membership is a pure function so it can be tested without pf.
"""

import ipaddress
import json
import os
import subprocess
import sys

import consumers
import intelligence
import report

TABLE = "wanquota_over_budget"
STATE_DIR = "/var/db/wanquota"
PLAN_PATH = os.path.join(STATE_DIR, "device-enforcement-plan.json")
PFCTL = "/sbin/pfctl"

# Groups whose members are never blocked, however far over budget they are.
PROTECTED_GROUPS = {"Protected Infrastructure", "INFRASTRUCTURE_DEVICES"}


def over_budget(hosts, policies, groups, router, protected_groups=PROTECTED_GROUPS):
    """Addresses that exceed their budget and are safe to act on.

    Returns (members, skipped) where skipped explains every exclusion, so a
    dry-run plan can be read without guessing why a device is absent.
    """
    members = []
    skipped = []
    for host in hosts:
        address = host.get("ip")
        if not address:
            continue
        if address == router:
            skipped.append({"device": address, "reason": "router"})
            continue
        policy = intelligence.policy_for(host, policies)
        if policy.get("exclude"):
            skipped.append({"device": address, "reason": "excluded by policy"})
            continue
        group = intelligence.group_for(address, groups)
        if group in protected_groups:
            skipped.append({"device": address, "reason": f"protected group: {group}"})
            continue
        budget = float(policy.get("budget_gb", 0) or 0) * 1e9
        if budget <= 0:
            continue
        total = float(host.get("total") or 0)
        if total <= budget:
            continue
        try:
            ipaddress.ip_address(address)
        except ValueError:
            skipped.append({"device": address, "reason": "not a literal address"})
            continue
        members.append({
            "device": address,
            "name": host.get("name", address),
            "mac": host.get("mac", ""),
            "total": total,
            "budget": budget,
            "over_by": total - budget,
        })
    return members, skipped


def apply_table(addresses, runner=None):
    """Replace the pf table contents atomically.

    pfctl reports what it did on stderr even when it succeeds ("1 addresses
    added.", "no changes."), so stderr is only treated as an error when the exit
    status says so. Passing it through unconditionally put a success message in
    the plan file's error field, which reads as a failure that did not happen.
    """
    run = runner or (lambda args: subprocess.run(args, capture_output=True, text=True, timeout=30))
    args = [PFCTL, "-t", TABLE, "-T", "replace"] + list(addresses)
    result = run(args)
    ok = getattr(result, "returncode", 1) == 0
    message = (getattr(result, "stderr", "") or "").strip()
    return ok, ("" if ok else message), message


def flush(runner=None):
    """Empty the table. This is the rollback."""
    return apply_table([], runner=runner)


def write_plan(document):
    os.makedirs(STATE_DIR, mode=0o750, exist_ok=True)
    with open(PLAN_PATH, "w", encoding="utf-8") as handle:
        json.dump(document, handle, separators=(",", ":"))


def run(period="month"):
    cfg = intelligence.options()
    enabled = cfg.get("device_enforcement", False)
    dry_run = cfg.get("device_dry_run", True)
    settings, _ = consumers.settings_and_names()
    if not enabled:
        # Nothing configured to act, so make sure nothing is left acting.
        applied, error, detail = flush()
        document = {
            "status": "disabled", "members": [], "skipped": [],
            "table": TABLE, "flushed": applied,
            "error": error or None, "pfctl": detail or None,
        }
        write_plan(document)
        return document

    consumer = consumers.report(period)
    policies = intelligence.policy_index(cfg["devices"])
    members, skipped = over_budget(
        consumer.get("hosts", []), policies, cfg["groups"], settings["router"]
    )
    addresses = [item["device"] for item in members]
    document = {
        "status": "ok",
        "period": period,
        "dry_run": dry_run,
        "table": TABLE,
        "members": members,
        "skipped": skipped,
    }
    if dry_run:
        document["note"] = (
            "Dry run: this is the membership that would be applied. No pf table was "
            "changed. Disable dry-run to enforce."
        )
    else:
        applied, error, detail = apply_table(addresses)
        document["applied"] = applied
        document["error"] = error or None
        document["pfctl"] = detail or None
    write_plan(document)
    return document


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    if mode == "flush":
        applied, error, detail = flush()
        print(json.dumps({"status": "ok" if applied else "failed", "flushed": applied,
                          "error": error or None, "pfctl": detail or None},
                         separators=(",", ":")))
        return
    period = sys.argv[2] if len(sys.argv) > 2 else "month"
    print(json.dumps(run(period), separators=(",", ":")))


if __name__ == "__main__":
    main()
