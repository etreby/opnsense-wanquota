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

Two instruments, and a rule for choosing between them.

  * **Weights** share traffic between links that are both carrying. This is the
    default and the safe one: it cannot idle a link.

  * **Drain** makes one link carry everything and demotes the rest to failover. It
    exists because weights cannot always avoid waste. If a provider's remaining
    allowance per day left exceeds what the whole household consumes in a day, then
    even giving it *all* the traffic will not exhaust it before its cycle renews —
    and giving it merely a share guarantees gigabytes expire unused. At that point
    sharing is the thing doing the damage.

    So drain engages exactly when `urgency >= household daily rate`, and releases
    on its own when that stops being true — which happens automatically at cycle
    renewal, when the allowance resets and the per-day figure collapses. There is no
    threshold to tune and no schedule to remember.

Three decisions that keep this from becoming dangerous:

  * **Tiers only in drain mode, and never force_down.** Weights mode does not touch
    tiers at all. Drain mode moves them deliberately, but still never touches
    force_down: taking a link *out of service* remains the guardrails' decision,
    while drain only decides which link is preferred. A demoted link stays a live
    failover and takes over within seconds if the primary drops — measured.

  * **A floor of 1.** Not a rounding artefact — policy. The balancer shifts the
    ratio and must never starve a link. Taking a link out of service is the
    guardrail's decision, and writing a weight of zero would be the balancer
    reaching for it.

  * **Overuse beats underuse.** A provider the guardrail has failed over or cut off
    is excluded from the balance and left at weight 1. A link nearly out of
    allowance must not be sent more traffic because its allowance expires soon;
    those two facts point the same way only by coincidence. While the guardrail is
    acting on any provider, drain stands down entirely rather than fighting it over
    the same tiers.

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


def household_rate(providers):
    """Bytes per day the household actually consumes, across every provider.

    The sum rather than any single link's figure: traffic moved to another provider
    is the same traffic, so what a link *could* absorb has to be compared against
    total demand, not against demand it already sees.
    """
    return sum(max(0.0, float(item.get("daily_average") or 0)) for item in providers)


# Drain releases a little below the level at which it engages. Without the band a
# provider sitting exactly at the household rate would engage and release on
# alternating runs, rewriting the gateway group every five minutes.
DRAIN_RELEASE_BAND = 0.9


def drain_decision(rows, demand, draining=False, band=DRAIN_RELEASE_BAND,
                   ceiling_percent=None):
    """Which provider, if any, should carry everything.

    Engages when the most urgent link could absorb the household's whole daily
    demand and still not spend its allowance before renewal — the case where
    sharing guarantees waste. Returns the decision and the reason for it, because a
    tier change nobody asked for needs to be able to explain itself.

    `ceiling_percent` is the floor guard, and it is deliberately not rate arithmetic.
    The engage condition already implies the allowance cannot run out — carrying all
    the traffic for the days left costs less than what remains — but that argument
    rests entirely on `demand`, which is a *lagging average* of measured days. A
    household that suddenly doubles its usage is not visible in that average for a
    day, and drain would keep concentrating onto a link heading for its cap. So there
    is a second condition that does not depend on the rate at all: a provider past
    this share of its quota is never a drain target. Reusing the guardrail's failover
    threshold means concentration stops at the same point the guardrails would have
    moved traffic off the link anyway.
    """
    eligible = [row for row in rows
                if not row.get("excluded") and row.get("gateway") and row.get("online", True)]
    full = []
    if ceiling_percent is not None:
        full = [row for row in eligible
                if float(row.get("percent") or 0) >= float(ceiling_percent)]
        eligible = [row for row in eligible if row not in full]
    if any(row.get("excluded") for row in rows):
        blocked = ", ".join(row["name"] for row in rows if row.get("excluded"))
        return {"engaged": False, "target": None,
                "reason": f"the guardrail is acting on {blocked}, and it owns the tiers "
                          "while it does"}
    if len(eligible) < 2:
        if full:
            names = ", ".join(f"{row['name']} at {float(row.get('percent') or 0):.0f}%"
                              for row in full)
            return {"engaged": False, "target": None,
                    "reason": (
                        f"{names} — past the point where concentrating more traffic onto "
                        "it would risk its cap, so it is not a drain target however much "
                        "allowance is left to spend")}
        return {"engaged": False, "target": None,
                "reason": "fewer than two usable providers, so there is nothing to "
                          "concentrate"}
    if demand <= 0:
        return {"engaged": False, "target": None,
                "reason": "no measured household traffic yet, so there is no demand to "
                          "compare an allowance against"}
    top = max(eligible, key=lambda row: float(row.get("urgency") or 0))
    urgency = float(top.get("urgency") or 0)
    threshold = demand * (band if draining else 1.0)
    if urgency < threshold:
        return {
            "engaged": False, "target": None,
            "demand": demand, "threshold": threshold,
            "reason": (
                f"{top['name']} can spend {urgency / 1e9:.1f} GB/day and the household "
                f"uses {demand / 1e9:.1f} GB/day, so a share of the traffic is enough to "
                "fill it and both links stay in service"),
        }
    return {
        "engaged": True, "target": top["name"],
        "demand": demand, "threshold": threshold,
        "reason": (
            f"{top['name']} has {urgency / 1e9:.1f} GB/day of allowance left to spend and "
            f"the whole household only uses {demand / 1e9:.1f} GB/day — even all of the "
            "traffic will not exhaust it before renewal, so sharing would waste the "
            "difference"),
    }


