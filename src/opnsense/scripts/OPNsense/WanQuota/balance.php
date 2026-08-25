#!/usr/local/bin/php
<?php

/*
 * Write the gateway weights the renewal-aware balancer computed.
 *
 * The arithmetic lives in balance.py, where it is pure and tested. This is the
 * part that cannot be: gateways live in the OPNsense Gateways model, and going
 * through the model is what validates a change and reloads the routing safely.
 * Editing config.xml by hand would skip both.
 *
 * Modes:
 *
 *   inventory  Report gateways and groups as the firewall sees them, dynamic
 *              gateways included. A DHCP gateway may have no gateway_item at all,
 *              and it is still a member of a group and still carries a weight, so
 *              reading only the configured items would report an empty firewall.
 *   apply      Write the weights in the plan, but only the ones that differ.
 *   tiers      Move gateways between tiers so one provider carries everything.
 *              Only reached in drain mode, and only when the plan says so.
 *   tierrelease Put the tiers back, leaving weights alone. This is how a drain
 *              lets go — releasing has to undo a change, not merely stop asking
 *              for one.
 *   check      What apply would write, writing nothing.
 *   tiercheck  What tiers would write, writing nothing.
 *   revert     Put the original tiers and weights back, deleting any gateway item
 *              this created. Tiers first: a revert that restored weights and then
 *              failed on tiers would leave the household concentrated on one link
 *              with the ratio undone.
 *
 * `force_down` is never written by this file. Drain decides which link is
 * *preferred*; taking a link out of service stays the guardrails' decision, and a
 * demoted gateway remains a live failover.
 */

require_once 'config.inc';
require_once 'util.inc';
require_once 'filter.inc';
require_once 'interfaces.inc';

use OPNsense\Core\Config;
use OPNsense\Routing\Gateways;

const PLAN_PATH = '/var/db/wanquota/balance-plan.json';
const ORIGINALS_PATH = '/var/db/wanquota/gateway-weights.json';
/*
 * Tier originals live in their own file, not in enforce.php's gateway-originals.json.
 * The guardrail owns tiers when it is acting and the balancer stands down then, so the
 * two never write at the same time — but they must not share a record of "before"
 * either, or whichever reverted second would restore the other's snapshot.
 */
const TIERS_PATH = '/var/db/wanquota/gateway-tiers.json';
const TIERS = ['item', 'item2', 'item3', 'item4', 'item5'];

function fail(string $message): void
{
    echo json_encode(['status' => 'failed', 'error' => $message]) . PHP_EOL;
    exit(1);
}

/**
 * Tell the resolver its upstreams may be reachable again.
 *
 * Changing routing reloads the filter, and a filter reload can drop long-lived TCP.
 * A DNS-over-TLS session is exactly that, so Unbound's upstream connections are
 * collateral damage of a weight or tier change. Unbound then does the sensible thing
 * for a real outage and the wrong thing here: it backs the upstream off, up to a
 * retransmit timeout of 120 seconds, and does not retry until that expires. Observed
 * on a live firewall: SERVFAIL for every external name while a raw TCP connect to the
 * same upstream on port 853 succeeded and plain UDP 53 answered. DNS stayed dead for
 * minutes after the cause had passed.
 *
 * `flush_infra` clears only the reachability and round-trip bookkeeping, so the next
 * query tries the upstream again. It deliberately does *not* flush the answer cache:
 * discarding valid answers would turn one routing change into a lookup storm.
 *
 * Best-effort by design. A firewall may not run Unbound at all, and a resolver that
 * cannot be nudged is no reason to fail a routing change already written.
 */
