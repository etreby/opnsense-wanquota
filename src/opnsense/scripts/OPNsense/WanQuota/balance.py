#!/usr/local/bin/python3
"""Send more traffic over whichever provider's allowance expires soonest.

The guardrails answer "this link is running out". Nothing answered the opposite
question, which on a household with two providers on different billing days is the
more common waste: "this link's allowance is about to expire unspent".

The arithmetic, with the numbers that motivated it. Two providers, one household:
ETISALAT 225 GB renewing on day 1, MOBINIL 400 GB renewing on day 15. On the 29th
ETISALAT has 2 days left and 60 GB unused — 30 GB/day to spend it — while MOBINIL
has 16 days and 250 GB, or 15.6 GB/day. ETISALAT's allowance is twice as urgent,
and every gigabyte the household sends over MOBINIL instead is a gigabyte ETISALAT
will never get back. So the quantity to equalise is headroom per remaining day:

    urgency = max(0, remaining - reserve) / max(1, days_left)

`remaining` and `days_left` already come from report.provider_summary(), computed
against each provider's own cycle day, so this needs no new measurement. `reserve`
is the existing emergency reserve, held back so the balancer never spends the
buffer the guardrails depend on.

Three decisions that keep this from becoming dangerous:

  * **Weights, never tiers.** A tier move is failover: the lower tier idles until
    the upper one fails, which is exactly the waste this exists to end. Tiers and
    force_down stay the guardrails' levers, and the balancer only ever changes the
    integer weight of a gateway inside its group.

  * **A floor of 1.** Not a rounding artefact — policy. The balancer shifts the
    ratio and must never starve a link. Taking a link out of service is the
    guardrail's decision, and writing a weight of zero would be the balancer
    reaching for it.

  * **Overuse beats underuse.** A provider the guardrail has failed over or cut off
    is excluded from the balance and left at weight 1. A link nearly out of
    allowance must not be sent more traffic because its allowance expires soon;
    those two facts point the same way only by coincidence.

Computing the plan is pure so it can be tested. Writing weights is a PHP shim,
because gateways live in the OPNsense Gateways model and the model is what
validates and reloads them safely.
"""

import datetime as dt
import json
import os
import subprocess
import sys
import time

import intelligence
import report

STATE_DIR = "/var/db/wanquota"
PLAN_PATH = os.path.join(STATE_DIR, "balance-plan.json")
SHIM = "/usr/local/opnsense/scripts/OPNsense/WanQuota/balance.php"

# Actions that take a provider out of the balance. The guardrail has decided this
# link should carry less or nothing; sending it more because its cycle renews soon
# would be the two features fighting over the same gateway.
GUARDRAIL_EXCLUSIONS = ("failover", "cutoff")


def urgency(provider, reserve_bytes=0):
    """Bytes per remaining day needed to spend this provider's allowance.

    Higher means more allowance is at risk of expiring unused. A provider with no
    headroom left, or one already past its quota, scores zero: there is nothing to
    save from expiry.
    """
    remaining = max(0.0, float(provider.get("remaining") or 0) - float(reserve_bytes or 0))
    days = max(1, int(provider.get("days_left") or 0))
    return remaining / days


def weights(rows, max_weight=10):
    """Turn urgency into integer gateway weights.

    `rows` are dicts carrying at least `urgency` and `excluded`. Returns the same
    rows with `weight` set, so the caller keeps whatever else it put there.

    When every provider scores zero — everything exhausted, or nothing measured yet
    — all weights go to 1 and the group is back to equal sharing. That is better
    than declining to answer, which would leave whatever ratio the last run wrote.
    """
    ceiling = max(2, min(10, int(max_weight or 10)))
    eligible = [row for row in rows if not row.get("excluded")]
    peak = max((float(row.get("urgency") or 0) for row in eligible), default=0.0)
    for row in rows:
        if row.get("excluded") or peak <= 0:
            row["weight"] = 1
        else:
            share = float(row.get("urgency") or 0) / peak
            row["weight"] = max(1, min(ceiling, int(round(share * ceiling))))
    return rows


