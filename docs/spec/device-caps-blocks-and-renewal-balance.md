# Device quota caps, device internet blocks, and renewal-aware WAN balance

Specification for os-wanquota 0.18. Three features, one release.

1. **Device quota cap** — give a device a monthly data allowance and act when it
   is exceeded.
2. **Device internet block** — take a device off the internet now, permanently or
   until a deadline, while leaving it on the LAN.
3. **Renewal-aware WAN balance** — automatically send more traffic over whichever
   provider's allowance is closest to expiring unused, so allowance is not wasted.

The first two are policy applied to a host. The third is policy applied to a
link. All three share one rule: nothing changes traffic until it is switched on,
and everything that changes traffic is reversible by one command.

## Why these three, and what already existed

The plugin could already cap a device's *rate* (`device_limits_json`, ipfw pipes
through the traffic shaper) and could already compute which devices had exceeded a
*budget* (`device_policies_json` → `devices.py` → the `wanquota_over_budget` pf
table). Three things were missing, and they are the whole of this release:

| Wanted | Already there | Missing |
| --- | --- | --- |
| Cap a device's monthly data | budget arithmetic, pf table, external alias | a way to set the budget other than hand-written JSON; a firewall rule that makes the table block anything; anything that runs the evaluation on a schedule |
| Block a device from the internet | nothing | everything |
| Prefer the WAN closest to renewal | per-provider `remaining` and `days_left`; guardrails that *deprioritize on overuse* | anything that acts on *underuse*, which is the opposite problem |

The guardrails answer "this link is running out". Nothing answered "this link's
allowance is about to expire unspent", which on a two-provider household with
different billing days is the more common waste.

### The gap that made per-device budgets inert

`setup.php` created `wanquota_over_budget` as an external alias so it would appear
in the rule editor, and the documentation told the user to write the rule. Nobody
did, so a firewall with per-device enforcement switched on and dry-run off filled a
table that no rule consulted — enforcement that reported success and blocked
nothing. `monitor.py` also never called `devices.py`, so even the table was only
filled when someone pressed a button.

Both are fixed here. The rules are created by the plugin, over empty tables, which
changes no traffic on its own.

## Feature 1 — Device quota cap

### Model

No new field. Entries keep living in `device_policies_json`:

```json
[{"address": "192.168.1.20", "budget_gb": 50, "exclude": false},
 {"mac": "aa:bb:cc:dd:ee:ff", "budget_gb": 200}]
```

Reusing the field is deliberate. `intelligence.policy_index()` already indexes an
entry by address, MAC and DHCP hostname, and `intelligence.policy_for()` already
resolves a host through all three, so a budget set once keeps applying after DHCP
moves the device. A parallel field would have forked that identity handling, which
is the part that is easy to get wrong and already correct.

### Basis: calendar month, stated rather than implied

A device budget is evaluated against the **calendar month**, not against a
provider's billing cycle. With two providers on different cycle days there is no
single cycle a device's traffic belongs to — a device's bytes are split across both
links by the load balancer — so per-cycle device accounting would have to pick a
provider arbitrarily. The calendar month is the honest unit, and the interface
labels it "this month" rather than "this cycle".

### Enforcement

`devices.py` is unchanged in its arithmetic. What changes around it:

* `monitor.py` calls `devices.run("month")` every five minutes, so membership
  tracks usage instead of waiting for a button.
* `setup.php` creates the firewall rule that blocks the alias, so membership has
  an effect.
* A new read-only `devices.py state` prints the last plan without recomputing or
  applying, which is what the interface polls.

Safety is unchanged and is the reason the feature is usable: off by default,
dry-run by default when enabled, the router is never a member, devices marked
`exclude` are never members, members of a protected infrastructure group are never
members, membership is derived fresh and applied as one atomic `pfctl -T replace`,
and `devices.py flush` is the complete rollback.

### Interface

Limits gains a third sub-tab, **Quota & access**, listing every device the firewall
can name with:

* the monthly quota in GB (blank = no quota),
* what it has used this month and the percentage of its quota,
* whether it is currently in the over-budget table,
* the block controls from feature 2.

One **Save and apply** writes both quotas and blocks.

### API

`POST /api/wanquota/devicepolicy/set_quotas` — `quotas: [{device, budget_gb}]`.
`GET /api/wanquota/devicepolicy/get` — devices, quotas, month usage, table state.

Both live in a new `DevicePolicyController`, **not** under
`api/wanquota/report/*`. The read-only ACL privilege matches that path prefix and
is the credential an AI agent should hold; an endpoint that blocks a device must
not be reachable through it.

## Feature 2 — Device internet block

### Model

New field `device_blocks_json`:

```json
[{"device": "aa:bb:cc:dd:ee:ff", "until": 0, "reason": "homework"},
 {"device": "192.168.1.115", "until": 1787000000}]
```

`device` is an address, MAC or DHCP hostname, resolved the same way a rate limit
is. `until` is a Unix timestamp; `0` means indefinite. `reason` is free text shown
in the interface and the log.

A separate field from `device_policies_json` because the two have different
lifetimes and different authority: a budget is a standing rule evaluated against
measurements, a block is an act taken now. Storing them together would mean an
expiring block rewriting the file that holds budgets.

### A separate table, for a reason that would otherwise bite

Blocks get their own pf table and alias, `wanquota_blocked`. Sharing
`wanquota_over_budget` would break both features: `devices.py` replaces that
table's contents wholesale on every run, so every manual block would be erased
within five minutes, and a dry-run budget setting would silently disable manual
blocks that were never meant to be advisory.

### No dry-run, on purpose

Budget enforcement is dry-run by default because it acts on a *prediction* the user
has not yet learned to trust. A block is not a prediction. Someone who ticks
"block this device" has already decided, and a dry-run that recorded the intent
without blocking would be a feature that lies. The safety here is that it is
per-device, explicit, visible, and one click to undo.

The refusals still stand, and they are the same three that protect the budget
path: the firewall itself is never blocked, a device marked `exclude` is never
blocked, and a member of a protected infrastructure group is never blocked. Each
refusal is reported with its reason rather than dropped.

### What "blocked from the internet" means precisely

The rule is `block in on <LAN> from <wanquota_blocked> to !<LAN net>`, **first** in
the LAN rule list. So:

* Internet access stops.
* LAN-to-LAN traffic is untouched — the destination is excluded, and most of it is
  switched and never reaches the firewall anyway.
* DNS and NTP served *by the firewall* keep working, because the firewall's own LAN
  address is inside the LAN network. Without that, a blocked device would sit there
  with a broken clock and a resolver timeout as well.

This is the same shape as the existing `block-cameras-wan.php` in the home-network
repository, which was written by hand for exactly this need and is what the feature
generalises.

Two placements were rejected. An outbound rule on the WAN interface cannot work at
all: outbound WAN rules see the post-NAT source address, so a rule naming an internal
address never matches. Appending the LAN rule rather than putting it first was the
first implementation here, on the reasoning that the negated destination made position
irrelevant — **and it was wrong, measured on the target firewall**. OPNsense emits
administrator pass rules as pf `quick` rules, so the pre-existing
`pass in quick on em0 from <MY_DEVICES> to any` matched first and the appended block
showed `Evaluations: 0` while the blocked device browsed normally. Being first is what
makes a block mean anything; the negated destination is what makes being first safe,
because every rule a block must not override addresses the firewall itself.

### Expiry

`blocks.py run` drops entries whose `until` has passed and rewrites the table, so
an expiring block is released by the same five-minute pass that enforces one. An
expired entry is removed from the configuration on that pass rather than left as
stale JSON.

### API

`POST /api/wanquota/devicepolicy/set_blocks` — `blocks: [{device, until, reason}]`.
`POST /api/wanquota/devicepolicy/unblock_all` — the panic button; flushes the table
and empties the field.

## Feature 3 — Renewal-aware WAN balance

### The problem, stated as arithmetic

Two providers, one household:

| | ETISALAT | MOBINIL |
| --- | --- | --- |
| Quota | 225 GB | 400 GB |
| Renews | day 1 | day 15 |

On the 25th, ETISALAT has 6 days left and MOBINIL has 20. If ETISALAT has 90 GB
unused it must move 15 GB/day to spend it; if MOBINIL has 300 GB unused it needs
15 GB/day too — they are balanced. But on the 29th, ETISALAT has 2 days and 60 GB
(30 GB/day) while MOBINIL has 16 days and 250 GB (15.6 GB/day): ETISALAT's
allowance is twice as urgent, and every gigabyte the household sends over MOBINIL
instead is a gigabyte ETISALAT will never get back.

So the quantity to equalise is **headroom per remaining day**:

```
urgency = max(0, remaining - reserve) / max(1, days_left)
```

`remaining` and `days_left` are already computed by `report.provider_summary()`
against the provider's own cycle day, so the arithmetic needs no new measurement.
`reserve` is the existing `emergency_reserve_gb`, held back so the balancer never
spends the buffer the guardrails depend on.

### From urgency to weights

OPNsense distributes a gateway group's traffic by integer weight, 1–10, among
members of the same tier. So:

```
weight(p) = max(1, round(urgency(p) / max_urgency * balance_max_weight))
```

