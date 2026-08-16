#!/usr/local/bin/python3
"""Guarded multi-WAN recovery for the OPNsense WAN Quota plugin.

The monitor deliberately fails closed.  It never executes a recovery action
unless quota data is available, another WAN passes its probe, the failure is
consecutive, and both the cooldown and daily limit permit an attempt.
"""

import datetime as dt
import fcntl
import hashlib
import hmac
import json
import os
import subprocess
import tempfile
import urllib.request
import urllib.parse
import http.cookiejar
import xml.etree.ElementTree as ET

import report


STATE_DIR = "/var/db/wanquota"
STATE_PATH = os.path.join(STATE_DIR, "recovery.json")
LOCK_PATH = os.path.join(STATE_DIR, "recovery.lock")
DEFAULT_TARGETS = ("1.1.1.1", "8.8.8.8", "9.9.9.9", "208.67.222.222")


def recovery_configuration(root=None):
    root = root or ET.parse(report.CONFIG_PATH).getroot()
    settings = root.find("./OPNsense/WanQuota/general")
    providers = []
    for index in range(1, 5):
        if report.text(settings, f"provider{index}_enabled", "1" if index <= 2 else "0") != "1":
            continue
        logical = report.text(settings, f"provider{index}_interface", "opt1" if index == 2 else "wan")
        providers.append({
            "index": index,
            "name": report.text(settings, f"provider{index}_name", f"ISP {index}"),
            "logical_interface": logical,
            "interface": report.text(root, f"./interfaces/{logical}/if", logical),
            "router": report.text(settings, f"provider{index}_router", ""),
            "target": report.text(settings, f"provider{index}_recovery_target", DEFAULT_TARGETS[index - 1]),
            "action_url": report.text(settings, f"provider{index}_recovery_url", ""),
            "method": report.text(settings, f"provider{index}_recovery_method", "url"),
            "username": report.text(settings, f"provider{index}_recovery_username", ""),
            "password": report.text(settings, f"provider{index}_recovery_password", ""),
            "enabled": report.text(settings, f"provider{index}_recovery_enabled", "0") == "1",
        })
    return {
        "enabled": report.text(settings, "recovery_enabled", "0") == "1",
        "failures": report.bounded_int(report.text(settings, "recovery_failures", "3"), 3, 2, 12),
        "cooldown_minutes": report.bounded_int(report.text(settings, "recovery_cooldown_minutes", "360"), 360, 30, 1440),
        "daily_limit": report.bounded_int(report.text(settings, "recovery_daily_limit", "2"), 2, 1, 10),
        "minimum_remaining_gb": report.bounded_int(report.text(settings, "recovery_minimum_remaining_gb", "1"), 1, 0, 10000),
        "providers": providers,
    }


