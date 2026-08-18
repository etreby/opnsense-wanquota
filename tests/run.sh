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
test -x "$repository/src/opnsense/scripts/OPNsense/WanQuota/layer2.py"
test -x "$repository/src/opnsense/scripts/OPNsense/WanQuota/discovery.py"
# A discovered service is only worth finding if accepting it makes it cappable, so the
# shaper catalog must be the union of the built-ins and what was accepted.
grep -q "def full_catalog" "$repository/src/opnsense/scripts/OPNsense/WanQuota/shaper.py"
grep -q "discovery.accepted_services" "$repository/src/opnsense/scripts/OPNsense/WanQuota/shaper.py"
grep -q "^\[discoveryaccept\]" "$repository/src/opnsense/service/conf/actions.d/actions_wanquota.conf"
test -x "$repository/src/opnsense/scripts/OPNsense/WanQuota/throughput.py"
test -x "$repository/src/opnsense/scripts/OPNsense/WanQuota/configure.php"
# Experimental upload shaping installs raw ipfw rules and flips a global sysctl, so
# the permit-everything rule must exist and must be numbered after the pipe rules:
# ahead of them it would end layer2 processing before a pipe could match, and absent
# altogether the system's stock layer2 deny becomes reachable for every frame.
python3 - "$repository/src/opnsense/scripts/OPNsense/WanQuota/layer2.py" <<'PYCHECK'
import re
import sys
source = open(sys.argv[1], encoding="utf-8").read()
first = int(re.search(r"^RULE_FIRST = (\d+)", source, re.M).group(1))
safety = int(re.search(r"^SAFETY_RULE = (\d+)", source, re.M).group(1))
assert first < safety, "the permit rule must come after the pipe rules"
assert safety < 110, "our layer2 rules must sit below the system's, which start at 110"
assert "allow" in source and "layer2" in source, "the permit rule is missing"
PYCHECK
grep -q "^\[layer2sync\]" "$repository/src/opnsense/service/conf/actions.d/actions_wanquota.conf"
grep -q "^\[throughput\]" "$repository/src/opnsense/service/conf/actions.d/actions_wanquota.conf"
grep -q "layer2.sync()" "$repository/src/opnsense/scripts/OPNsense/WanQuota/monitor.py"
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
# The enable and dry-run switches govern service and device limits together, so there
# must be exactly one of each in the Limits tab. There were two of each, one per
# sub-tab, both writing the same model field: saving a device limit while the device
# sub-tab's switch was unticked turned shaping off, so the service limits looked
# untouched but disabled and no rules were installed.
python3 - "$repository/src/opnsense/mvc/app/views/OPNsense/WanQuota/general.volt" <<'PYCHECK'
import re
import sys
source = open(sys.argv[1], encoding="utf-8").read()
for switch in ("limitEnabled", "limitDryRun"):
    found = re.findall(r'<input[^>]*id="%s"' % switch, source)
    assert len(found) == 1, f"expected exactly one {switch} control, found {len(found)}"
for gone in ("deviceLimitEnabled", "deviceLimitDryRun"):
    assert gone not in source, f"{gone} duplicates a shared switch and must not return"
PYCHECK
# The endpoints must treat the switches as optional, so a caller that omits them
# cannot silently disable shaping.
grep -q 'private function applyState' \
    "$repository/src/opnsense/mvc/app/controllers/OPNsense/WanQuota/Api/LimitsController.php"
python3 - "$repository/src/opnsense/mvc/app/controllers/OPNsense/WanQuota/Api/LimitsController.php" <<'PYCHECK'
import sys
source = open(sys.argv[1], encoding="utf-8").read()
assert "shaper_enabled = $this->request->getPost('enabled')" not in source, \
    "absent must not read as off: use applyState"
PYCHECK
# Every setting that can be written must be visible somewhere in the interface, and
# every visible setting must be writable. A setting reachable by the API but absent
# from the wizard is one a user cannot see or correct.
python3 - "$repository" <<'PYCHECK'
import re
import sys
from pathlib import Path
root = Path(sys.argv[1])
forms = root / "src/opnsense/mvc/app/controllers/OPNsense/WanQuota/forms"
visible = set()
for path in forms.glob("wizard_*.xml"):
    visible |= set(re.findall(r"wanquota\.general\.([a-z0-9_]+)", path.read_text()))
