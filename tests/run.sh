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
grep -q '^\[mcp\]' "$repository/src/opnsense/service/conf/actions.d/actions_wanquota.conf"
grep -q '^\[deviceflush\]' "$repository/src/opnsense/service/conf/actions.d/actions_wanquota.conf"
grep -q 'devices.py' "$repository/src/opnsense/scripts/OPNsense/WanQuota/teardown.php"
grep -q 'shaper.php' "$repository/src/opnsense/scripts/OPNsense/WanQuota/teardown.php"
grep -q '^\[shaperflush\]' "$repository/src/opnsense/service/conf/actions.d/actions_wanquota.conf"
# Invariants established by measuring a real cap on hardware. Each of these was
# wrong once and produced a limit that appeared configured and shaped nothing.
grep -q "direction = 'out'" "$repository/src/opnsense/scripts/OPNsense/WanQuota/shaper.php"
grep -q 'template reload OPNsense/IPFW' "$repository/src/opnsense/scripts/OPNsense/WanQuota/shaper.php"
grep -q 'template reload OPNsense/Shaper' "$repository/src/opnsense/scripts/OPNsense/WanQuota/shaper.php"
grep -q 'shaper/start.sh' "$repository/src/opnsense/scripts/OPNsense/WanQuota/shaper.php"
grep -q 'function delete_pipes' "$repository/src/opnsense/scripts/OPNsense/WanQuota/shaper.php"
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
