#!/usr/local/bin/php
<?php

/*
 * Remove expired internet blocks from the configuration.
 *
 * blocks.py already stops enforcing an entry whose deadline has passed — the pf
 * table is rebuilt from scratch every run, so an expired block is released by the
 * same pass that would have enforced it. This deletes the entry as well, so the
 * interface does not list blocks that are not in force and a device blocked for an
 * evening does not carry a stale entry for as long as the plugin is installed.
 *
 * It is PHP rather than part of blocks.py because writing /conf/config.xml belongs
 * to the model. A Python script rewriting the XML it had just parsed would race
 * with anything else saving configuration.
 */

require_once 'config.inc';
require_once 'util.inc';

use OPNsense\Core\Config;
use OPNsense\WanQuota\WanQuota;

$action = $argv[1] ?? '';
$keys = array_slice($argv, 2);
if (!in_array($action, ['expire', 'expire-service'], true) || empty($keys)) {
    echo json_encode(['status' => 'failed',
                      'error' => 'usage: blocks.php <expire|expire-service> <key> [key...]']) . PHP_EOL;
    exit(1);
}

$model = new WanQuota();
$isService = ($action === 'expire-service');
$field = $isService ? 'service_blocks_json' : 'device_blocks_json';
$itemKey = $isService ? 'service' : 'device';

$blocks = json_decode((string)$model->general->$field, true);
$blocks = is_array($blocks) ? $blocks : [];

$wanted = [];
foreach ($keys as $key) {
    $wanted[strtolower(trim($key))] = true;
}

$kept = [];
$removed = [];
foreach ($blocks as $block) {
    $target = strtolower(trim((string)($block[$itemKey] ?? '')));
    /*
     * Only drop an entry that is both named in the request and genuinely expired.
     */
    $until = (int)($block['until'] ?? 0);
    if ($target !== '' && isset($wanted[$target]) && $until > 0 && $until <= time()) {
        $removed[] = $block;
        continue;
    }
    $kept[] = $block;
}

if (empty($removed)) {
    echo json_encode(['status' => 'ok', 'removed' => 0,
                      'note' => 'Nothing was expired at the time of writing.']) . PHP_EOL;
    exit(0);
}

$model->general->$field = json_encode($kept);
$messages = $model->performValidation();
if (count($messages) > 0) {
    $problems = [];
    foreach ($messages as $message) {
        $problems[] = (string)$message;
    }
    echo json_encode(['status' => 'failed', 'errors' => $problems]) . PHP_EOL;
    exit(1);
}
$model->serializeToConfig();
$descr = $isService
    ? sprintf('Expire %d WAN quota service block(s)', count($removed))
    : sprintf('Expire %d WAN quota device block(s)', count($removed));
Config::getInstance()->save($descr);
echo json_encode(['status' => 'ok', 'removed' => count($removed),
                  'items' => array_column($removed, $itemKey)]) . PHP_EOL;
