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
- Guarded multi-WAN recovery monitoring with per-provider probes, remaining-quota checks, repeated-failure confirmation, alternate-WAN interlock, serialized actions, cooldowns, daily limits, persistent audit state, and optional authenticated HTTP(S) recovery endpoints for router helpers or smart plugs.

Automatic recovery is disabled by default and fails closed. A soft-reboot URL cannot
recover a router whose management plane is frozen; use a supported smart plug or
another independently powered recovery endpoint for hard power cycling. Never point
both providers at the same power-control endpoint.

## Screenshots

![WAN quota dashboard widgets](docs/screenshots/dashboard-widgets.png)

![Consumer and attributed-domain report](docs/screenshots/consumer-report.png)

![Data-source health report](docs/screenshots/data-health.png)

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

## License and provenance

BSD-2-Clause. The initial implementation and public-release hardening used
OpenAI Codex (GPT-5 family) under human review.