def gateway_for(interface, gateways, protocol="inet"):
    """The gateway carrying a provider's logical interface.

    Matched on interface and protocol, never on the gateway's name. Naming a
    gateway after its provider is a habit, not a guarantee, and a rename would
    silently point the balancer at the wrong link.
    """
    for gateway in gateways or []:
        if str(gateway.get("interface") or "") != interface:
            continue
        if str(gateway.get("ipprotocol") or "inet") != protocol:
            continue
        if str(gateway.get("disabled") or "0") == "1":
            continue
        return gateway
    return None


def discover(runner=None):
    """Gateways and groups as the firewall itself sees them, dynamic ones included."""
    run = runner or (lambda args: subprocess.run(args, capture_output=True, text=True, timeout=60))
    if not os.path.isfile(SHIM):
        return {"gateways": [], "groups": [], "error": "balance.php is not installed"}
    try:
        result = run(["/usr/local/bin/php", SHIM, "inventory"])
        return json.loads(result.stdout or "{}")
    except Exception as error:
        return {"gateways": [], "groups": [], "error": str(error)}


def build(providers, cfg, inventory, decisions=None):
    """The whole plan: what each provider scores, and the weight it should carry."""
    reserve = float(cfg.get("reserve_gb", 0) or 0) * 1e9
    decisions = decisions or {}
    gateways = inventory.get("gateways") or []
    groups = inventory.get("groups") or []
    wanted = str(cfg.get("balance_group") or "").strip()
    group = None
    if wanted:
        group = next((item for item in groups if item.get("name") == wanted), None)
    elif len(groups) == 1:
        group = groups[0]

    rows = []
    for provider in providers:
        if not provider.get("available", True):
            continue
        applied = str(decisions.get(provider["name"], {}).get("applied") or "none")
        recommended = str(decisions.get(provider["name"], {}).get("recommended") or "observe")
        excluded = applied in GUARDRAIL_EXCLUSIONS
        gateway = gateway_for(provider["logical_interface"], gateways)
        rows.append({
            "name": provider["name"],
            "logical_interface": provider["logical_interface"],
            "remaining": provider.get("remaining", 0),
            "days_left": provider.get("days_left", 0),
            "cycle_end": provider.get("end"),
            "percent": provider.get("percent", 0),
            "urgency": urgency(provider, reserve),
            "excluded": excluded,
            "excluded_reason": (
                f"the guardrail has applied {applied}; overuse takes precedence over underuse"
                if excluded else ""),
            "guardrail": recommended,
            "gateway": (gateway or {}).get("name", ""),
            "gateway_exists": bool(gateway and gateway.get("configured")),
            "current_weight": int((gateway or {}).get("weight") or 1),
            "in_group": bool(gateway and group
                             and (gateway.get("name") in (group.get("members") or []))),
        })
    weights(rows, cfg.get("balance_max_weight", 10))

    problems = []
    if not groups:
        problems.append("no gateway group is configured, so there is nothing to balance")
    elif group is None:
        names = ", ".join(item.get("name", "?") for item in groups)
        problems.append(
            f"more than one gateway group exists ({names}); name the one to balance in "
            "the balance settings")
    for row in rows:
        if not row["gateway"]:
            problems.append(
                f"{row['name']}: no gateway uses {row['logical_interface']}, so its share "
                "cannot be written")
        elif group is not None and not row["in_group"]:
            problems.append(
                f"{row['name']}: {row['gateway']} is not a member of "
                f"{group.get('name')}, so its weight does not affect the balance")
    changes = [row for row in rows
               if row["gateway"] and row["weight"] != row["current_weight"]]
    return {
        "group": (group or {}).get("name", ""),
        "group_members": (group or {}).get("members", []),
        "providers": rows,
        "changes": [{"gateway": row["gateway"], "name": row["name"],
                     "from": row["current_weight"], "to": row["weight"]}
                    for row in changes],
        "problems": problems,
        "reserve_gb": cfg.get("reserve_gb", 0),
        "max_weight": max(2, min(10, int(cfg.get("balance_max_weight", 10) or 10))),
        "note": (
            "Weight is the share of new connections a gateway receives inside its group. "
            "The provider whose remaining allowance is largest per day left before renewal "
            "gets the highest weight, so allowance is spent rather than lost. Tiers and "
            "force_down are never touched: taking a link out of service stays the "
            "guardrails' decision."
        ),
    }


