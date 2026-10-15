#!/usr/local/bin/php
<?php

require_once 'config.inc';
require_once 'util.inc';
require_once 'filter.inc';

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

/*
 * Release manual internet blocks too. Same argument as above, and more pressing:
 * a budget block at least corresponds to something the device did, while a manual
 * block left behind by a plugin that no longer exists is a device with no internet
 * and nothing on the firewall to explain why.
 */
$blocks = '/usr/local/opnsense/scripts/OPNsense/WanQuota/blocks.py';
if (is_executable($blocks)) {
    exec(escapeshellarg($blocks) . ' flush 2>&1', $blockOut, $blockStatus);
    echo $blockStatus === 0
        ? "Released manual device internet blocks\n"
        : "WARNING: could not release manual blocks; check the wanquota_blocked pf table\n";
} else {
    exec('/sbin/pfctl -t wanquota_blocked -T flush 2>&1', $ignoredBlocks, $blockFallback);
    exec('/sbin/pfctl -t wanquota_blocked_services -T flush 2>&1', $ignoredServices, $serviceFallback);
    echo ($blockFallback === 0 && $serviceFallback === 0)
        ? "Flushed the manual block table\n"
        : "WARNING: the manual block table may still hold members\n";
}

/*
 * Put any gateway weight the balancer wrote back where it found it, before the
 * script that knows how to do so is removed. A household left permanently weighted
 * 10:1 towards one provider by a plugin that is gone would be a routing change with
 * no owner.
 */
$balance = '/usr/local/opnsense/scripts/OPNsense/WanQuota/balance.php';
if (is_file($balance)) {
    exec('/usr/local/bin/php ' . escapeshellarg($balance) . ' revert 2>&1', $balanceOut, $balanceStatus);
    echo $balanceStatus === 0
        ? "Reverted renewal-aware gateway weights\n"
        : "WARNING: could not revert gateway weights; check System > Gateways\n";
}

/*
 * Finally the rules. They are removed by description, which is how they were
 * recognised as already present at install, and only ours are touched.
 */
$descriptions = [
    'Block devices over their WAN quota budget (os-wanquota)',
    'Block devices from the internet (os-wanquota)',
    'Block traffic to blocked services (os-wanquota)',
];
$configObject = \OPNsense\Core\Config::getInstance()->object();
$removedRules = 0;
if (isset($configObject->filter)) {
    /* Collect first: removing from a live SimpleXML node list while iterating skips entries. */
    $doomed = [];
    foreach ($configObject->filter->rule as $rule) {
        if (in_array((string)$rule->descr, $descriptions, true)) {
            $doomed[] = $rule;
        }
    }
    foreach ($doomed as $rule) {
        $node = dom_import_simplexml($rule);
        $node->parentNode->removeChild($node);
        $removedRules++;
    }
}
if ($removedRules > 0) {
    \OPNsense\Core\Config::getInstance()->save(sprintf('Remove %d WAN quota block rule(s)', $removedRules));
    if (function_exists('filter_configure')) {
        filter_configure();
    }
    echo "Removed {$removedRules} WAN quota block rule(s)\n";
}
