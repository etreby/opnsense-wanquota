#!/usr/local/bin/python3
"""Take a device off the internet, now, while leaving it on the LAN.

This is the blunt instrument next to the shaper's rate cap and the budget
enforcer's threshold: someone has decided this device should not reach the
internet, and the plugin's job is to make that true and to make undoing it one
click.

What "blocked from the internet" means precisely. The rule setup.php installs is
`block in on <LAN> from <wanquota_blocked> to !<LAN net>`, first in the LAN rule
list. So internet access stops; LAN-to-LAN traffic is untouched, because the
destination is excluded and most of it is switched and never reaches the firewall
anyway; and DNS and NTP served by the firewall keep working, because the firewall's
own address is inside the LAN network — a blocked device should not also lose its
clock and its resolver.

Two placements were rejected, one of them after measuring it fail. An outbound rule
on the WAN interface cannot work at all: outbound WAN rules see the post-NAT source,
so a rule naming an internal address never matches. Appending the LAN rule instead of
putting it first looked fine and was not: OPNsense emits administrator pass rules as
pf `quick` rules, so a broad `pass ... from <MY_DEVICES> to any` earlier in the list
matched first and the block showed `Evaluations: 0` while the blocked device browsed
normally.

Three design decisions worth stating, because each one is a place a reasonable
person would have chosen otherwise:

  * **Its own pf table**, not the budget enforcer's. devices.py replaces
    `wanquota_over_budget` wholesale on every run, so a manual block filed there
    would be erased within five minutes, and a dry-run budget setting would
    silently make manual blocks advisory when they were never meant to be.

  * **No dry-run.** Budget enforcement is dry-run by default because it acts on a
    prediction the user has not yet learned to trust. A block is not a prediction.
    Someone who asked for it has already decided, and a dry-run that recorded the
    intent without blocking would be a feature that lies.

  * **The same three refusals as the budget path.** The firewall itself is never
    blocked, a device marked excluded is never blocked, and a member of a protected
    infrastructure group is never blocked. A block that could lock the firewall out
    of its own network, or take down the things the network needs, is not a feature.

Deciding membership is a pure function so it can be tested without pf, a config, or
a firewall.
"""

import ipaddress
import json
import os
import subprocess
import sys
import time

import consumers
import devices as budget
import intelligence
import shaper

TABLE = "wanquota_blocked"
STATE_DIR = "/var/db/wanquota"
PLAN_PATH = os.path.join(STATE_DIR, "block-plan.json")
PFCTL = "/sbin/pfctl"


def entries(config_path=None):
    """The configured blocks, as a list, whatever the field actually holds."""
    saved = intelligence.CONFIG_PATH
    if config_path:
        intelligence.CONFIG_PATH = config_path
    try:
        import xml.etree.ElementTree as ET
        root = ET.parse(intelligence.CONFIG_PATH).getroot()
        general = root.find("./OPNsense/WanQuota/general")
        raw = intelligence.value(general, "device_blocks_json", "[]")
    except (OSError, ValueError):
        return []
    finally:
        intelligence.CONFIG_PATH = saved
    try:
        parsed = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def members(blocks, known, policies, groups, router, now=None,
            protected_groups=budget.PROTECTED_GROUPS):
    """Addresses to block, and why every other entry was not blocked.

    Returns (members, skipped, expired). `expired` is separate from `skipped`
    because an expired block is a block that did its job, not one that was
    refused, and the caller removes those from the configuration rather than
    reporting them as problems.
    """
    now = int(time.time()) if now is None else int(now)
    chosen = []
    skipped = []
    expired = []
    seen = {}
    for block in blocks or []:
        key = str(block.get("device") or "").strip()
        if not key:
            skipped.append({"device": "(unnamed)", "reason": "no device given"})
            continue
        try:
            until = int(block.get("until") or 0)
        except (TypeError, ValueError):
            skipped.append({"device": key, "reason": "until must be a Unix timestamp"})
            continue
        if until and until <= now:
            expired.append({"device": key, "until": until,
                            "reason": "the block deadline has passed"})
            continue
        # The firewall is refused before anything is looked up, not after. It does not
        # appear in the device list — that list is built from DHCP leases and ARP — so
        # a check that ran only on a matched row refused the firewall with "no device
        # matches", which is true and misleading: it reads like a typo rather than a
        # guarantee. The guarantee must not depend on the firewall happening to be in
        # a list produced somewhere else.
        if router and key.lower() == str(router).lower():
            skipped.append({"device": key, "reason": "refused: this is the firewall itself"})
            continue
        row = shaper.match_device(block, known)
        if row is None:
            skipped.append({
                "device": key,
                "reason": "no device on the network matches that address, MAC or hostname",
            })
            continue
        address = row["address"]
        if router and address == router:
            skipped.append({"device": key, "reason": "refused: this is the firewall itself"})
            continue
        # policy_for expects a consumers-shaped host, whose address field is "ip".
        policy = intelligence.policy_for(
            {"ip": address, "mac": row.get("mac", ""), "hostname": row.get("hostname", "")},
            policies)
        if policy.get("exclude"):
            skipped.append({"device": key, "reason": "excluded by policy"})
            continue
        group = intelligence.group_for(address, groups)
        if group in protected_groups:
            skipped.append({"device": key, "reason": f"protected group: {group}"})
            continue
        try:
            ipaddress.ip_address(address)
        except ValueError:
            skipped.append({"device": key, "reason": "not a literal address"})
            continue
        # Two entries can name one device by different identifiers. Blocking it twice
        # is harmless in pf, but reporting it twice makes the interface disagree with
        # itself about how many devices are blocked.
        if address in seen:
            skipped.append({
                "device": key,
                "reason": f"already blocked by the entry for {seen[address]!r}",
            })
            continue
        seen[address] = key
        chosen.append({
            "device": address,
            "name": row.get("name") or address,
            "mac": row.get("mac", ""),
            "matched": key,
            "until": until,
            "reason": str(block.get("reason") or ""),
        })
    return chosen, skipped, expired


