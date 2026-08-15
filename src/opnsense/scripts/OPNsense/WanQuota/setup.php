#!/usr/local/bin/php
<?php

require_once 'config.inc';
require_once 'util.inc';

use OPNsense\WanQuota\WanQuota;

$model = new WanQuota();
$defaults = [
    'enabled' => '1',
    'provider1_name' => 'ISP 1',
    'provider1_interface' => 'wan',
    'provider1_quota_gb' => '100',
    'provider1_cycle_day' => '1',
    'provider1_warning_percent' => '80',
    'provider2_name' => 'ISP 2',
    'provider2_interface' => 'opt1',
    'provider2_quota_gb' => '100',
    'provider2_cycle_day' => '1',
    'provider2_warning_percent' => '80',
    'consumers_enabled' => '1',
    'domain_enabled' => '1',
    'top_limit' => '20',
    'default_period' => 'thirty',
    'domain_retention_days' => '90',
    'alerts_enabled' => '1',
    'projection_alert_enabled' => '1',
    'alert_repeat_hours' => '24',
];
foreach ($defaults as $field => $value) {
    if ((string)$model->general->{$field} === '') {
        $model->general->{$field} = $value;
    }
}

$validation = $model->performValidation();
if (count($validation) > 0) {
    foreach ($validation as $message) {
        fwrite(STDERR, (string)$message . PHP_EOL);
    }
    exit(1);
}

$model->serializeToConfig();

$cron = new \OPNsense\Cron\Cron();
$cronExists = false;
foreach ($cron->jobs->job->iterateItems() as $item) {
    if ((string)$item->description === 'Collect DNS mappings for WAN domain attribution') {
        // Adopt schedules created by the private preview package so future
        // uninstall operations can identify plugin-owned state reliably.
        $item->origin = 'wanquota';
        $cronExists = true;
        break;
    }
}
if (!$cronExists) {
    $job = $cron->jobs->job->add();
    $job->origin = 'wanquota';
    $job->enabled = '1';
    $job->minutes = '*/5';
    $job->hours = '*';
    $job->days = '*';
    $job->months = '*';
    $job->weekdays = '*';
    $job->who = 'root';
    $job->command = 'wanquota collect';
    $job->parameters = '';
    $job->description = 'Collect DNS mappings for WAN domain attribution';
    $cronValidation = $cron->performValidation();
    if (count($cronValidation) > 0) {
        foreach ($cronValidation as $message) {
            fwrite(STDERR, (string)$message . PHP_EOL);
        }
        exit(1);
    }
}

// Serialize even when adopting an older schedule with origin=cron.
$cron->serializeToConfig();

\OPNsense\Core\Config::getInstance()->save('Initialize WAN quota and consumer reporting plugin');
echo "WAN quota settings and DNS collector schedule saved\n";