function nudgeResolver(): array
{
    $control = '/usr/local/sbin/unbound-control';
    $config = '/var/unbound/unbound.conf';
    if (!is_executable($control) || !is_file($config)) {
        return ['nudged' => false, 'reason' => 'unbound-control is not available here'];
    }
    $output = [];
    $status = 0;
    exec(sprintf('%s -c %s flush_infra all 2>&1',
        escapeshellarg($control), escapeshellarg($config)), $output, $status);
    return ['nudged' => $status === 0,
            'reason' => $status === 0 ? 'upstream reachability reset' : trim(implode(' ', $output))];
}

/**
 * Every gateway the firewall knows, with whether it has a configuration item.
 *
 * getGateways() merges configured items with the dynamic ones discovered from
 * interfaces, which is the only view that matches what a gateway group can
 * actually reference.
 */
function inventory(): array
{
    $model = new Gateways();
    $configured = [];
    foreach ($model->gateway_item->iterateItems() as $item) {
        $configured[(string)$item->name] = $item->getAttributes()['uuid'] ?? '';
    }
    $gateways = [];
    foreach ($model->getGateways() as $gateway) {
        $name = (string)($gateway['name'] ?? '');
        if ($name === '' || !empty($gateway['virtual'])) {
            continue;
        }
        $gateways[] = [
            'name' => $name,
            'interface' => (string)($gateway['interface'] ?? ''),
            'ipprotocol' => (string)($gateway['ipprotocol'] ?? 'inet'),
            'weight' => (int)($gateway['weight'] ?? 1),
            'disabled' => empty($gateway['disabled']) ? '0' : '1',
            'dynamic' => empty($gateway['dynamic']) ? false : true,
            /* False means applying a weight has to create the item first. */
            'configured' => isset($configured[$name]),
            'uuid' => $configured[$name] ?? '',
        ];
    }
    $groups = [];
    foreach (Config::getInstance()->object()->gateways->gateway_group as $group) {
        $tiers = [];
        $members = [];
        foreach (['item', 'item2', 'item3', 'item4', 'item5'] as $tier) {
            $names = array_values(array_filter(array_map('trim', explode(',', (string)$group->{$tier}))));
            $tiers[$tier] = $names;
            $members = array_merge($members, $names);
        }
        $groups[] = [
            'name' => (string)$group->name,
            'members' => $members,
            'tiers' => $tiers,
            'poolopts' => (string)$group->poolopts,
        ];
    }
    /*
     * Whether a drain is currently in force. balance.py needs this to know that
     * releasing requires *undoing* something rather than merely not proposing it:
     * without it, a released drain simply stopped asking for a tier move and the
     * group stayed concentrated on one link for ever.
     */
    return ['status' => 'ok', 'gateways' => $gateways, 'groups' => $groups,
            'drained' => is_file(TIERS_PATH)];
}

function loadOriginals(): array
{
    $state = is_file(ORIGINALS_PATH) ? json_decode(file_get_contents(ORIGINALS_PATH), true) : [];
    return is_array($state) ? $state : [];
}

function saveOriginals(array $state): void
{
    if (!is_dir(dirname(ORIGINALS_PATH))) {
        mkdir(dirname(ORIGINALS_PATH), 0750, true);
    }
    file_put_contents(ORIGINALS_PATH, json_encode($state, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES), LOCK_EX);
    chmod(ORIGINALS_PATH, 0600);
}

/** Write one gateway's weight, creating the item when the gateway is purely dynamic. */
function setWeight(Gateways $model, array $gateway, int $weight): void
{
    if (!empty($gateway['uuid'])) {
        $node = $model->getNodeByReference('gateway_item.' . $gateway['uuid']);
        if ($node !== null) {
            $node->weight = (string)$weight;
            return;
        }
    }
    /*
     * No item exists, so the gateway is dynamic and has never been given settings.
     * createOrUpdateGateway is the same call the GUI makes in that situation; the
     * empty `gateway` field is what marks it dynamic.
     */
    $model->createOrUpdateGateway([
        'name' => $gateway['name'],
        'interface' => $gateway['interface'],
        'ipprotocol' => $gateway['ipprotocol'],
        'weight' => (string)$weight,
        'descr' => 'Created by os-wanquota to carry a renewal-aware weight',
    ]);
}