def write_plan(document):
    os.makedirs(STATE_DIR, mode=0o750, exist_ok=True)
    with open(PLAN_PATH, "w", encoding="utf-8") as handle:
        json.dump(document, handle, separators=(",", ":"))


def read_plan():
    try:
        with open(PLAN_PATH, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {"status": "unknown", "providers": [], "changes": [],
                "note": "No balance plan has been written yet."}


def decisions_for(providers, cfg):
    """The guardrail's current position on each provider, keyed by name."""
    result = {}
    for provider in providers:
        try:
            result[provider["name"]] = intelligence.policy_decision(provider, cfg)
        except Exception:
            result[provider["name"]] = {"applied": "none", "recommended": "observe"}
    return result


def apply_now(runner=None):
    """Hand the plan to the shim. A no-op when no weight actually moved."""
    run = runner or (lambda args: subprocess.run(args, capture_output=True, text=True, timeout=120))
    if not os.path.isfile(SHIM):
        return {"status": "failed", "error": "balance.php is not installed"}
    try:
        result = run(["/usr/local/bin/php", SHIM, "apply"])
        return json.loads(result.stdout or "{}")
    except Exception as error:
        return {"status": "failed", "error": str(error)}


def run(force=False):
    """Compute the plan, and act on it when configuration allows.

    Always writes the plan, even when disabled, so the interface can show what the
    balance *would* be without the user having to switch anything on first.
    """
    cfg = intelligence.options()
    enabled, providers = report.configuration()
    today = dt.date.today()
    summaries = [report.provider_summary(provider, today) for provider in providers]
    document = build(summaries, cfg, discover(), decisions_for(summaries, cfg))
    document["enabled"] = cfg.get("balance", False)
    document["dry_run"] = cfg.get("balance_dry_run", True)
    document["updated"] = int(time.time())
    permitted = force or (cfg.get("balance", False) and not cfg.get("balance_dry_run", True))
    if not enabled:
        document["status"] = "disabled"
        document["state"] = "plugin_off"
    elif document["problems"]:
        # A plan that cannot be written is reported rather than half-applied. Writing
        # the weights that happen to be resolvable would leave a ratio nobody chose.
        document["status"] = "blocked"
        document["state"] = "blocked"
    elif not permitted:
        document["status"] = "ok"
        document["state"] = ("off" if not cfg.get("balance", False) else "dry_run")
    elif not document["changes"]:
        # Integer weights compared before anything is written: this is the hysteresis.
        # Without it a five-minute cron would rewrite the configuration 288 times a
        # day and reload the firewall each time, for a ratio that had not moved.
        document["status"] = "ok"
        document["state"] = "live"
        document["applied"] = {"status": "ok", "changed": 0,
                               "note": "Weights already match the plan."}
    else:
        document["status"] = "ok"
        document["state"] = "live"
        document["applied"] = apply_now()
    write_plan(document)
    return document


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if mode == "state":
        print(json.dumps(read_plan(), separators=(",", ":")))
        return
    if mode == "apply":
        print(json.dumps(run(force=True), separators=(",", ":")))
        return
    if mode == "revert":
        result = subprocess.run(["/usr/local/bin/php", SHIM, "revert"],
                                capture_output=True, text=True, timeout=120)
        print(result.stdout.strip() or json.dumps({"status": "failed",
                                                   "error": result.stderr.strip()}))
        return
    print(json.dumps(run(), separators=(",", ":")))


if __name__ == "__main__":
    main()
