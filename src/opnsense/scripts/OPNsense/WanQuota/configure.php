#!/usr/local/bin/php
<?php

/*
 * Write plugin settings and limits through the model.
 *
 * The MCP server is Python and the configuration lives in a PHP model, so writes
 * go through this script rather than a nested configd call, which would have the
 * server asking configd to run something while configd is already running the
 * server. It reads one JSON instruction on stdin and prints one JSON result, so it
 * is equally usable by hand.
 *
 * Every write goes through performValidation() before being saved. A rejected
 * write changes nothing and returns the model's own messages: an agent editing a
 * quota should be told "not a number" by the same code that tells a person.
 */

require_once 'config.inc';
require_once 'util.inc';

/*
 * Fields an outside caller may set. An allowlist rather than "any field in the
 * model" so that adding a field to the model does not silently widen what a remote
 * caller can reach, and so an unknown name is a reported error instead of a value
 * written nowhere.
 */
const WRITABLE = [
    'enabled', 'consumers_enabled', 'domain_enabled', 'top_limit', 'default_period',
    'domain_retention_days', 'alerts_enabled', 'projection_alert_enabled',
    'alert_repeat_hours', 'intelligence_enabled', 'intelligence_retention_days',
    'anomaly_sigma', 'device_groups_json', 'device_policies_json',
    'domain_categories_json', 'enforcement_enabled', 'enforcement_dry_run',
    'device_enforcement_enabled', 'device_enforcement_dry_run', 'shaper_enabled',
    'shaper_dry_run', 'service_limits_json', 'device_limits_json',
    'enforcement_policy', 'guardrail_thresholds', 'emergency_reserve_gb',
    'webhook_enabled', 'webhook_url', 'webhook_format', 'webhook_recipient',
    'scheduled_reports_enabled', 'email_enabled', 'email_to', 'smtp_host',
    'smtp_port', 'smtp_username', 'smtp_password', 'prometheus_enabled',
    'dashboard_accent',
];

function writable_fields(): array
{
    $fields = WRITABLE;
    foreach (range(1, 4) as $index) {
        foreach (['enabled', 'name', 'interface', 'quota_gb', 'cycle_day',
                  'warning_percent', 'cycle_cost', 'baseline_gb', 'baseline_cycle'] as $suffix) {
            $fields[] = "provider{$index}_{$suffix}";
        }
    }
    return $fields;
}

function fail(string $message, array $extra = []): void
{
    echo json_encode(array_merge(['status' => 'failed', 'error' => $message], $extra)) . PHP_EOL;
    exit(1);
}

function decode_list(string $raw): array
{
    $value = json_decode($raw === '' ? '[]' : $raw, true);
    return is_array($value) ? $value : [];
}

/* A limit list keyed by its identifier, so an edit replaces rather than duplicates. */
function index_by(array $items, string $key): array
{
    $indexed = [];
    foreach ($items as $item) {
        $name = strtolower(trim((string)($item[$key] ?? '')));
        if ($name !== '') {
            $indexed[$name] = $item;
        }
    }
    return $indexed;
}

$raw = stream_get_contents(STDIN);
$request = json_decode((string)$raw, true);
if (!is_array($request)) {
    fail('a JSON instruction is required on stdin');
}
$action = (string)($request['action'] ?? '');

$model = new OPNsense\WanQuota\WanQuota();
$changed = [];
$allowed = writable_fields();