/**
 * Move gateways between tiers so one provider carries everything.
 *
 * Only tiers. force_down is never touched here: drain decides which link is
 * *preferred*, while taking a link out of service stays the guardrail's decision. A
 * demoted gateway remains a live failover and takes over within seconds if the
 * primary drops.
 */
function applyTiers(bool $checkOnly): array
{
    $plan = is_file(PLAN_PATH) ? json_decode(file_get_contents(PLAN_PATH), true) : null;
    if (!is_array($plan)) {
        fail('No balance plan has been computed yet');
    }
    if (!empty($plan['problems'])) {
        fail('The plan cannot be applied: ' . implode('; ', $plan['problems']));
    }
    $moves = $plan['tiers']['moves'] ?? [];
    $groupName = (string)($plan['group'] ?? '');
    if (empty($moves)) {
        return ['status' => 'ok', 'changed' => 0, 'note' => 'Tiers already match the plan.'];
    }
    if ($groupName === '') {
        fail('The plan names no gateway group, so no tier can be written');
    }
    $wanted = $plan['tiers']['wanted'] ?? [];
    /*
     * Refuse to write a layout with an empty first tier. A gateway group whose top
     * tier holds nothing is a group with no primary, and this is the one mistake in
     * the feature that would take the household off the internet rather than merely
     * route it badly.
     */
    if (!in_array('item', array_values($wanted), true)) {
        fail('Refused: the plan would leave the first tier empty');
    }

    $configObject = Config::getInstance()->object();
    $target = null;
    foreach ($configObject->gateways->gateway_group as $group) {
        if ((string)$group->name === $groupName) {
            $target = $group;
            break;
        }
    }
    if ($target === null) {
        fail(sprintf('This firewall has no gateway group called %s', $groupName));
    }

    $state = is_file(TIERS_PATH) ? json_decode(file_get_contents(TIERS_PATH), true) : [];
    $state = is_array($state) ? $state : [];
    if (!isset($state[$groupName])) {
        /* Record the layout once, before the first change, so revert is exact. */
        $before = [];
        foreach (TIERS as $tier) {
            $before[$tier] = (string)$target->{$tier};
        }
        $state[$groupName] = $before;
    }
    if ($checkOnly) {
        return ['status' => 'ok', 'check_only' => true, 'changed' => count($moves),
                'moves' => $moves, 'group' => $groupName];
    }

    writeTiers($target, $wanted);
    $messages = (new Gateways())->performValidation();
    if (count($messages) > 0) {
        $problems = [];
        foreach ($messages as $message) {
            $problems[] = (string)$message;
        }
        fail('The gateway model refused the tier change: ' . implode('; ', $problems));
    }
    Config::getInstance()->save(sprintf('WAN quota drain: %s carries the traffic',
        $plan['drain']['target'] ?? 'one provider'));
    if (!is_dir(dirname(TIERS_PATH))) {
        mkdir(dirname(TIERS_PATH), 0750, true);
    }
    file_put_contents(TIERS_PATH, json_encode($state, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES), LOCK_EX);
    chmod(TIERS_PATH, 0600);
    if (function_exists('system_routing_configure')) {
        system_routing_configure();
    }
    filter_configure();
    return ['status' => 'ok', 'changed' => count($moves), 'moves' => $moves,
            'group' => $groupName, 'resolver' => nudgeResolver()];
}