def tier_plan(rows, decision, group):
    """The tier each gateway should sit in, and whether that differs from now.

    Only ever two tiers: the drained provider alone in the first, everything else in
    the second as live failover. Restoring means putting each gateway back in the
    tier the group had it in before drain first engaged.
    """
    members = (group or {}).get("members") or []
    tiers = (group or {}).get("tiers") or {}
    current = {}
    for tier, names in tiers.items():
        for name in names:
            current[name] = tier
    wanted = {}
    if decision.get("engaged"):
        for row in rows:
            gateway = row.get("gateway")
            if not gateway or gateway not in members:
                continue
            wanted[gateway] = "item" if row["name"] == decision["target"] else "item2"
    moves = [{"gateway": name, "from": current.get(name, "item"), "to": tier}
             for name, tier in sorted(wanted.items())
             if current.get(name, "item") != tier]
    return {"wanted": wanted, "current": current, "moves": moves}


# Tier names in priority order. pf builds its pool from the highest non-empty tier
# and ignores the rest, which is why a weight in a lower tier has no effect at all.
TIER_ORDER = ("item", "item2", "item3", "item4", "item5")


def shares(rows, tiers):
    """Percentage of new connections each provider should actually receive.

    Computed from the tier layout and the weights together, because that is how pf
    builds the pool: only the highest non-empty tier contributes entries, and within
    it a gateway's weight *is* its number of entries. A weight in a lower tier is
    not a small share, it is no share — which is the thing raw weights hide. Reading
    "weight 6" beside a link carrying nothing is a fair way to be misled, so the
    percentage is derived here rather than left to the interface to guess at.

    Sets `share_percent` and `weight_in_effect` on each row and returns them.
    """
    layout = dict((tiers or {}).get("wanted") or (tiers or {}).get("current") or {})
    active = []
    if layout:
        for tier in TIER_ORDER:
            named = [gateway for gateway, where in layout.items() if where == tier]
            if named:
                active = named
                break
    for row in rows:
        gateway = row.get("gateway")
        # With no layout known at all, every provider that has a gateway shares —
        # the group has one tier and the weights are what split it.
        row["weight_in_effect"] = bool(gateway) and (not active or gateway in active)
    carrying = [row for row in rows if row.get("weight_in_effect")]
    total = sum(max(1, int(row.get("weight") or 1)) for row in carrying)
    for row in rows:
        if row.get("weight_in_effect") and total > 0:
            row["share_percent"] = max(1, int(row.get("weight") or 1)) / total * 100
        else:
            row["share_percent"] = 0.0
    return rows