The floor of 1 is not a rounding artefact, it is policy: the balancer's job is to
shift the *ratio*, never to starve a link. Taking a link out of service is the
guardrail's decision, expressed through `force_down` and tier moves, and the
balancer must not reach for it by writing a weight of zero.

If every provider's urgency is zero — everything exhausted, or nothing measured —
all weights go to 1 and the group is back to equal sharing. Doing nothing is a
worse answer than doing that: it would leave whatever ratio the last run happened
to write.

### Drain mode: the case weights cannot reach

Weights change a ratio. Some situations have no good ratio: if a provider's headroom
per remaining day exceeds total household demand, then no share short of *all* the
traffic exhausts its allowance, and every gigabyte sent elsewhere is one that expires.
Sharing is then the thing doing the damage.

Drain mode makes that provider the sole first-tier member and demotes the others to
the second tier as live failover. The trigger is derived rather than configured:

> engage when `urgency >= household daily rate`, where the household rate is the sum
> of every provider's measured daily average.

Nothing is scheduled and no threshold is tuned. Release follows from the same
inequality: at cycle renewal the allowance resets and `urgency` collapses, so the
condition fails and the tiers go back. A release band (engage at the rate, release at
0.9 × the rate) stops a provider sitting exactly on the boundary from engaging and
releasing on alternating runs.

Two failure modes were found by testing rather than reasoning, and both are now
covered:

* **Release must undo, not merely stop proposing.** The first implementation computed
  no tier moves once the condition lapsed, which left the group concentrated on one
  link for ever. Releasing now actively restores the recorded original layout, and
  turning drain mode off releases too.
* **The plan must be written before it is applied.** `balance.php` reads the plan from
  disk, so writing it after applying made the shim act on the previous run's plan. It
  looked correct because consecutive runs usually agree — and failed exactly when the
  answer changed, applying nothing while reporting "already match".

**The floor guard, and why it is not rate arithmetic.** `urgency >= demand` already
implies the allowance cannot be exhausted: carrying everything for `days_left` costs
`demand × days_left`, which the inequality says is less than `remaining − reserve`.
That proof is only as good as `demand`, and `demand` is a lagging average over
measured days — a household that doubles its usage today does not appear in it until
tomorrow. So drain carries a second condition with no rate term in it: **a provider at
or past the guardrail's failover threshold (`guardrail_thresholds[2]`, 90% by default)
is never a drain target.** It overrides the release band, so an engaged drain lets go
rather than holding on while the link fills. Ruling one provider out does not rule out
concentrating on another.

Drain refuses to act while any provider is under guardrail action, refuses to promote
a link that is down, refuses to run with fewer than two usable providers, refuses when
there is no measured demand to compare against, refuses any provider past the floor
guard, and refuses any layout that would leave the first tier empty.

### Weights, not tiers, outside drain mode

Moving a gateway to a lower tier is failover: the lower tier idles until the upper
one fails. That is the waste this feature exists to end, so the balancer never
touches tiers or `force_down`. Those stay the guardrails' levers, which gives a
clean precedence rule:

> **A provider the guardrail has moved to failover or cut off is excluded from the
> balance.** Its weight is left at 1 and the remaining providers are balanced
> among themselves.

Overuse beats underuse. A link that is nearly out of allowance must not be sent
more traffic because its allowance expires soon — those two facts point the same
way only by coincidence, and the guardrail's answer is the safe one.

### How the weight is written

`report.provider_summary()` gives a provider's **logical interface** (`wan`,
`opt1`). A gateway is matched to a provider by that interface plus
`ipprotocol == inet`, never by matching gateway names against provider names: the
`ETISALAT_DHCP` convention is a habit, not a guarantee, and a rename would
silently point the balancer at the wrong link.

On the target firewall both gateways are DHCP-dynamic and both already carry a
`gateway_item` in `//OPNsense/Gateways` (weights 3 and 1), because configuring
monitoring created them. Where an item does not exist, `balance.php` creates one
through `Gateways::createOrUpdateGateway()` — the same call the GUI makes when a
dynamic gateway is given settings — and records that it did, so reverting deletes
the item rather than restoring a field that never existed.

Original weights are recorded once, before the first change, in
`/var/db/wanquota/gateway-weights.json`. `balance.php revert` puts them back.

### Known behaviour change

`enforce.php` iterates `gateway_item`, so on a firewall with only dynamic
gateways and no items, the guardrails were an error rather than an action. Any
firewall where the balancer creates items therefore gains working guardrails at
the same moment. This is the intended end state and it is documented here so it is
not discovered as a surprise in production.

### Only when it changes