/** Rewrite a group's tiers from a gateway => tier map, dropping empty members. */
function writeTiers($group, array $wanted): void
{
    $byTier = array_fill_keys(TIERS, []);
    /* Anything in the group that the plan does not mention keeps the tier it has. */
    foreach (TIERS as $tier) {
        foreach (array_filter(array_map('trim', explode(',', (string)$group->{$tier}))) as $name) {
            if (!isset($wanted[$name])) {
                $byTier[$tier][] = $name;
            }
        }
    }
    foreach ($wanted as $name => $tier) {
        if (isset($byTier[$tier])) {
            $byTier[$tier][] = $name;
        }
    }
    foreach (TIERS as $tier) {
        $group->{$tier} = implode(',', array_values(array_unique(array_filter($byTier[$tier]))));
    }
}

/** Put a group's tiers back exactly as they were before drain first engaged. */
function revertTiers(): array
{
    $state = is_file(TIERS_PATH) ? json_decode(file_get_contents(TIERS_PATH), true) : [];
    $state = is_array($state) ? $state : [];
    if (empty($state)) {
        return ['status' => 'ok', 'changed' => 0,
                'note' => 'No tier was ever changed, so there is nothing to put back.'];
    }
    $configObject = Config::getInstance()->object();
    $restored = [];
    foreach ($configObject->gateways->gateway_group as $group) {
        $name = (string)$group->name;
        if (!isset($state[$name])) {
            continue;
        }
        foreach (TIERS as $tier) {
            $group->{$tier} = (string)($state[$name][$tier] ?? '');
        }
        $restored[] = $name;
    }
    $messages = (new Gateways())->performValidation();
    if (count($messages) > 0) {
        $problems = [];
        foreach ($messages as $message) {
            $problems[] = (string)$message;
        }
        fail('The gateway model refused the tier revert: ' . implode('; ', $problems));
    }
    Config::getInstance()->save('Revert WAN quota drain: restore the original gateway tiers');
    @unlink(TIERS_PATH);
    if (function_exists('system_routing_configure')) {
        system_routing_configure();
    }
    filter_configure();
    return ['status' => 'ok', 'changed' => count($restored), 'groups' => $restored,
            'resolver' => nudgeResolver()];
}

function apply(bool $checkOnly): array
{
    $plan = is_file(PLAN_PATH) ? json_decode(file_get_contents(PLAN_PATH), true) : null;
    if (!is_array($plan)) {
        fail('No balance plan has been computed yet');
    }
    if (!empty($plan['problems'])) {
        fail('The plan cannot be applied: ' . implode('; ', $plan['problems']));
    }
    $changes = $plan['changes'] ?? [];
    if (empty($changes)) {
        return ['status' => 'ok', 'changed' => 0, 'note' => 'Weights already match the plan.'];
    }

    $current = inventory();
    $byName = [];
    foreach ($current['gateways'] as $gateway) {
        $byName[$gateway['name']] = $gateway;
    }

    $model = new Gateways();
    $originals = loadOriginals();
    $written = [];
    foreach ($changes as $change) {
        $name = (string)($change['gateway'] ?? '');
        $target = (int)($change['to'] ?? 0);
        if ($name === '' || !isset($byName[$name])) {
            fail(sprintf('The plan names gateway %s, which this firewall does not have', $name ?: '(unnamed)'));
        }
        if ($target < 1 || $target > 10) {
            fail(sprintf('%s: weight %d is outside the 1-10 range the model allows', $name, $target));
        }
        $gateway = $byName[$name];
        /*
         * Record the original once, before the first change, and record whether the
         * item existed. Reverting a gateway that had no item means deleting the item
         * rather than restoring a field that was never there.
         */
        if (!isset($originals[$name])) {
            $originals[$name] = [
                'weight' => (string)$gateway['weight'],
                'existed' => $gateway['configured'],
            ];
        }
        if ((int)$gateway['weight'] === $target) {
            continue;
        }
        if (!$checkOnly) {
            setWeight($model, $gateway, $target);
        }
        $written[] = ['gateway' => $name, 'from' => (int)$gateway['weight'], 'to' => $target];
    }

    if (empty($written)) {
        return ['status' => 'ok', 'changed' => 0, 'note' => 'Weights already match the plan.'];
    }

    $messages = $model->performValidation();
    if (count($messages) > 0) {
        $problems = [];
        foreach ($messages as $message) {
            $problems[] = (string)$message;
        }
        fail('The gateway model refused the change: ' . implode('; ', $problems));
    }
    if ($checkOnly) {
        return ['status' => 'ok', 'check_only' => true, 'changed' => count($written),
                'written' => $written];
    }

    $model->serializeToConfig();
    Config::getInstance()->save('WAN quota renewal-aware gateway weights');
    saveOriginals($originals);
    /*
     * A weight only takes effect once the routing tables and the filter are rebuilt.
     * system_routing_configure() rewrites the gateway groups pf uses for
     * route-to/load-balancing; filter_configure() then reloads the rules that
     * reference them.
     */
    if (function_exists('system_routing_configure')) {
        system_routing_configure();
    }
    filter_configure();
    return ['status' => 'ok', 'changed' => count($written), 'written' => $written,
            'resolver' => nudgeResolver()];
}