def release_needed(decision, inventory):
    """True when a drain is in force and the condition for it no longer holds.

    Releasing has to *undo* a tier change, not merely stop proposing one. Without
    this, a drain that engaged before a cycle renewal stayed engaged after it: the
    decision correctly flipped to disengaged, the plan proposed no moves, and the
    group remained concentrated on one link indefinitely. Seen on a live firewall by
    simulating the renewal rather than waiting a week for it.
    """
    return bool(inventory.get("drained")) and not decision.get("engaged")


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
            # Drain must never promote a link that is down: it would concentrate
            # everything onto a gateway that cannot carry it. Absent status reads as
            # up, so a firewall that cannot report gateway health behaves as before.
            "online": str((gateway or {}).get("status") or "online").lower()
                      not in ("down", "force_down"),
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

    # Drain is opt-in. In weights mode the tier plan is computed and reported anyway,
    # so the interface can show what concentrating would do before anyone allows it.
    demand = household_rate(providers)
    draining_now = bool(group and len(
        [name for name in ((group.get("tiers") or {}).get("item") or [])]) == 1
        and len(group.get("members") or []) > 1)
    # The floor guard reuses the guardrail's failover threshold rather than adding a
    # setting: the point at which the guardrails would move traffic off a link is the
    # same point at which drain should stop piling more onto it.
    thresholds = sorted(set(cfg.get("thresholds") or []))
    ceiling = thresholds[2] if len(thresholds) >= 4 else 90
    decision = drain_decision(rows, demand, draining=draining_now,
                              ceiling_percent=ceiling)
    plan = tier_plan(rows, decision, group)
    plan["release"] = release_needed(decision, inventory)
    mode = str(cfg.get("balance_mode") or "weights")
    shares(rows, plan)
    if mode != "drain":
        decision = {**decision, "engaged": False, "target": None, "allowed": False,
                    "reason": decision["reason"] + " (drain mode is off, so tiers are "
                                                   "not touched either way)"}
        # Leaving drain mode is itself a reason to release: the tiers it moved must
        # not be left behind by turning the mode off.
        plan = {"wanted": {}, "current": plan["current"], "moves": [],
                "release": bool(inventory.get("drained"))}
        # Recompute against the layout that will actually be in force once the
        # release lands, not the drained one the discarded plan described.
        shares(rows, {"current": {} if plan["release"] else plan["current"]})
    else:
        decision["allowed"] = True

    return {
        "group": (group or {}).get("name", ""),
        "group_members": (group or {}).get("members", []),
        "providers": rows,
        "changes": [{"gateway": row["gateway"], "name": row["name"],
                     "from": row["current_weight"], "to": row["weight"]}
                    for row in changes],
        "problems": problems,
        "mode": mode,
        "demand": demand,
        "drain_ceiling_percent": ceiling,
        "drain": decision,
        "tiers": plan,
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


def apply_now(runner=None, mode="apply"):
    """Hand the plan to the shim. A no-op when nothing actually moved."""
    run = runner or (lambda args: subprocess.run(args, capture_output=True, text=True, timeout=120))
    if not os.path.isfile(SHIM):
        return {"status": "failed", "error": "balance.php is not installed"}
    try:
        result = run(["/usr/local/bin/php", SHIM, mode])
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
    else:
        document["status"] = "ok"
        document["state"] = "live"
        # Integer weights and tier names are both compared before anything is written:
        # this is the hysteresis. Without it a five-minute cron would rewrite the
        # configuration 288 times a day and reload the firewall each time, for a ratio
        # that had not moved.
        tier_moves = (document.get("tiers") or {}).get("moves") or []
        release = bool((document.get("tiers") or {}).get("release"))
        if not document["changes"] and not tier_moves and not release:
            document["applied"] = {"status": "ok", "changed": 0,
                                   "note": "Weights and tiers already match the plan."}
        else:
            # The plan is written BEFORE applying, and this ordering is the whole
            # correctness of the apply path: balance.php reads the plan from disk, so
            # writing it afterwards had the shim act on the *previous* run's plan. It
            # looked like it worked, because consecutive runs usually compute the same
            # answer and the stale plan happened to say the same thing — until the
            # answer changed, and then the first run after the change applied nothing
            # and reported "already match". Measured on a live firewall: a tier move
            # was computed, reported as applied, and the tiers did not move.
            write_plan(document)
            document["applied"] = apply_now()
            # Tiers are a separate write so a weight failure cannot leave tiers half
            # applied, and so the reasons appear separately in the plan.
            if tier_moves:
                document["applied_tiers"] = apply_now(mode="tiers")
            elif release:
                document["released_tiers"] = apply_now(mode="tierrelease")
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
