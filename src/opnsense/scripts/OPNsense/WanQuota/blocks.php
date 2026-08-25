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

$keys = array_slice($argv, 2);
if (($argv[1] ?? '') !== 'expire' || empty($keys)) {
    echo json_encode(['status' => 'failed',
                      'error' => 'usage: blocks.php expire <device> [device...]']) . PHP_EOL;
    exit(1);
}

$model = new WanQuota();
$blocks = json_decode((string)$model->general->device_blocks_json, true);
$blocks = is_array($blocks) ? $blocks : [];

$wanted = [];
foreach ($keys as $key) {
    $wanted[strtolower(trim($key))] = true;
}

$kept = [];
$removed = [];
foreach ($blocks as $block) {
    $device = strtolower(trim((string)($block['device'] ?? '')));
    /*
     * Only drop an entry that is both named in the request and genuinely expired.
     * The request is a list of identifiers, and an identifier can be re-blocked
     * between the run that noticed the expiry and this call; re-checking the
     * timestamp means that new block survives.
     */
    $until = (int)($block['until'] ?? 0);
    if ($device !== '' && isset($wanted[$device]) && $until > 0 && $until <= time()) {
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

$model->general->device_blocks_json = json_encode($kept);
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
Config::getInstance()->save(sprintf('Expire %d WAN quota device block(s)', count($removed)));
echo json_encode(['status' => 'ok', 'removed' => count($removed),
                  'devices' => array_column($removed, 'device')]) . PHP_EOL;
