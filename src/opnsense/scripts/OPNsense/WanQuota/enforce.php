#!/usr/local/bin/php
<?php

/* Apply an explicitly enabled, reversible gateway guardrail policy. */
require_once 'config.inc';
require_once 'util.inc';
require_once 'filter.inc';

use OPNsense\Core\Config;
use OPNsense\Routing\Gateways;

$logical = $argv[1] ?? '';
$action = $argv[2] ?? '';
$checkOnly = ($argv[3] ?? '') === 'check';
if (!preg_match('/^[a-zA-Z0-9_]+$/', $logical) || !in_array($action, ['observe', 'deprioritize', 'failover', 'cutoff'], true)) {
    fwrite(STDERR, "Invalid enforcement request\n");
    exit(1);
}

$statePath = '/var/db/wanquota/gateway-originals.json';
$state = is_file($statePath) ? json_decode(file_get_contents($statePath), true) : [];
$state = is_array($state) ? $state : [];
$gateways = new Gateways();
$configObject = Config::getInstance()->object();
$matched = [];

foreach ($gateways->gateway_item->iterateItems() as $gateway) {
    if ((string)$gateway->interface !== $logical) {
        continue;
    }
    $name = (string)$gateway->name;
    $matched[] = $name;
    if (!isset($state[$name])) {
        $state[$name] = ['weight' => (string)$gateway->weight, 'force_down' => (string)$gateway->force_down, 'groups' => []];
        foreach ($configObject->gateways->gateway_group as $group) {
            foreach (['item', 'item2', 'item3', 'item4', 'item5'] as $tier) {
                $members = array_filter(explode(',', (string)$group->{$tier}));
                if (in_array($name, $members, true)) {
                    $state[$name]['groups'][(string)$group->name] = $tier;
                }
            }
        }
    }
    if ($action === 'observe') {
        $gateway->weight = $state[$name]['weight'];
        $gateway->force_down = $state[$name]['force_down'];
    } elseif ($action === 'cutoff') {
        $gateway->force_down = '1';
    } else {
        $gateway->force_down = '0';
        $gateway->weight = '1';
    }
}

if (empty($matched)) {
    fwrite(STDERR, "No gateway uses interface {$logical}\n");
    exit(1);
}

foreach ($configObject->gateways->gateway_group as $group) {
    foreach ($matched as $name) {
        $originalTier = $state[$name]['groups'][(string)$group->name] ?? null;
        if ($originalTier === null) continue;
        $target = $action === 'failover' ? 'item2' : $originalTier;
        foreach (['item', 'item2', 'item3', 'item4', 'item5'] as $tier) {
            $original = (string)$group->{$tier};
            $members = array_values(array_filter(explode(',', $original), fn($member) => $member !== $name));
            if ($target === $tier) {
                $members[] = $name;
            }
            $updated = implode(',', array_unique($members));
            if ($updated !== $original) $group->{$tier} = $updated;
        }
    }
}

$messages = $gateways->performValidation();
if (count($messages) > 0) {
    foreach ($messages as $message) fwrite(STDERR, (string)$message . PHP_EOL);
    exit(1);
}

if ($checkOnly) {
    echo json_encode(['status' => 'ok', 'check_only' => true, 'interface' => $logical, 'action' => $action, 'gateways' => $matched]) . PHP_EOL;
    exit(0);
}

$gateways->serializeToConfig();
Config::getInstance()->save("WAN quota guardrail: {$action} {$logical}");
if (!is_dir(dirname($statePath))) mkdir(dirname($statePath), 0750, true);
file_put_contents($statePath, json_encode($state, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES), LOCK_EX);
chmod($statePath, 0600);
filter_configure();
echo json_encode(['status' => 'ok', 'interface' => $logical, 'action' => $action, 'gateways' => $matched]) . PHP_EOL;
