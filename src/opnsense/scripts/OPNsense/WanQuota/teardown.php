#!/usr/local/bin/php
<?php

require_once 'config.inc';
require_once 'util.inc';

$cron = new \OPNsense\Cron\Cron();
$removed = 0;
$uuids = [];
foreach ($cron->jobs->job->iterateItems() as $item) {
    $description = (string)$item->description;
    $command = (string)$item->command;
    $origin = (string)$item->origin;
    if (
        ($origin === 'wanquota' && $command === 'wanquota collect') ||
        ($description === 'Collect DNS mappings for WAN domain attribution' && $command === 'wanquota collect')
    ) {
        $uuids[] = $item->getAttributes()['uuid'];
    }
}

foreach ($uuids as $uuid) {
    if ($cron->jobs->job->del($uuid)) {
        $removed++;
    }
}

if ($removed > 0) {
    $cron->serializeToConfig();
    \OPNsense\Core\Config::getInstance()->save('Remove WAN quota DNS collector schedule');
}

echo "Removed {$removed} WAN quota scheduler job(s)\n";