source = (root / "src/opnsense/scripts/OPNsense/WanQuota/configure.php").read_text()
block = source[source.index("const WRITABLE = ["):source.index("];")]
writable = set(re.findall(r"'([a-z0-9_]+)'", block))
for index in range(1, 5):
    for suffix in ("enabled", "name", "interface", "quota_gb", "cycle_day",
                   "warning_percent", "cycle_cost", "baseline_gb", "baseline_cycle"):
        writable.add(f"provider{index}_{suffix}")
model = (root / "src/opnsense/mvc/app/models/OPNsense/WanQuota/WanQuota.xml").read_text()
general = model[model.index("<general>"):model.index("</general>")]
fields = set(re.findall(r"<([a-z0-9_]+) type=", general))
# Four settings are owned by the Limits tab, which has its own controls for them.
# They used to appear in the wizard as well, so the dry-run switch existed twice and
# the two copies could disagree; the correspondence check has to know that rather than
# forcing them back into the wizard.
elsewhere = {"shaper_enabled", "shaper_dry_run", "service_limits_json", "device_limits_json"}
view = (root / "src/opnsense/mvc/app/views/OPNsense/WanQuota/general.volt").read_text()
assert "id=\"limitEnabled\"" in view and "id=\"limitDryRun\"" in view, \
    "the Limits tab must still own the enable and dry-run controls"
for field in elsewhere:
    assert f"wanquota.general.{field}" not in view or field in ("shaper_enabled",), \
        f"{field} is owned by the Limits tab and must not be a wizard field too"
missing = (writable - visible) - elsewhere
assert not missing, f"writable but invisible: {sorted(missing)}"
unseen = (fields - visible) - elsewhere
assert not unseen, f"in the model but nowhere in the interface: {sorted(unseen)}"
PYCHECK
# Both tables on the live sessions page must filter to a device when its name is
# clicked, not navigate to the historical report. Only the sessions table was changed
# the first time, and the device summary table above it — the one a reader clicks first
# — still left the page.
python3 - "$repository/src/opnsense/mvc/app/views/OPNsense/WanQuota/general.volt" <<'PYCHECK'
import sys
source = open(sys.argv[1], encoding="utf-8").read()
for name in ("deviceTable", "sessionTable"):
    start = source.index(f"function {name}(")
    depth, index = 0, source.index("{", start)
    while True:
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                break
        index += 1
    body = source[start:index]
    assert "wq-session-device" in body, \
        f"{name} must filter to the device rather than leaving the sessions page"
PYCHECK
# An HTML entity must not be passed through esc(), which renders it as literal text.
# The port column showed "55972 &rarr; 443" until the arrow was moved outside esc().
python3 - "$repository/src/opnsense/mvc/app/views/OPNsense/WanQuota/general.volt" <<'PYCHECK'
import re
import sys
source = open(sys.argv[1], encoding="utf-8").read()
entity = re.compile(r"&[a-zA-Z]+;|&#\d+;")
bad = []
start = 0
while True:
    at = source.find("esc(", start)
    if at < 0:
        break
    # Match parentheses so a nested call does not end the argument early, which is what
    # let the escaped arrow through the first version of this check.
    depth, index = 0, at + 3
    while index < len(source):
        if source[index] == "(":
            depth += 1
        elif source[index] == ")":
            depth -= 1
            if depth == 0:
                break
        index += 1
    argument = source[at + 4:index]
    if entity.search(argument):
        bad.append(argument.strip()[:70])
    start = at + 4
