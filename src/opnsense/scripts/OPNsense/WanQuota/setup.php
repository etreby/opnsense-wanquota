#!/usr/local/bin/php
<?php

require_once 'config.inc';
require_once 'util.inc';
require_once 'filter.inc';

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
    'device_blocks_json' => '[]',
    'balance_mode' => 'weights',
    'balance_enabled' => '0',
    'balance_dry_run' => '1',
    'balance_group' => '',
    'balance_max_weight' => '10',
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
 * Declare the two per-device tables as "external" aliases, and create the firewall
 * rules that make them mean something.
 *
 * Populating a bare pf table is not enough to be usable: firewall rules are written
 * against aliases, so a table OPNsense does not know about never appears in the rule
 * dropdown and cannot be selected. An external alias is precisely the type for a
 * table whose contents are maintained by something else — OPNsense owns its
 * lifecycle and shows it in the rule editor, while the plugin fills it.
 *
 * The rules used to be the administrator's job, and the documentation said so. That
 * was a mistake worth naming: a firewall with per-device enforcement switched on and
 * dry-run off filled a table that no rule consulted, so enforcement reported success
 * and blocked nothing. Creating the rules here closes that gap, and creating them is
 * safe for the same reason creating the alias is — both tables are empty at
 * creation, so both rules are live and match nothing.
 */
$tables = [
    'wanquota_over_budget' => 'WAN quota: devices over their per-device budget (maintained by os-wanquota)',
    'wanquota_blocked' => 'WAN quota: devices blocked from the internet (maintained by os-wanquota)',
];
try {
    $aliases = new \OPNsense\Firewall\Alias();
    $existing = [];
    foreach ($aliases->aliases->alias->iterateItems() as $alias) {
        $existing[(string)$alias->name] = true;
    }
    $added = [];
    foreach ($tables as $aliasName => $description) {
        if (isset($existing[$aliasName])) {
            continue;
        }
        $alias = $aliases->aliases->alias->Add();
        $alias->name = $aliasName;
        $alias->type = 'external';
        $alias->description = $description;
        $added[] = $aliasName;
    }
    if (!empty($added)) {
        $aliasErrors = $aliases->performValidation();
        if (count($aliasErrors) > 0) {
            foreach ($aliasErrors as $message) {
                fwrite(STDERR, 'alias: ' . (string)$message . PHP_EOL);
            }
        } else {
            $aliases->serializeToConfig();
            echo 'Created external alias(es): ' . implode(', ', $added) . "\n";
        }
    }
} catch (\Throwable $error) {
    // Never fail the install over this: everything except per-device enforcement
    // works without the aliases, and an alias can be created by hand.
    fwrite(STDERR, 'Could not create the WAN quota aliases: ' . $error->getMessage() . PHP_EOL);
}

/*
 * The rules themselves.
 *
 * Shape: block in on the LAN interface, from the alias, to anything that is *not*
 * the LAN network. The negated destination is what keeps a block from doing more
 * harm than was asked for:
 *
 *   * Internet access stops, which is the point.
 *   * LAN-to-LAN traffic is untouched. Most of it is switched and never reaches the
 *     firewall at all, but a device blocked from the internet should still be able
 *     to reach a printer or a NAS.
 *   * DNS and NTP served by the firewall keep working, because the firewall's own
 *     LAN address is inside the LAN network. Without that a blocked device would
 *     lose its clock and its resolver too, which is worse than what was asked for.
 *
 * Position: first. This was measured rather than assumed, and the first attempt was
 * wrong. The rules were appended, on the reasoning that the negated destination made
 * position irrelevant. It does not: OPNsense emits administrator pass rules as pf
 * `quick` rules, so a broad `pass in quick on em0 from <MY_DEVICES> to any` earlier
 * in the list matches first and the block is never evaluated. On the firewall this
 * was written for, the appended rule showed `Evaluations: 0` while the blocked
 * device browsed normally. Being first is what makes a block mean anything, and the
 * negated destination is what makes being first safe — the rules a block must not
 * override all address the firewall itself, which the negation already excludes.
 *
 * inet46 rather than inet: a pf table holds both families, so an IPv4-only rule
 * would leave a blocked device reaching the internet over IPv6.
 *
 * Any previous copy is removed first, wherever it sits, so an upgrade from a version
 * that appended them repairs the position instead of skipping the rule it already
 * recognises.
 */
$ruleSpecs = [
    'wanquota_over_budget' => 'Block devices over their WAN quota budget (os-wanquota)',
    'wanquota_blocked' => 'Block devices from the internet (os-wanquota)',
];
$createdRules = [];
try {
    $configObject = \OPNsense\Core\Config::getInstance()->object();
    if (!isset($configObject->filter)) {
        $configObject->addChild('filter');
    }
    $wanted = array_flip($ruleSpecs);
    /* Collect before removing: a live SimpleXML node list skips entries otherwise. */
    $stale = [];
    foreach ($configObject->filter->rule as $rule) {
        if (isset($wanted[(string)$rule->descr])) {
            $stale[] = dom_import_simplexml($rule);
        }
    }
    foreach ($stale as $node) {
        $node->parentNode->removeChild($node);
    }
    $filterDom = dom_import_simplexml($configObject->filter);
    $document = $filterDom->ownerDocument;
    $first = null;
    foreach ($filterDom->childNodes as $child) {
        if ($child->nodeType === XML_ELEMENT_NODE && $child->nodeName === 'rule') {
            $first = $child;
            break;
        }
    }
    /*
     * Reversed, inserting each before the last one placed, so the pair ends up in the
     * order listed above rather than mirrored.
     */
    foreach (array_reverse($ruleSpecs, true) as $aliasName => $description) {
        $rule = $document->createElement('rule');
        foreach (['type' => 'block', 'ipprotocol' => 'inet46', 'descr' => $description,
                  'interface' => 'lan', 'log' => '1'] as $field => $value) {
            $rule->appendChild($document->createElement($field, $value));
        }
        $source = $document->createElement('source');
        $source->appendChild($document->createElement('address', $aliasName));
        $rule->appendChild($source);
        $destination = $document->createElement('destination');
        $destination->appendChild($document->createElement('network', 'lan'));
        $destination->appendChild($document->createElement('not', '1'));
        $rule->appendChild($destination);
        if ($first === null) {
            $filterDom->appendChild($rule);
        } else {
            $filterDom->insertBefore($rule, $first);
        }
        $first = $rule;
        $createdRules[] = $description;
    }
    if (!empty($createdRules)) {
        echo 'Installed firewall rule(s) at the top of the LAN list: '
            . implode('; ', array_reverse($createdRules)) . "\n";
        echo "Both tables are empty, so the rules match nothing until a device is blocked.\n";
    }
} catch (\Throwable $error) {
    fwrite(STDERR, 'Could not create the WAN quota block rules: ' . $error->getMessage() . PHP_EOL);
}

\OPNsense\Core\Config::getInstance()->save('Initialize WAN quota and consumer reporting plugin');
/*
 * Reload the filter only when a rule was created. A rule sitting in the
 * configuration is not a rule pf is enforcing, and blocks.py only replaces table
 * contents — it never reloads rules — so without this the first block would fill a
 * table that pf had no rule for. Reloading on every install would be a needless
 * interruption on a firewall where nothing changed.
 */
if (!empty($createdRules)) {
    filter_configure();
    echo "Firewall reloaded so the new rule(s) are live\n";
}
echo "WAN quota settings and DNS collector schedule saved\n";
