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
grep -q '^\[mcp\]' "$repository/src/opnsense/service/conf/actions.d/actions_wanquota.conf"
grep -q 'WanQuota/setup.php' "$repository/+POST_INSTALL.post"
grep -q 'WanQuota/teardown.php' "$repository/+PRE_DEINSTALL.post"
grep -q 'general/index#consumers' "$repository/src/opnsense/www/js/widgets/WanConsumers.js"
grep -q 'general/index' "$repository/src/opnsense/www/js/widgets/WanQuota.js"
grep -q 'general/index#consumers' "$repository/src/opnsense/www/js/widgets/WanDomains.js"
grep -q '<wandomains>' "$repository/src/opnsense/www/js/widgets/Metadata/WanQuota.xml"

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
# Volt tags are rendered server-side; stand them in as literals so the remaining
# JavaScript can be parsed on its own.
script = re.sub(r"\{\{.*?\}\}", "'x'", "\n".join(blocks), flags=re.S)
Path(sys.argv[2]).write_text(script, encoding="utf-8")
PY
    node --check "$extracted"
    rm -rf "$scratch"
fi