assert not bad, f"HTML entities inside esc() render as text: {bad}"
PYCHECK
# A session row must carry the flow key the backend produces. Rebuilding it in the
# interface from separate fields would drift from the key sessions.py uses to
# deduplicate NAT twins, and per-session rates would then be attributed to the wrong
# flow or silently lost.
grep -q '"key": "|".join' "$repository/src/opnsense/scripts/OPNsense/WanQuota/sessions.py"
grep -q 'before\[row.key\]' "$repository/src/opnsense/mvc/app/views/OPNsense/WanQuota/general.volt"
# Capping offers the registrable domain, never the per-session hostname: one appliance
# for one session is useless as a cap target.
grep -q 'remote_registrable' "$repository/src/opnsense/scripts/OPNsense/WanQuota/sessions.py"
grep -q 'row.remote_registrable' "$repository/src/opnsense/mvc/app/views/OPNsense/WanQuota/general.volt"
# No two top-level functions in the view may share a name. JavaScript keeps the last
# declaration silently, so a duplicate does not fail to load — it replaces the other
# one. A second rate() defined for the live sessions table overwrote the one formatting
# per-WAN throughput, and because it returns null when called with one argument, the
# live cards rendered with empty numbers while every layer beneath them was correct.
python3 - "$repository/src/opnsense/mvc/app/views/OPNsense/WanQuota/general.volt" <<'PYCHECK'
import collections
import re
import sys
source = open(sys.argv[1], encoding="utf-8").read()
names = re.findall(r"^function ([A-Za-z_$][\w$]*)\s*\(", source, re.M)
duplicated = [name for name, n in collections.Counter(names).items() if n > 1]
assert not duplicated, f"these view functions are declared more than once: {duplicated}"
PYCHECK
# A provider's fields are shown only when that provider is on: two of the four slots
# are normally off, so most of the settings page was configuration for WANs that do not
# exist. Nothing is removed, so a disabled slot keeps its stored values.
grep -q "function applyFieldVisibility" \
    "$repository/src/opnsense/mvc/app/views/OPNsense/WanQuota/general.volt"
# Every dependent must be a real model field, or a typo silently hides nothing; and no
# dependent may itself be a control, because the single visibility pass would then be
# able to leave a row wrongly shown.
python3 - "$repository" <<'PYCHECK'
import re
import sys
from pathlib import Path
root = Path(sys.argv[1])
view = (root / "src/opnsense/mvc/app/views/OPNsense/WanQuota/general.volt").read_text()
block = view[view.index("const FIELD_DEPENDENCIES = {"):view.index("const PROVIDER_FIELDS")]
anyof = view[view.index("const FIELD_ANY_OF = {"):view.index("function settingRow")]
controls = set(re.findall(r"^\s{4}([a-z0-9_]+):", block, re.M))
dependents = set(re.findall(r"'([a-z0-9_]+)'", block))
# An any-of entry names the dependent as its key and its controls as values.
dependents |= set(re.findall(r"^\s{4}([a-z0-9_]+):", anyof, re.M))
controls |= set(re.findall(r"'([a-z0-9_]+)'", anyof))
model = (root / "src/opnsense/mvc/app/models/OPNsense/WanQuota/WanQuota.xml").read_text()
general = model[model.index("<general>"):model.index("</general>")]
fields = set(re.findall(r"<([a-z0-9_]+) type=", general))
unknown = (controls | dependents) - fields
assert not unknown, f"not model fields: {sorted(unknown)}"
nested = controls & dependents
assert not nested, f"a dependent that is also a control needs a settling loop: {sorted(nested)}"
PYCHECK
# The guardrail must not report "dry run" for a state that is not dry run.
grep -q "function guardrailState" \
    "$repository/src/opnsense/mvc/app/views/OPNsense/WanQuota/general.volt"
if grep -q "policy.dry_run?'(dry-run)'" \
        "$repository/src/opnsense/mvc/app/views/OPNsense/WanQuota/general.volt"; then
    echo "enforcement being off is not dry run; report the state" >&2
    exit 1
fi
# Opening the Limits tab must always reload it. Refreshing only when nothing had
# loaded yet left the shared enable and dry-run switches showing whatever they showed
# on the first visit, so a change made in Settings left Limits contradicting the
# configuration — and "am I live or in dry run?" must not be ambiguous.
python3 - "$repository/src/opnsense/mvc/app/views/OPNsense/WanQuota/general.volt" <<'PYCHECK'
import sys
source = open(sys.argv[1], encoding="utf-8").read()
assert 'if (!limitData) refreshLimits()' not in source, \
    "the Limits tab must reload every time it is opened, not only the first time"
assert "function renderLimitState" in source, \
    "the effective limit state must be stated from the configuration, not the checkboxes"
PYCHECK
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
