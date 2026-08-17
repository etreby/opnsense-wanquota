#!/usr/local/bin/php
<?php

/*
 * Apply the per-service bandwidth plan to the OPNsense traffic shaper.
 *
 * The plan is computed in shaper.py; this only writes it into the TrafficShaper
 * model and asks OPNsense to reload. Going through the model rather than calling
 * ipfw directly is deliberate and not merely tidy: ipfw is not loaded on a stock
 * system, and loading it by hand installs a default deny rule that would cut all
 * traffic. OPNsense brings it up through the system's own rc scripts, which set
 * the accept default and synchronise the pf/ipfw load order. Only that path is
 * safe.
 *
 * Everything this creates is tagged with origin=wanquota, so a sync can replace
 * exactly what the plugin owns and never disturb a hand-made pipe or rule.
 */

require_once 'config.inc';
require_once 'util.inc';

const ORIGIN = 'wanquota';
const PLAN = '/var/db/wanquota/shaper-plan.json';

$mode = $argv[1] ?? 'apply';

$model = new OPNsense\TrafficShaper\TrafficShaper();

/* Remove only what previous runs created. */
$removed = 0;
foreach (['rules' => 'rule', 'pipes' => 'pipe'] as $set => $item) {
    $uuids = [];
    foreach ($model->$set->$item->iterateItems() as $node) {
        if ((string)$node->origin === ORIGIN) {
            $uuids[] = $node->getAttributes()['uuid'];
        }
    }
    foreach ($uuids as $uuid) {
        if ($model->$set->$item->del($uuid)) {
            $removed++;
        }
    }
}

if ($mode === 'flush') {
    $model->serializeToConfig();
    OPNsense\Core\Config::getInstance()->save('Remove WAN quota per-service bandwidth limits');
    (new OPNsense\Core\Backend())->configdRun('ipfw reload');
    echo json_encode(['status' => 'ok', 'removed' => $removed]) . PHP_EOL;
    exit(0);
}

$plan = @json_decode((string)@file_get_contents(PLAN), true);
if (!is_array($plan)) {
    fwrite(STDERR, "No usable plan at " . PLAN . "; run shaper.py first\n");
    exit(1);
}
if (($plan['status'] ?? '') !== 'ok' || !empty($plan['dry_run'])) {
    // Nothing to apply: either disabled, or a dry run whose whole purpose is to
    // change nothing. The removal above still runs, so turning the feature off or
    // switching to dry-run releases any limit already in place.
    $model->serializeToConfig();
    OPNsense\Core\Config::getInstance()->save('WAN quota per-service limits released');
    (new OPNsense\Core\Backend())->configdRun('ipfw reload');
    echo json_encode([
        'status' => $plan['status'] ?? 'unknown',
        'applied' => 0,
        'removed' => $removed,
        'dry_run' => !empty($plan['dry_run']),
    ]) . PHP_EOL;
    exit(0);
}

$applied = [];
$errors = [];
foreach ($plan['pipes'] ?? [] as $entry) {
    $pipe = $model->pipes->pipe->Add();
    $pipe->number = (string)$entry['pipe'];
    $pipe->enabled = '1';
    $pipe->bandwidth = (string)$entry['mbit'];
    $pipe->bandwidthMetric = 'Mbit';
    /*
     * Mask on the destination address so the cap applies per device rather than
     * to the service as a whole. Without it two televisions share one pipe and
     * both degrade, which reads as the limit being set too low.
     */
    $pipe->mask = 'dst-ip';
    $pipe->description = sprintf('WAN quota: %s limited to %s Mbit/s', $entry['label'], $entry['mbit']);
    $pipe->origin = ORIGIN;

    $rule = $model->rules->rule->Add();
    $rule->enabled = '1';
    $rule->sequence = (string)$entry['pipe'];
    $rule->interface = 'lan';
    /*
     * Matching on the LAN in the inbound direction catches the download side for
     * every provider at once. A rule per WAN would have to be kept in step with
     * the provider list, and would miss traffic on a provider not yet configured.
     */
    $rule->direction = 'in';
    $rule->proto = 'ip';
    $rule->source = implode(',', $entry['addresses']);
    $rule->destination = 'any';
    $rule->target = (string)$pipe->getAttributes()['uuid'];
    $rule->description = sprintf('WAN quota: %s', $entry['label']);
    $rule->origin = ORIGIN;

    $applied[] = ['service' => $entry['service'], 'mbit' => $entry['mbit'],
                  'addresses' => $entry['address_count']];
}

$messages = $model->performValidation();
if (count($messages) > 0) {
    foreach ($messages as $message) {
        $errors[] = (string)$message;
    }
    fwrite(STDERR, "Validation failed; no change made:\n  " . implode("\n  ", $errors) . "\n");
    exit(1);
}

$model->serializeToConfig();
OPNsense\Core\Config::getInstance()->save('Apply WAN quota per-service bandwidth limits');
(new OPNsense\Core\Backend())->configdRun('ipfw reload');

echo json_encode([
    'status' => 'ok',
    'applied' => $applied,
    'removed' => $removed,
    'rejected' => $plan['rejected'] ?? [],
]) . PHP_EOL;
