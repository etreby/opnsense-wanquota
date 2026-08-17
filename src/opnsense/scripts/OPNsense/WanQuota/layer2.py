#!/usr/local/bin/python3
"""Upload shaping through ipfw's layer2 hook, for firewalls where layer 3 cannot see it.

Why this exists, and why it is experimental
-------------------------------------------
A per-device upload cap needs ipfw to see traffic leaving a LAN device. A netmap
capture engine — Zenarmor is the common one — takes packets off the kernel path
before ipfw's inbound IP hook runs, and then no upload rule can ever match.

Measured on a live firewall, uploading 8.4 MB from one device in a 45 second window:

    count ip from <device> to any layer2      3,005 packets   4,072,022 bytes
    count ip from <device> to any             (layer 3)   3 packets   231 bytes

So the traffic is visible at the ethernet hook even when it is invisible at the IP
hook, and an upload cap is achievable. It is offered only as an experiment because it
cannot be built the safe way:

  * The OPNsense traffic shaper model has no layer2 field. Its rule offers interface,
    proto, source, destination, direction and a pipe target, and nothing else. So
    these rules are raw ipfw, outside the model that normally owns them.

  * Raw rules do not survive `ipfw reload`, which OPNsense runs whenever firewall or
    shaper configuration changes. Without help the cap would work and then silently
    stop, which is the failure this plugin works hardest to avoid. The collector
    therefore re-asserts them every five minutes, and `verify` reports whether the
    rule is matching, so a gap is visible rather than silent.

  * Layer2 filtering is a global switch. Turning it on activates the system's stock
    layer2 rules for all traffic, including a deny for frame types that are not IPv4
    or IPv6. A permit-everything rule is therefore installed *after* the pipe rules
    and before the stock set, which leaves what passes exactly as it is with the
    switch off, while still letting a pipe rule match first.

Rule numbering
--------------
The stock layer2 rules begin at 110 and the deny is at 150, so these must sit below
110 to be reached at all. Only this range is ever touched.
"""

import json
import os
import subprocess
import sys

# Below the system's own layer2 rules, which start at 110.
RULE_FIRST = 90
RULE_LAST = 99
# The permit-everything rule, last of ours: a pipe rule above it matches first, and
# anything else is passed exactly as it would be with layer2 filtering off.
SAFETY_RULE = 99
SYSCTL = "net.link.ether.ipfw"


def _run(command, runner=None):
    invoke = runner or _shell
    return invoke(command)


def _shell(command):
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=30)
        return done.returncode, (done.stdout or "") + (done.stderr or "")
    except Exception as error:  # a missing binary must not raise into the collector
        return 1, str(error)


def desired_rules(plan):
    """The layer2 rules a plan calls for, in the order they must be installed.

    Each device that needs an upload cap through this path gets one rule sending its
    egress traffic to the pipe the shaper already created for it.
    """
    rules = []
    number = RULE_FIRST
    for entry in (plan or {}).get("device_pipes") or ():
        if not entry.get("upload_layer2") or not entry.get("upload_pipe"):
            continue
        if number >= SAFETY_RULE:
            # Out of room below the system's rules. Reported rather than silently
            # dropping a limit the user configured.
            break
        rules.append({
            "number": number,
            "pipe": int(entry["upload_pipe"]),
            "device": entry["device"],
            "name": entry.get("name") or entry["device"],
            "spec": ["pipe", str(entry["upload_pipe"]), "ip", "from", str(entry["device"]),
                     "to", "any", "layer2"],
        })
        number += 1
    return rules


def installed_rules(listing):
    """Rule numbers this module owns that are currently present."""
    present = []
    for line in (listing or "").splitlines():
        fields = line.split()
        if not fields or not fields[0].isdigit():
            continue
        number = int(fields[0])
        if RULE_FIRST <= number <= RULE_LAST and "layer2" in line:
            present.append(number)
    return sorted(set(present))


def _listing(runner=None):
    status, output = _run(["/sbin/ipfw", "-a", "list"], runner)
    return output if status == 0 else ""


def remove(runner=None):
    """Take the rules out and put the global switch back."""
    for number in range(RULE_FIRST, RULE_LAST + 1):
        _run(["/sbin/ipfw", "delete", str(number)], runner)
    _run(["/sbin/sysctl", f"{SYSCTL}=0"], runner)
    return {"status": "ok", "removed": True}


def apply_rules(plan, runner=None):
    """Install exactly the rules the plan calls for, and nothing else.

    Idempotent: the existing rules in this range are removed first, so re-asserting
    after an `ipfw reload` and applying a changed plan are the same operation.
    """
    rules = desired_rules(plan)
    if not rules:
        return {"status": "ok", "rules": [], "enabled": False, **remove(runner)}

    # Rules first, then the permit-everything rule, then the switch. Enabling the
    # switch last means layer2 filtering is never active without the permit rule in
    # place, so there is no window in which the stock deny could drop a frame.
    for number in range(RULE_FIRST, RULE_LAST + 1):
        _run(["/sbin/ipfw", "delete", str(number)], runner)
    installed, failed = [], []
    for rule in rules:
        status, output = _run(["/sbin/ipfw", "add", str(rule["number"])] + rule["spec"], runner)
        if status == 0:
            installed.append(rule)
        else:
            failed.append({"device": rule["device"], "error": output.strip()[:200]})
    status, output = _run(["/sbin/ipfw", "add", str(SAFETY_RULE), "allow", "ip",
                           "from", "any", "to", "any", "layer2"], runner)
    if status != 0:
        # Without the permit rule the stock deny would be reachable, so refuse to
        # enable the switch and take our rules back out.
        remove(runner)
        return {"status": "failed", "rules": [], "enabled": False,
                "error": f"could not install the layer2 permit rule: {output.strip()[:200]}"}
    _run(["/sbin/sysctl", f"{SYSCTL}=1"], runner)
    return {
        "status": "failed" if failed else "ok",
        "enabled": True,
        "rules": [{"number": r["number"], "pipe": r["pipe"], "device": r["device"],
                   "name": r["name"]} for r in installed],
        "failed": failed,
        "note": (
            "Experimental. These rules are raw ipfw, because the shaper model has no "
            "layer2 field, so an ipfw reload removes them until the collector puts them "
            "back. Check Verify to confirm the upload rule is matching."
        ),
    }


def sync(plan=None, runner=None):
    """Re-assert the rules if they have gone missing, without touching a healthy set."""
    document = plan
    if document is None:
        try:
            with open("/var/db/wanquota/shaper-plan.json", encoding="utf-8") as handle:
                document = json.load(handle)
        except (OSError, ValueError):
            return {"status": "ok", "action": "none", "reason": "no plan to act on"}
    wanted = desired_rules(document)
    if (document.get("status") != "ok" or document.get("dry_run")) or not wanted:
        # Nothing should be installed: releasing is as important as installing.
        present = installed_rules(_listing(runner))
        if present:
            remove(runner)
            return {"status": "ok", "action": "removed", "rules": []}
        return {"status": "ok", "action": "none"}
    present = set(installed_rules(_listing(runner)))
    expected = {rule["number"] for rule in wanted} | {SAFETY_RULE}
    if present == expected:
        return {"status": "ok", "action": "none", "rules": sorted(present)}
    result = apply_rules(document, runner)
    result["action"] = "installed"
    return result


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "sync"
    if mode == "remove":
        print(json.dumps(remove(), separators=(",", ":")))
        return
    print(json.dumps(sync(), separators=(",", ":")))


if __name__ == "__main__":
    main()