switch ($action) {
    case 'set_settings':
        $fields = $request['fields'] ?? null;
        if (!is_array($fields) || !$fields) {
            fail('fields must be a non-empty object');
        }
        $unknown = array_diff(array_keys($fields), $allowed);
        if ($unknown) {
            fail('not a writable setting: ' . implode(', ', $unknown),
                 ['writable' => $allowed]);
        }
        foreach ($fields as $name => $value) {
            if (is_bool($value)) {
                $value = $value ? '1' : '0';
            }
            $model->general->$name = (string)$value;
            $changed[] = $name;
        }
        break;

    case 'set_service_limit':
    case 'remove_service_limit':
        $service = strtolower(trim((string)($request['service'] ?? '')));
        if ($service === '') {
            fail('service is required');
        }
        $limits = index_by(decode_list((string)$model->general->service_limits_json), 'service');
        if ($action === 'remove_service_limit') {
            if (!isset($limits[$service])) {
                fail(sprintf('no limit is set for %s', $service));
            }
            unset($limits[$service]);
        } else {
            $entry = ['service' => $service, 'enabled' => true];
            $mbit = $request['mbit'] ?? null;
            $resolution = strtolower(trim((string)($request['resolution'] ?? '')));
            if ($mbit !== null && $mbit !== '') {
                if (!is_numeric($mbit) || (float)$mbit <= 0) {
                    fail('mbit must be a positive number');
                }
                $entry['mbit'] = (float)$mbit;
            } elseif ($resolution !== '') {
                $entry['resolution'] = $resolution;
            } else {
                fail('either mbit or resolution is required');
            }
            $limits[$service] = $entry;
        }
        $model->general->service_limits_json = json_encode(array_values($limits));
        $changed[] = 'service_limits_json';
        break;

    case 'set_device_limit':
    case 'remove_device_limit':
        $device = trim((string)($request['device'] ?? ''));
        if ($device === '') {
            fail('device is required (address, MAC or DHCP hostname)');
        }
        $limits = index_by(decode_list((string)$model->general->device_limits_json), 'device');
        $key = strtolower($device);
        if ($action === 'remove_device_limit') {
            if (!isset($limits[$key])) {
                fail(sprintf('no limit is set for %s', $device));
            }
            unset($limits[$key]);
        } else {
            $mbit = $request['mbit'] ?? null;
            if ($mbit === null || $mbit === '' || !is_numeric($mbit) || (float)$mbit <= 0) {
                fail('mbit must be a positive number');
            }
            $entry = ['device' => $device, 'enabled' => true, 'mbit' => (float)$mbit];
            $upload = $request['upload_mbit'] ?? null;
            if ($upload !== null && $upload !== '') {
                if (!is_numeric($upload) || (float)$upload <= 0) {
                    fail('upload_mbit must be a positive number');
                }
                $entry['upload_mbit'] = (float)$upload;
            }
            $limits[$key] = $entry;
        }
        $model->general->device_limits_json = json_encode(array_values($limits));
        $changed[] = 'device_limits_json';
        break;

    default:
        fail(sprintf('unknown action: %s', $action === '' ? '(none)' : $action),
             ['actions' => ['set_settings', 'set_service_limit', 'remove_service_limit',
                            'set_device_limit', 'remove_device_limit']]);
}

/*
 * The two shaper switches are accepted alongside a limit edit, because "cap YouTube
 * to 480p" from an agent almost always means "and turn it on". They are optional, so
 * a caller that only wants to record a limit can leave the state alone.
 */
foreach (['enabled' => 'shaper_enabled', 'dry_run' => 'shaper_dry_run'] as $key => $field) {
    if (array_key_exists($key, $request) && $request[$key] !== null) {
        $model->general->$field = !empty($request[$key]) ? '1' : '0';
        $changed[] = $field;
    }
}

$messages = $model->performValidation();
if (count($messages) > 0) {
    $problems = [];
    foreach ($messages as $message) {
        $problems[] = (string)$message;
    }
    fail('validation failed; nothing was changed', ['messages' => $problems]);
}
$model->serializeToConfig();
OPNsense\Core\Config::getInstance()->save('WAN quota configuration changed via API');

$result = ['status' => 'ok', 'action' => $action, 'changed' => array_values(array_unique($changed))];

/*
 * A limit that is saved but not applied shapes nothing, and an agent has no way to
 * notice. Applying is therefore part of a limit change rather than a second call the
 * caller has to remember. shaper.py's sync decides whether anything needs doing, so
 * an edit that changes nothing does not reload the shaper.
 */
if ($action !== 'set_settings' || array_intersect($changed, ['shaper_enabled', 'shaper_dry_run'])) {
    $script = __DIR__ . '/shaper.py';
    exec(escapeshellarg($script) . ' sync 2>&1', $output, $status);
    $result['shaper'] = ['ok' => $status === 0, 'detail' => trim(implode("\n", $output))];
}

echo json_encode($result) . PHP_EOL;