Weights are integers and are compared before anything is written. A run that
computes the same weights makes no config change, no `Config::save()`, and no
filter reload. This is the hysteresis: without it a five-minute cron would rewrite
the configuration 288 times a day and reload the firewall each time, for a ratio
that had not moved.

### Model

| Field | Default | Meaning |
| --- | --- | --- |
| `balance_enabled` | `0` | Compute and act. Off, like everything that changes traffic. |
| `balance_dry_run` | `1` | Compute and record the plan; write nothing. |
| `balance_group` | `` | Gateway group to balance. Empty auto-detects the only group; required when there is more than one. |
| `balance_max_weight` | `10` | The weight the most urgent provider receives. Lower it to soften the ratio. |

### Interface

The Intelligence tab gains a **Renewal-aware WAN balance** panel: per provider the
remaining allowance, days to renewal, GB/day of headroom, the current gateway
weight and the computed one, with the switches and an **Apply now** button. When a
provider is excluded because the guardrail failed it over or cut it off, the panel
says so on that provider's row instead of showing a weight the balancer will not
write.

### API

`GET /api/wanquota/balance/get`, `POST /api/wanquota/balance/set`
(enabled, dry_run, max_weight, group), `POST /api/wanquota/balance/apply`.
`BalanceController`, again outside `api/wanquota/report/*`.

## Scheduling

`monitor.py`, on the existing five-minute cron, gains three steps after the
intelligence snapshot, each independently guarded so one failure cannot stop the
others:

1. `blocks.run()` — enforce and expire manual blocks.
2. `devices.run("month")` — recompute over-budget membership.
3. `balance.run()` — recompute weights, and apply when enabled and not dry-run.

Blocks run first. An explicit block should not wait behind a budget recomputation
that reads several databases.

## Firewall rules created at install

`setup.php` creates, idempotently:

* the `wanquota_blocked` external alias, alongside the existing
  `wanquota_over_budget`;
* one LAN block rule per alias, inserted at the **front** of the rule list. Any
  previous copy is removed first, wherever it sits, so a firewall upgraded from a
  build that appended them has its placement repaired rather than skipped.

Both tables are empty at creation, so both rules are live and match nothing. This
is the same argument `setup.php` already makes for creating the alias: creating it
changes no traffic, and not creating it makes the feature silently inert.

`teardown.php` removes both rules and flushes both tables. A device left blocked by
a rule whose owner has been uninstalled is the one uninstall outcome that must not
happen.

## Tests

Pure functions, tested without pf, a firewall, or a config:

* `blocks.members()` — matching by address/MAC/hostname, expiry, the router
  refusal, the exclude refusal, the protected-group refusal, a non-literal
  address, duplicate entries.
* `balance.urgency()` / `balance.weights()` — the ratio, the reserve subtraction,
  the floor of 1, the all-zero case, guardrail exclusion, `max_weight` scaling,
  and that equal urgency yields equal weights.
* `balance.gateway_for()` — interface-and-protocol matching, and that a name
  collision does not decide it.
* Existing `test_devices.py` continues to cover budget membership.

`make test` must be green before packaging.

## Making a block take effect on an open connection

A firewall rule governs new connections. pf consults its state table first, so a
device holding an established connection keeps using it after being blocked — the
rule is evaluated and never matches.

This is not a corner case for the devices most worth blocking. Measured on the target
firewall: an ESP32 holding a single long-lived TCP session to its vendor's cloud kept
using it while the block rule sat at **0 packets matched after 23,000 evaluations**.
An IoT device that opens one session and never needs another is never blocked at all.

So adding an address to either table now kills that address's states, and only for
addresses **newly** added. Killing on every pass would tear down the device's *local*
connections every five minutes for as long as the block lasted — those are permitted
and would re-establish immediately, but repeatedly resetting them is not what was
asked for. Releasing kills nothing: a device being let back on should have its traffic
resume, and there is nothing the rule was stopping.

One remnant is left behind by design. `pfctl -k <address>` matches states by the
addresses pf holds, and a NAT state records the internal address only as the
translation, so the post-NAT half of an existing conversation survives. It carries
nothing — the device's own packets are dropped at the LAN interface before NAT, which
is what the rising rule counter shows — and it expires on its own. Killing it would
mean matching on the NAT address pair, which is shared, and could tear down an
unrelated device's connection to the same destination.

## Not in this release

* **MCP tools** for blocking a device and setting a device quota. The parity is
  obvious and the plumbing exists, but the request did not ask for it and every
  MCP write tool needs its own refusal semantics. Follow-up.
* **Per-cycle device accounting.** Deliberate, argued above.
* **Category or schedule-based blocks** ("no YouTube after 22:00"). The shaper
  already caps a service; a time-of-day block is a different feature.
* **Balancing more than one gateway group.** `balance_group` names one.
