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

/*
 * Remove the shaper pipes and rules this plugin created. A bandwidth cap left
 * behind by a plugin that no longer exists would throttle traffic with nothing to
 * explain why.
 */
$shaper = '/usr/local/opnsense/scripts/OPNsense/WanQuota/shaper.php';
if (is_file($shaper)) {
    exec('/usr/local/bin/php ' . escapeshellarg($shaper) . ' flush 2>&1', $shaperOut, $shaperStatus);
    echo $shaperStatus === 0
        ? "Removed per-service bandwidth limits\n"
        : "WARNING: could not remove per-service bandwidth limits; check Firewall > Shaper\n";
}

/*
 * Release per-device enforcement before the plugin goes away. Leaving members in
 * the pf table would keep devices blocked by a rule whose owner no longer exists,
 * which is the one uninstall outcome that must not happen.
 */
$script = '/usr/local/opnsense/scripts/OPNsense/WanQuota/devices.py';
if (is_executable($script)) {
    exec(escapeshellarg($script) . ' flush 2>&1', $output, $status);
    echo $status === 0
        ? "Released per-device WAN quota enforcement\n"
        : "WARNING: could not release per-device enforcement; check the wanquota_over_budget pf table\n";
} else {
    exec('/sbin/pfctl -t wanquota_over_budget -T flush 2>&1', $ignored, $fallback);
    echo $fallback === 0
        ? "Flushed the per-device enforcement table\n"
        : "WARNING: per-device enforcement table may still hold members\n";
}
