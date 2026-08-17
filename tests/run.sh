#!/bin/sh
set -eu

repository=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python3 -m unittest discover -s "$repository/tests" -v
python3 -m compileall -q "$repository/src" "$repository/tests"

test -f "$repository/+POST_INSTALL.post"
test -f "$repository/+PRE_DEINSTALL.post"
test -x "$repository/+POST_INSTALL.post"
test -x "$repository/+PRE_DEINSTALL.post"
test -x "$repository/src/opnsense/scripts/OPNsense/WanQuota/report.py"
test -x "$repository/src/opnsense/scripts/OPNsense/WanQuota/consumers.py"
test -x "$repository/src/opnsense/scripts/OPNsense/WanQuota/monitor.py"
test -x "$repository/src/opnsense/scripts/OPNsense/WanQuota/health.py"
test -x "$repository/src/opnsense/scripts/OPNsense/WanQuota/intelligence.py"
test -x "$repository/src/opnsense/scripts/OPNsense/WanQuota/mcp.py"
test -x "$repository/src/opnsense/scripts/OPNsense/WanQuota/devices.py"
test -x "$repository/src/opnsense/scripts/OPNsense/WanQuota/shaper.py"
test -x "$repository/src/opnsense/scripts/OPNsense/WanQuota/sessions.py"
test -x "$repository/src/opnsense/scripts/OPNsense/WanQuota/explain.py"
test -x "$repository/src/opnsense/scripts/OPNsense/WanQuota/addresses.py"
grep -q '^\[mcp\]' "$repository/src/opnsense/service/conf/actions.d/actions_wanquota.conf"
grep -q '^\[deviceflush\]' "$repository/src/opnsense/service/conf/actions.d/actions_wanquota.conf"
grep -q 'devices.py' "$repository/src/opnsense/scripts/OPNsense/WanQuota/teardown.php"
grep -q 'shaper.php' "$repository/src/opnsense/scripts/OPNsense/WanQuota/teardown.php"
# mapDataToFormUI only populates <form> elements whose id, up to the first hyphen,
# equals the key it was given. Step forms named anything else load no data at all
# and every setting renders blank, which is exactly what happened once.
python3 - "$repository/src/opnsense/mvc/app/views/OPNsense/WanQuota/general.volt" <<'PYCHECK'
import re
import sys

source = open(sys.argv[1], encoding="utf-8").read()
ids = re.findall(r"'id'\s*:\s*'([^']+)'", source)
steps = [i for i in ids if i.startswith("frm_") and i != "frm_wanquota_settings"]
assert steps, "no step forms found in the settings view"
bad = [i for i in steps if i.split("-")[0] != "frm_wanquota_settings"]
assert not bad, f"step form ids will not be populated by mapDataToFormUI: {bad}"
PYCHECK
grep -q '^\[shaperflush\]' "$repository/src/opnsense/service/conf/actions.d/actions_wanquota.conf"
# Invariants established by measuring a real cap on hardware. Each of these was
# wrong once and produced a limit that appeared configured and shaped nothing.
grep -q "direction = 'out'" "$repository/src/opnsense/scripts/OPNsense/WanQuota/shaper.php"
grep -q 'template reload OPNsense/IPFW' "$repository/src/opnsense/scripts/OPNsense/WanQuota/shaper.php"
grep -q 'template reload OPNsense/Shaper' "$repository/src/opnsense/scripts/OPNsense/WanQuota/shaper.php"
grep -q 'shaper/start.sh' "$repository/src/opnsense/scripts/OPNsense/WanQuota/shaper.php"
grep -q 'function delete_pipes' "$repository/src/opnsense/scripts/OPNsense/WanQuota/shaper.php"
# Turning limits off must also delete the pipes from the running kernel, not only
# from the configuration. Measured: after disabling, the rules were gone but
# `ipfw pipe list` still showed 22000 and 22500, so the release looked incomplete
# to anyone checking. There must be a delete_pipes call in the release path, which
# is the branch taken when the plan is disabled or a dry run.
python3 - "$repository/src/opnsense/scripts/OPNsense/WanQuota/shaper.php" <<'PYCHECK'
import re
import sys
source = open(sys.argv[1], encoding="utf-8").read()
released = source.split("per-service limits released")
assert len(released) == 2, "the release branch is no longer identifiable"
following = released[1].split("exit(0);")[0]
assert "delete_pipes(" in following, \
    "disabling limits must delete the kernel pipes, not just the configuration"