def load_state(path=STATE_PATH):
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
            return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state, path=STATE_PATH):
    directory = os.path.dirname(path)
    os.makedirs(directory, mode=0o750, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="recovery-", suffix=".json", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(state, handle, separators=(",", ":"), sort_keys=True)
        os.chmod(temporary, 0o640)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def source_address(interface):
    try:
        output = subprocess.check_output(["/sbin/ifconfig", interface, "inet"], text=True, timeout=5)
        words = output.split()
        return words[words.index("inet") + 1]
    except (subprocess.SubprocessError, ValueError, OSError):
        return ""


def ping(source, destination):
    if not source or not destination:
        return False
    return subprocess.run(
        ["/sbin/ping", "-q", "-S", source, "-c", "2", "-W", "1000", destination],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8, check=False,
    ).returncode == 0


def quota_map():
    enabled, providers = report.configuration()
    document = report.summary(enabled, providers)
    return {item["logical_interface"]: item for item in document.get("providers", [])}


def decision(provider, options, quota, internet_ok, alternate_ok, now, state):
    key = provider["logical_interface"]
    current = state.setdefault(key, {"failures": 0, "attempts": []})
    today = now.date().isoformat()
    current["attempts"] = [item for item in current.get("attempts", []) if item.get("day") == today]
    if internet_ok:
        current["failures"] = 0
        return "healthy"
    current["failures"] = int(current.get("failures", 0)) + 1
    if not provider["enabled"]:
        return "provider-disabled"
    if not alternate_ok:
        return "alternate-unavailable"
    if not quota or not quota.get("available"):
        return "quota-unavailable"
    if quota.get("remaining", 0) < options["minimum_remaining_gb"] * 1_000_000_000:
        return "quota-exhausted"
    if current["failures"] < options["failures"]:
        return "confirming-failure"
    last = int(current.get("last_attempt", 0) or 0)
    if int(now.timestamp()) - last < options["cooldown_minutes"] * 60:
        return "cooldown"
    if len(current["attempts"]) >= options["daily_limit"]:
        return "daily-limit"
    return "recover"


def dlink_m961_reboot(provider):
    base = f"http://{provider['router']}"
    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))

    def post(path, values):
        request = urllib.request.Request(
            base + path,
            data=urllib.parse.urlencode(values).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with opener.open(request, timeout=15) as response:
            return response.read().decode(errors="replace")

    key_data = json.loads(post("/boafrm/formLoginKey", {"username": provider["username"]}))
    challenge = key_data["Challenge"]
    private = hmac.new((key_data["PublicKey"] + provider["password"]).encode(), challenge.encode(), hashlib.md5).hexdigest().upper()
    login = hmac.new(private.encode(), challenge.encode(), hashlib.md5).hexdigest().upper()
    result = json.loads(post("/boafrm/formPreLoginSetup", {"username": provider["username"], "password": login}))
    if result.get("status") != 1:
        return False, "D-Link authentication failed"
    post("/boafrm/formLoginSetup", {"username": provider["username"], "password": login})
    post("/boafrm/formSaveConfig", {"reboot": "Reboot"})
    return True, "D-Link reboot accepted"


def invoke(provider):
    if provider.get("method") == "dlink_m961":
        if not provider["router"] or not provider["username"] or not provider["password"]:
            return False, "D-Link router address or credentials missing"
        try:
            return dlink_m961_reboot(provider)
        except Exception as error:
            return False, f"D-Link reboot failed: {error}"
    url = provider["action_url"]
    if not url or not url.startswith(("http://", "https://")):
        return False, "No HTTPS/HTTP recovery URL configured"
    request = urllib.request.Request(url, data=b"{}", method="POST", headers={"Content-Type": "application/json"})
    if provider["username"] or provider["password"]:
        import base64
        token = base64.b64encode(f"{provider['username']}:{provider['password']}".encode()).decode()
        request.add_header("Authorization", "Basic " + token)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return 200 <= response.status < 300, f"HTTP {response.status}"
    except Exception as error:
        return False, str(error)


def run(now=None):
    now = now or dt.datetime.now().astimezone()
    options = recovery_configuration()
    if not options["enabled"]:
        return {"status": "disabled", "providers": []}
    quotas = quota_map()
    os.makedirs(STATE_DIR, mode=0o750, exist_ok=True)
    with open(LOCK_PATH, "a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = load_state()
        probes = {}
        for provider in options["providers"]:
            source = source_address(provider["interface"])
            probes[provider["logical_interface"]] = {
                "source": source,
                "internet": ping(source, provider["target"]),
                "router": ping(source, provider["router"]),
            }
        results = []
        recovery_started = False
        for provider in options["providers"]:
            key = provider["logical_interface"]
            alternate_ok = any(value["internet"] for other, value in probes.items() if other != key)
            outcome = decision(provider, options, quotas.get(key), probes[key]["internet"], alternate_ok, now, state)
            action = None
            if outcome == "recover" and recovery_started:
                outcome = "serialized"
            if outcome == "recover" and not recovery_started:
                recovery_started = True
                ok, detail = invoke(provider)
                action = {"success": ok, "detail": detail}
                current = state[key]
                current["last_attempt"] = int(now.timestamp())
                current.setdefault("attempts", []).append({"day": now.date().isoformat(), "at": int(now.timestamp()), "success": ok})
                current["failures"] = 0 if ok else current["failures"]
                subprocess.run(["/usr/bin/logger", "-t", "wanquota-recovery", f"{provider['name']}: {detail}"], check=False)
            results.append({"name": provider["name"], "interface": key, "router_reachable": probes[key]["router"], "internet_reachable": probes[key]["internet"], "decision": outcome, "action": action})
        state["updated_at"] = now.isoformat(timespec="seconds")
        save_state(state)
    return {"status": "ok", "generated_at": now.isoformat(timespec="seconds"), "providers": results}


def main():
    try:
        print(json.dumps(run(), separators=(",", ":")))
    except BlockingIOError:
        print(json.dumps({"status": "busy", "providers": []}, separators=(",", ":")))


if __name__ == "__main__":
    main()