function revert(): array
{
    $originals = loadOriginals();
    if (empty($originals)) {
        return ['status' => 'ok', 'changed' => 0,
                'note' => 'No weight was ever changed, so there is nothing to put back.'];
    }
    $model = new Gateways();
    $restored = [];
    $removed = [];
    foreach ($model->gateway_item->iterateItems() as $item) {
        $name = (string)$item->name;
        if (!isset($originals[$name])) {
            continue;
        }
        if (empty($originals[$name]['existed'])) {
            /* This plugin created the item; reverting means removing it. */
            $removed[] = $name;
            continue;
        }
        $item->weight = (string)$originals[$name]['weight'];
        $restored[] = ['gateway' => $name, 'weight' => (string)$originals[$name]['weight']];
    }
    foreach ($removed as $name) {
        foreach ($model->gateway_item->iterateItems() as $item) {
            if ((string)$item->name === $name) {
                $model->gateway_item->del($item->getAttributes()['uuid']);
                break;
            }
        }
    }
    $messages = $model->performValidation();
    if (count($messages) > 0) {
        $problems = [];
        foreach ($messages as $message) {
            $problems[] = (string)$message;
        }
        fail('The gateway model refused the revert: ' . implode('; ', $problems));
    }
    $model->serializeToConfig();
    Config::getInstance()->save('Revert WAN quota renewal-aware gateway weights');
    @unlink(ORIGINALS_PATH);
    if (function_exists('system_routing_configure')) {
        system_routing_configure();
    }
    filter_configure();
    return ['status' => 'ok', 'changed' => count($restored) + count($removed),
            'restored' => $restored, 'removed' => $removed,
            'resolver' => nudgeResolver()];
}

$mode = $argv[1] ?? 'inventory';
switch ($mode) {
    case 'inventory':
        echo json_encode(inventory()) . PHP_EOL;
        break;
    case 'check':
        echo json_encode(apply(true)) . PHP_EOL;
        break;
    case 'apply':
        echo json_encode(apply(false)) . PHP_EOL;
        break;
    case 'tiers':
        echo json_encode(applyTiers(false)) . PHP_EOL;
        break;
    case 'tierrelease':
        /* Put the tiers back and leave the weights alone: releasing a drain returns
           the group to sharing, which is still the balancer's to manage. */
        echo json_encode(revertTiers()) . PHP_EOL;
        break;
    case 'tiercheck':
        echo json_encode(applyTiers(true)) . PHP_EOL;
        break;
    case 'revert':
        /* Tiers first: a revert that restored weights and then failed on tiers would
           leave the household concentrated on one link with the ratio undone. */
        $tiers = revertTiers();
        $weights = revert();
        echo json_encode(['status' => 'ok', 'tiers' => $tiers, 'weights' => $weights]) . PHP_EOL;
        break;
    default:
        fail('Unknown mode: ' . $mode);
}