PYCHECK
# Removing one limit while others stay enabled must also delete its kernel pipe.
# Measured after removing a Twitch cap: `ipfw pipe list` still showed 21001 at
# 3 Mbit/s with no rule pointing at it, which reads as a limit still in force.
python3 - "$repository/src/opnsense/scripts/OPNsense/WanQuota/shaper.php" <<'PYCHECK'
import sys
source = open(sys.argv[1], encoding="utf-8").read()
body = source[source.index("WAN quota per-service bandwidth pipes"):]
body = body[:body.index("exit(0);")]
assert "delete_pipes(" in body, \
    "applying must delete kernel pipes the new plan no longer uses"
PYCHECK
# Upload shaping is impossible while a capture engine holds packets away from
# ipfw's inbound hook, so the plan must be able to refuse the upload half alone
# rather than reporting a cap that shapes nothing.
# The model's bandwidth is an IntegerField, so writing a fractional Mbit/s rate
# fails validation and applies nothing at all — a 480p cap (1.5 Mbit/s) created no
# pipe, no rule, and reported no error in the interface. The bandwidth written must
# come from the plan's integral field, never from the fractional rate.
if grep -qE '(bandwidth|bandwidthMetric) = .*\$entry\[.(upload_)?mbit' \
        "$repository/src/opnsense/scripts/OPNsense/WanQuota/shaper.php"; then
    echo "pipe bandwidth must use the plan's integral bandwidth, not the Mbit rate" >&2
    exit 1
fi
grep -q 'function bandwidth_of' "$repository/src/opnsense/scripts/OPNsense/WanQuota/shaper.php"
grep -q 'def bandwidth_fields' "$repository/src/opnsense/scripts/OPNsense/WanQuota/shaper.py"
# The running rule matches a snapshot of addresses from apply time. A service cap
# whose CDN moves then holds none of the addresses in use, so the collector must
# re-apply when the shaped set changes; without this the feature works only until
# the CDN rotates.
grep -q 'shaper.sync()' "$repository/src/opnsense/scripts/OPNsense/WanQuota/monitor.py"
grep -q 'def plan_fingerprint' "$repository/src/opnsense/scripts/OPNsense/WanQuota/shaper.py"
# The MCP server can change settings and limits, so it must not be reachable under
# a privilege named "read only": that would let a read-only account reconfigure the
# plugin. Reports stay readable there.
python3 - "$repository/src/opnsense/mvc/app/models/OPNsense/WanQuota/ACL/ACL.xml" <<'PYCHECK'
import sys
import xml.etree.ElementTree as ET
root = ET.parse(sys.argv[1]).getroot()
readonly = root.find("./page-services-wanquota-readonly/patterns")
patterns = [node.text for node in readonly]
assert "api/wanquota/mcp/*" not in patterns, \
    "the MCP endpoint can write; it must not sit under the read-only privilege"
assert "api/wanquota/report/*" in patterns, "reports must stay readable"
PYCHECK
test -x "$repository/src/opnsense/scripts/OPNsense/WanQuota/configure.php"
grep -q 'CONFIGURE_SCRIPT' "$repository/src/opnsense/scripts/OPNsense/WanQuota/mcp.py"
grep -q '^\[shapersync\]' "$repository/src/opnsense/service/conf/actions.d/actions_wanquota.conf"
grep -q 'co_delivery' "$repository/src/opnsense/scripts/OPNsense/WanQuota/shaper.py"
grep -q 'def netmap_interception' "$repository/src/opnsense/scripts/OPNsense/WanQuota/shaper.py"
grep -q 'upload_rejected' "$repository/src/opnsense/scripts/OPNsense/WanQuota/shaper.py"
# A disabled upload field must still render the configured rate. Saving reads
# disabled inputs, so blanking it would silently delete a rate the user set and
# lose it for good if the capture engine were later removed.
if grep -q 'uploadOk ? row.upload_mbit' \
        "$repository/src/opnsense/mvc/app/views/OPNsense/WanQuota/general.volt"; then
    echo "the disabled upload field must keep showing the configured rate" >&2
    exit 1
