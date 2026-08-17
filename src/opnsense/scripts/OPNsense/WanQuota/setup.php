#!/usr/local/bin/php
<?php

require_once 'config.inc';
require_once 'util.inc';

use OPNsense\WanQuota\WanQuota;

$model = new WanQuota();
$defaults = [
    'enabled' => '1',
    'provider1_enabled' => '1',
    'provider1_name' => 'ISP 1',
    'provider1_interface' => 'wan',
    'provider1_quota_gb' => '100',
    'provider1_cycle_day' => '1',
    'provider1_warning_percent' => '80',
    'provider1_cycle_cost' => '0',
    'provider1_baseline_gb' => '0',
    'provider1_baseline_cycle' => '',
    'provider2_enabled' => '1',
    'provider2_name' => 'ISP 2',
    'provider2_interface' => 'opt1',
    'provider2_quota_gb' => '100',
    'provider2_cycle_day' => '1',
    'provider2_warning_percent' => '80',
    'provider2_cycle_cost' => '0',
    'provider2_baseline_gb' => '0',
    'provider2_baseline_cycle' => '',
    'provider3_enabled' => '0',
    'provider3_name' => 'ISP 3',
    'provider3_interface' => 'wan',
    'provider3_quota_gb' => '100',
    'provider3_cycle_day' => '1',
    'provider3_warning_percent' => '80',
    'provider3_cycle_cost' => '0',
    'provider3_baseline_gb' => '0',
    'provider3_baseline_cycle' => '',
    'provider4_enabled' => '0',
    'provider4_name' => 'ISP 4',
    'provider4_interface' => 'wan',
    'provider4_quota_gb' => '100',
    'provider4_cycle_day' => '1',
    'provider4_warning_percent' => '80',
    'provider4_cycle_cost' => '0',
    'provider4_baseline_gb' => '0',
    'provider4_baseline_cycle' => '',
    'consumers_enabled' => '1',
    'domain_enabled' => '1',
    'top_limit' => '20',
    'default_period' => 'thirty',
    'domain_retention_days' => '90',
    'alerts_enabled' => '1',
    'projection_alert_enabled' => '1',
    'alert_repeat_hours' => '24',
    'intelligence_enabled' => '1',
    'intelligence_retention_days' => '730',
    'anomaly_sigma' => '3',
    'device_groups_json' => '[]',
    'device_policies_json' => '[]',
    'domain_categories_json' => '{}',
    'enforcement_enabled' => '0',
    'enforcement_dry_run' => '1',
    'enforcement_policy' => 'observe',
    'guardrail_thresholds' => '50,75,90,100',
    'emergency_reserve_gb' => '5',
    'webhook_enabled' => '0',
    'webhook_url' => '',
    'webhook_format' => 'generic',
    'webhook_recipient' => '',
    'scheduled_reports_enabled' => '0',
    'email_enabled' => '0',
    'email_to' => '',
    'smtp_host' => '',
    'smtp_port' => '587',
    'smtp_username' => '',
    'smtp_password' => '',
    'prometheus_enabled' => '0',
    'dashboard_accent' => '#3b82f6',
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

/*
 * Declare the per-device enforcement table as an "external" alias.
 *
 * Populating a bare pf table is not enough to be usable: firewall rules are
 * written against aliases, so a table OPNsense does not know about never appears
 * in the rule dropdown and cannot be selected. An external alias is precisely the
 * type for a table whose contents are maintained by something else — OPNsense
 * owns its lifecycle and shows it in the rule editor, while the plugin fills it.
 *
 * The alias is created empty and stays empty until per-device enforcement is
 * enabled, which is off by default. Creating it changes no traffic on its own.
 */
$aliasName = 'wanquota_over_budget';
try {
    $aliases = new \OPNsense\Firewall\Alias();
    $exists = false;
    foreach ($aliases->aliases->alias->iterateItems() as $alias) {
        if ((string)$alias->name === $aliasName) {
            $exists = true;
            break;
        }
    }
    if (!$exists) {
        $alias = $aliases->aliases->alias->Add();
        $alias->name = $aliasName;
        $alias->type = 'external';
        $alias->description = 'WAN quota: devices over their per-device budget (maintained by os-wanquota)';
        $aliasErrors = $aliases->performValidation();
        if (count($aliasErrors) > 0) {
            foreach ($aliasErrors as $message) {
                fwrite(STDERR, 'alias: ' . (string)$message . PHP_EOL);
            }
        } else {
            $aliases->serializeToConfig();
            echo "Created the {$aliasName} external alias for per-device enforcement\n";
        }
    }
} catch (\Throwable $error) {
    // Never fail the install over this: everything except per-device enforcement
    // works without the alias, and the alias can be created by hand.
    fwrite(STDERR, "Could not create the {$aliasName} alias: " . $error->getMessage() . PHP_EOL);
}

\OPNsense\Core\Config::getInstance()->save('Initialize WAN quota and consumer reporting plugin');
echo "WAN quota settings and DNS collector schedule saved\n";
