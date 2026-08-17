# os-wanquota

Community preview of an OPNsense plugin for configurable multi-WAN billing-cycle
quota reporting and top-consumer visibility.

## Features

- One to four independently enabled providers, resolved from OPNsense logical interfaces.
- Downloadable CSV and JSON quota summaries and consumer/domain attribution reports.
- Responsive Chart.js dashboard with quota cards, provider comparisons, traffic mix,
  top-consumer/domain bars, daily/monthly trends, and visual source-health status.
- Decimal-GB quota, billing-cycle day, warning threshold, remaining allowance,
  daily budget, projection, and vnStat-backed history.
- Dashboard widgets and JSON API.
- Top LAN consumers from ntopng host RRDs.
- Estimated domain bandwidth by correlating Insight flow bytes with recently
  observed Unbound A/AAAA answers, including a visible coverage percentage.
- Configurable reporting period, result count, and DNS mapping retention.
- Clickable dashboard widgets that open the full report or Consumers tab.
- Dedicated Top WAN Domains widget with visible attribution coverage.
- Color-coded quota progress meters and projected-overage warnings.
- Deduplicated quota alerts in the system log with configurable repeat timing.
- Data Health tab covering vnStat, ntopng, Insight, DNS mappings, and alert freshness.
- Device-to-domain drill-down using a single deduplicated LAN flow source.
- Exact per-WAN flow-total rankings for devices and domains when Insight retains the post-NAT internal address. Direction splits remain explicitly unavailable because Insight interface direction is not equivalent to download versus upload bytes.
- Persistent completed-cycle archive, imported ISP baselines, previous-cycle comparisons,
  exhaustion forecasts, daily budgets, and provider cost-per-GB metrics.
- Gateway latency, loss, availability and traffic-versus-quality views.
- Device groups discovered from OPNsense aliases, optional group budgets, domain
  service categories, first/last-seen metadata, and search/filter drill-downs.
- Conservative anomaly detection for device totals, unusual uploads, new devices,
  quiet-hours traffic, provider spikes, and gateway health.
- Multi-level quota guardrails with dry-run recommendations, emergency reserves,
  expiring overrides, reversible weight/tier changes and an optional quota cutoff.
- HTTPS webhook alerts and scheduled summaries, native authenticated JSON API,
  Prometheus-compatible metrics, wallboard mode, high-contrast mode, and clickable charts.
- Read-only Model Context Protocol server so AI agents can query quota status,
  consumers, forecasts, and data-source health over stdio or the authenticated API.
- Device names resolved from DHCP leases as well as static mappings, and device
  identity tracked by MAC so budgets and history survive an address change.
- Optional per-device budget enforcement, disabled and dry-run by default.

## Screenshots

![WAN quota dashboard widgets](docs/screenshots/dashboard-widgets.png)

![Consumer and attributed-domain report](docs/screenshots/consumer-report.png)

![Data-source health report](docs/screenshots/data-health.png)

![WAN intelligence, forecasts and guardrails](docs/screenshots/intelligence-report.png)

## Configuration

Open **Reporting → WAN Quota → Settings**. Intelligence collection is enabled by
default, while automatic guardrail enforcement is disabled and dry-run is enabled.
Keep those safe defaults until the recommendations match your intended routing.

Device groups and budgets accept JSON arrays such as
`[{"name":"Family","members":["192.168.1.0/25"],"budget_gb":200}]`.
Per-device policies accept
`[{"address":"192.168.1.20","budget_gb":50,"exclude":false}]`. Existing
OPNsense aliases named `INFRASTRUCTURE_DEVICES`, `MY_DEVICES`,
`HOME_IOT_DEVICES`, and `UNCLASSIFIED_DEVICES` are discovered automatically.

Temporary policy overrides are available from the Intelligence tab. They expire
after 1–168 hours and remain advisory while enforcement is disabled or dry-run.
The emergency reserve and four configurable percentage thresholds determine when
the plugin recommends deprioritizing, failing over, or cutting off a provider.
All routing changes are reversible and the original gateway settings are retained.

The authenticated OPNsense API exposes intelligence JSON at
`/api/wanquota/report/intelligence_thirty` and Prometheus text inside the
`metrics` field at `/api/wanquota/report/metrics`. HTTPS webhooks support generic,
Discord, Slack, Telegram, and private Home Assistant destinations. SMTP reports
use STARTTLS and can include a CSV provider summary.

## Model Context Protocol

