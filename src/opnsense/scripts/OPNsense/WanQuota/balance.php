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
 * Three modes:
 *
 *   inventory  Report gateways and groups as the firewall sees them, dynamic
 *              gateways included. A DHCP gateway may have no gateway_item at all,
 *              and it is still a member of a group and still carries a weight, so
 *              reading only the configured items would report an empty firewall.
 *   apply      Write the weights in the plan, but only the ones that differ.
 *   revert     Put the original weights back, deleting any item this created.
 *
 * Only `weight` is ever written. Tiers and force_down belong to the guardrails —
 * balance.py's whole safety argument rests on this file not touching them.
 */

require_once 'config.inc';
require_once 'util.inc';
require_once 'filter.inc';
require_once 'interfaces.inc';

use OPNsense\Core\Config;
use OPNsense\Routing\Gateways;

const PLAN_PATH = '/var/db/wanquota/balance-plan.json';
const ORIGINALS_PATH = '/var/db/wanquota/gateway-weights.json';

function fail(string $message): void
{
    echo json_encode(['status' => 'failed', 'error' => $message]) . PHP_EOL;
    exit(1);
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
    return ['status' => 'ok', 'gateways' => $gateways, 'groups' => $groups];
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
    return ['status' => 'ok', 'changed' => count($written), 'written' => $written];
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
            'restored' => $restored, 'removed' => $removed];
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
    case 'revert':
        echo json_encode(revert()) . PHP_EOL;
        break;
    default:
        fail('Unknown mode: ' . $mode);
}