fi
# Limits and Settings write the same fields, so a change on one page must refresh
# the other. Enabling limits and clearing dry-run from the Limits page once left
# Settings still showing them off, which reads as the save having been lost.
grep -q 'function loadSettings' "$repository/src/opnsense/mvc/app/views/OPNsense/WanQuota/general.volt"
grep -q 'shown.bs.tab., loadSettings' "$repository/src/opnsense/mvc/app/views/OPNsense/WanQuota/general.volt"
python3 - "$repository/src/opnsense/mvc/app/views/OPNsense/WanQuota/general.volt" <<'PYCHECK'
import sys
source = open(sys.argv[1], encoding="utf-8").read()
def handler_after(marker):
    """The callback body only: stop at the next top-level function definition."""
    start = source.index(marker)
    rest = source[start:]
    end = rest.find("\nfunction ")
    return rest[:end if end > 0 else 2000]

for endpoint in ("/api/wanquota/limits/set'", "/api/wanquota/limits/setDevices'"):
    assert "loadSettings()" in handler_after(endpoint), \
        f"saving via {endpoint} must refresh the settings form"
assert "refreshLimitViews()" in handler_after("/api/wanquota/settings/set'"), \
    "saving settings must refresh the limits views"
PYCHECK
grep -q '^\[shaperverify\]' "$repository/src/opnsense/service/conf/actions.d/actions_wanquota.conf"
grep -q '^\[shapercapability\]' "$repository/src/opnsense/service/conf/actions.d/actions_wanquota.conf"
grep -q 'WanQuota/setup.php' "$repository/+POST_INSTALL.post"
grep -q 'WanQuota/teardown.php' "$repository/+PRE_DEINSTALL.post"
grep -q 'general/index#consumers' "$repository/src/opnsense/www/js/widgets/WanConsumers.js"
grep -q 'general/index' "$repository/src/opnsense/www/js/widgets/WanQuota.js"
grep -q 'general/index#consumers' "$repository/src/opnsense/www/js/widgets/WanDomains.js"
grep -q '<wandomains>' "$repository/src/opnsense/www/js/widgets/Metadata/WanQuota.xml"

# The PHP side was only ever linted. Run the framework-free transport tests when
# a php binary is available: CI has one and so does the firewall, so this is
# covered in both places, and skipped cleanly where php is absent.
if command -v php >/dev/null 2>&1; then
    php "$repository/tests/php/McpGatewayTest.php"
fi

# The report view carries most of the UI logic but is not covered by the unit
# tests, and a syntax error there breaks the page silently. Parse the inline
# script blocks when a JS engine is available; skip cleanly when it is not, so
# this stays runnable on the firewall.
if command -v node >/dev/null 2>&1; then
    for widget in "$repository"/src/opnsense/www/js/widgets/*.js; do
        node --check "$widget"
    done
    scratch=$(mktemp -d)
    extracted="$scratch/view.js"
    python3 - "$repository/src/opnsense/mvc/app/views/OPNsense/WanQuota/general.volt" "$extracted" <<'PY'
import re
import sys
from pathlib import Path

source = Path(sys.argv[1]).read_text(encoding="utf-8")
blocks = re.findall(r"<script[^>]*>(.*?)</script>", source, re.S)
script = "\n".join(blocks)
# Substitute what Volt actually renders, not a placeholder. Many of these tags sit
# inside single-quoted JavaScript strings that also carry double-quoted HTML
# attributes, so a rendered apostrophe would terminate the string early. Expanding
# lang._('...') to its literal text means the check fails on exactly that mistake
# instead of hiding it behind a safe stand-in token.
script = re.sub(r"\{\{\s*lang\._\((['\"])(.*?)\1\)\s*\}\}", lambda m: m.group(2), script, flags=re.S)
# Any remaining tag (cache_safe and friends) is not text; a bare token is fine.
script = re.sub(r"\{\{.*?\}\}", "x", script, flags=re.S)
Path(sys.argv[2]).write_text(script, encoding="utf-8")
PY
    node --check "$extracted"
    rm -rf "$scratch"
fi