The plugin ships a read-only MCP server so an AI agent can answer questions about
the link ("is either provider going to blow its cap this cycle?", "which device
drove yesterday's spike?") without being handed shell access to the firewall.

Nine tools are exposed: `wanquota_summary`, `wanquota_daily`, `wanquota_monthly`,
`wanquota_health`, `wanquota_consumers`, `wanquota_intelligence`,
`wanquota_metrics`, plus `wanquota_device` and `wanquota_site` for drilling into
one device or one domain without pulling the whole report. Period-aware tools
accept `today`, `week`, `thirty`, or `month`.

The summary and health reports are also exposed as resources at
`wanquota://summary` and `wanquota://health`. Every tool declares
`readOnlyHint`, so a client need not ask before each call.

Guardrail overrides are deliberately **not** exposed. The tool surface cannot
change routing, set an override, or write any state, so connecting an agent
cannot alter how traffic leaves the network. Use the Intelligence tab or
`POST /api/wanquota/override` for overrides.

### Giving an agent a read-only credential

The tool surface being read-only is not enough on its own: a key is only as
narrow as the privilege it is issued under, and a key holding the full
**Services: WAN Quotas** privilege can also POST an override.

Grant **Services: WAN Quotas (read only)** instead. It covers the reporting and
MCP endpoints and nothing else, so the credential cannot change routing even if
something else on the box could. Overrides live on their own path precisely so
this split is possible — ACL patterns match on the URL, so an override action
sharing the reporting path could not have been excluded.

Create a group with only that privilege, add a user to it, and issue the API key
under that user.

### Exposure

`/api/wanquota/mcp` refuses any request whose client address is not inside the
LAN network defined in `config.xml`, or loopback. The check fails closed: if the
LAN cannot be determined the endpoint serves nothing. An off-LAN caller is
refused before its request body is parsed, so it learns nothing about the
endpoint beyond the refusal.

That guard is defence in depth, **not** the primary control. This endpoint is
served by the OPNsense web GUI, so what can reach it at all is decided by the
interfaces the GUI listens on (**System → Settings → Administration**) and the
firewall rules in front of it. If the GUI itself is reachable from WAN, that is
the exposure to fix; the plugin only guarantees it will not answer MCP there.

Two consequences worth knowing:

- Administering from a different internal VLAN is refused too. "LAN" means the
  `lan` interface in `config.xml`, not RFC1918 generally.
- The stdio transport is not address-filtered, because reaching it already
  requires shell access to the firewall.

Over stdio, from a workstation with SSH access to the firewall:

```json
{
  "mcpServers": {
    "wanquota": {
      "command": "ssh",
      "args": ["root@firewall.example", "/usr/local/opnsense/scripts/OPNsense/WanQuota/mcp.py", "--stdio"]
    }
  }
}
```

Over the authenticated API, POST a JSON-RPC request to `/api/wanquota/mcp` using
an OPNsense API key and secret as HTTP Basic credentials:

```
curl -sk -u "$KEY:$SECRET" https://firewall.example/api/wanquota/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

Both transports run the same dispatcher in
`src/opnsense/scripts/OPNsense/WanQuota/mcp.py`. It implements JSON-RPC 2.0
against the Python standard library only, so the feature adds no packages to
`PLUGIN_DEPENDS`.

Tool calls degrade the way the rest of the plugin does: if a collector is
unavailable the call returns `isError` with the reason rather than dropping the
session, and `wanquota_health` is the tool to reach for first when a figure looks
wrong.

## Building and installing

Build a real package rather than copying files into place. Copying preserves the
source tree's file modes, and a script that loses its executable bit stops being
runnable by configd without any visible error.

On the firewall, fetch the plugins tree once:

```
opnsense-code plugins
```

Then place this repository at `/usr/plugins/net/wanquota` and build:

```
cd /usr/plugins/net/wanquota
make clean && make package
pkg install -y -f work/pkg/os-wanquota-*.pkg
```

The post-install hook reloads configd, runs migrations, flushes the menu and ACL
caches, and registers the DNS collector, so no manual restart is needed.

`PLUGIN_REVISION` tracks fixes released against the same `PLUGIN_VERSION`, giving
package versions such as `0.8_2`.

## Per-device budget enforcement

The gateway guardrails act on a whole provider. Per-device enforcement acts on
individual devices that exceed a budget, by maintaining the pf table
`wanquota_over_budget`. **You must add a firewall rule blocking that table** —
the plugin maintains membership, your rule decides what membership means.

It is **disabled by default, and dry-run when first enabled**. Dry run records
the membership it would apply to
`/var/db/wanquota/device-enforcement-plan.json` and changes nothing. Read that
file before turning dry-run off.

Three categories can never be blocked, regardless of budget: the firewall itself,
any device marked `exclude` in the per-device policies, and any member of a group
named `Protected Infrastructure` or discovered from the
`INFRASTRUCTURE_DEVICES` alias. A budget cannot lock the firewall out of its own
network or take down infrastructure the network depends on.

Membership is recomputed every run and applied as one atomic replace, so raising
a budget releases the device on the next run. `configctl wanquota deviceflush`
empties the table immediately, and uninstalling the plugin flushes it too — a
rule owned by a plugin that no longer exists must not keep blocking anything.

None of this is reachable from the MCP server. The tool surface stays read-only,
and a test asserts no tool or resource can touch enforcement.

## Device identity

Names come from static mappings in `config.xml` first, then the DHCP hostname
from the dnsmasq or Kea lease file, then the bare address. Reading only static
mappings left devices showing as raw IPs that the firewall could already name.

Per-device budgets and exclusions match on address, MAC, **or** DHCP hostname,
and history baselines are keyed to the MAC when one is known. Addresses are not
identity: DHCP reassigns them, and a device using a randomised MAC per network
holds several leases at once, so a policy keyed only to an address silently stops
applying to the device it was set for.

## Requirements

- A current OPNsense installation with `os-vnstat` and `os-ntopng`.
- Insight/NetFlow enabled on the LAN interface for domain attribution.
- Unbound DNS for DNS attribution. Host quota reporting still works when domain
  attribution is disabled.

The domain report is an estimate, not traffic decryption. DoH/DoT, VPNs, ECH,
shared CDN addresses, expired cache entries, and DNS answers missed between
collector runs can remain unattributed. The coverage indicator is therefore a
required part of interpreting the result.

## Development status

This repository is the source-only community preview. It intentionally contains
no production configuration, databases, generated package, device inventory, or
credentials. Installation through the OPNsense plugin catalog will require
acceptance into the official `opnsense/plugins` repository.

Official-framework builds generate the standard OPNsense install hooks. On
install or upgrade these reload configd, run migrations, flush the menu and ACL
caches, initialize defaults without overwriting existing settings, and register
the DNS collector. Uninstall removes only the plugin-owned collector schedule;
configuration and accounting history are retained for a future reinstall.

Run the portable checks with:

```sh
./tests/run.sh
```

## License

BSD-2-Clause.
