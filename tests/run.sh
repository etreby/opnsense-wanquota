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