def apply_table(addresses, runner=None):
    """Replace the table contents atomically.

    Shares devices.py's reading of pfctl: it reports what it did on stderr even on
    success ("1 addresses added.", "no changes."), so stderr is only an error when
    the exit status says so.
    """
    run = runner or (lambda args: subprocess.run(args, capture_output=True, text=True, timeout=30))
    result = run([PFCTL, "-t", TABLE, "-T", "replace"] + list(addresses))
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


def read_plan():
    try:
        with open(PLAN_PATH, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {"status": "unknown", "members": [], "skipped": [],
                "note": "No block plan has been written yet."}


def prune(expired, config_path=None):
    """Drop entries whose deadline has passed from the configuration itself.

    Leaving them behind would mean the interface listing blocks that are not in
    force, and a device that was temporarily blocked would carry a stale entry for
    as long as the plugin is installed. Handled by the PHP shim, because writing
    /conf/config.xml belongs to the model, not to a Python script parsing XML.
    """
    if not expired:
        return {"removed": 0}
    keys = [item["device"] for item in expired]
    script = "/usr/local/opnsense/scripts/OPNsense/WanQuota/blocks.php"
    if not os.path.isfile(script):
        return {"removed": 0, "error": "blocks.php is not installed"}
    try:
        result = subprocess.run(["/usr/local/bin/php", script, "expire"] + keys,
                                capture_output=True, text=True, timeout=60)
        return json.loads(result.stdout or "{}")
    except Exception as error:
        return {"removed": 0, "error": str(error)}


def run(config_path=None):
    cfg = intelligence.options()
    settings, _ = consumers.settings_and_names()
    blocks = entries(config_path)
    chosen, skipped, expired = members(
        blocks, shaper.device_identities(), intelligence.policy_index(cfg["devices"]),
        cfg["groups"], settings["router"])
    applied, error, detail = apply_table([item["device"] for item in chosen])
    document = {
        "status": "ok" if applied else "failed",
        "table": TABLE,
        "members": chosen,
        "skipped": skipped,
        "expired": expired,
        "applied": applied,
        "error": error or None,
        "pfctl": detail or None,
        "updated": int(time.time()),
        "note": (
            "A block stops internet access and leaves LAN traffic alone. DNS and NTP "
            "served by the firewall keep working, so a blocked device is not left with "
            "a broken clock as well."
        ),
    }
    if expired:
        document["pruned"] = prune(expired, config_path)
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
    if mode == "state":
        print(json.dumps(read_plan(), separators=(",", ":")))
        return
    print(json.dumps(run(), separators=(",", ":")))


if __name__ == "__main__":
    main()
